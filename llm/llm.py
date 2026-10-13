"""
llm/llm.py
-----------
Single gateway for every LLM call in this project.

WHY ONE WRAPPER?
  If we called ChatOllama() directly in each service file, swapping the model
  would require hunting through 10 files. Here, everything is in one place:
    - Change LLM_MODEL in config.py → every service uses the new model.
    - Change OLLAMA_BASE_URL → works for remote Ollama too.
    - Add retry logic, logging, or cost tracking → one place to do it.

WHAT THIS FILE DOES NOT DO:
  - It does not contain business logic or prompt text.
    Prompts live in the service that needs them.
  - It does not decide what question to ask. Services do that.
  - It does not calculate anything. It only calls the model and
    returns the raw text or parsed JSON.

SECURITY NOTE:
  We NEVER pass cell values from uploaded files into prompts here.
  Callers are responsible for passing only safe, code-controlled text.
  This prevents prompt injection (Core Design Principle #6).
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Custom exception
# ─────────────────────────────────────────────────────────────────────────────
class LLMError(Exception):
    """
    Raised when the LLM call fails (Ollama is down, model not loaded, etc.)

    WHY A CUSTOM EXCEPTION?
      If we let the underlying exception bubble up, the caller gets a cryptic
      httpx.ConnectError or OllamaError. Our custom LLMError has a friendly
      message and can be caught specifically:

        try:
            result = call_llm(prompt)
        except LLMError as e:
            show_user("AI is unavailable. Using rule-based fallback.")
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# LLM factory
# ─────────────────────────────────────────────────────────────────────────────
def get_llm(temperature: float = 0.0) -> ChatOllama:
    """
    Create and return a configured ChatOllama instance.

    temperature=0.0 means the model always picks the most likely token —
    deterministic and predictable. Good for structured tasks like column
    mapping or function selection. For explanations (Phase 4), we might
    use temperature=0.3 to get slightly more natural language.

    We create a new instance per call because ChatOllama is stateless —
    it doesn't hold conversation history between calls.
    """
    return ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=temperature,
        num_predict=settings.LLM_MAX_TOKENS,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Basic LLM call → plain text
# ─────────────────────────────────────────────────────────────────────────────
def call_llm(prompt: str, system_prompt: str = "", temperature: float = 0.0) -> str:
    """
    Send a prompt to the LLM and return the response as a plain string.

    This is the simplest call — used when we just need an explanation in
    natural language (Phase 4: "explain why profit dropped").

    Args:
        prompt:        The user-facing question or instruction.
        system_prompt: Background instructions that shape the model's behaviour.
                       Example: "You are a business analyst. Be concise."
        temperature:   0.0 = deterministic; 0.7 = more creative.

    Returns:
        The model's response as a stripped string.

    Raises:
        LLMError: If Ollama is unreachable or the model returns an error.

    Example:
        text = call_llm(
            prompt="Explain in one sentence why revenue was highest in February.",
            system_prompt="You are a helpful business assistant. Use simple words."
        )
    """
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=prompt))

    try:
        llm = get_llm(temperature=temperature)
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        raise LLMError(
            f"Could not reach the AI model ({settings.LLM_MODEL}). "
            "Make sure Ollama is running: `ollama serve`"
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# JSON-returning LLM call
# ─────────────────────────────────────────────────────────────────────────────
def call_llm_json(prompt: str, system_prompt: str = "") -> dict[str, Any]:
    """
    Call the LLM expecting a JSON response. Returns a parsed Python dict.

    WHY NOT with_structured_output()?
      LangChain's with_structured_output() relies on function/tool calling,
      which is not reliable for all local models (gemma3:4b may not support it).
      Instead, we instruct the model to output JSON in the prompt, then
      extract and parse it from the raw response text. More robust.

    Strategy:
      1. Add a JSON instruction to the system prompt.
      2. Call call_llm() to get raw text.
      3. Try to parse it directly as JSON.
      4. If that fails, search the text for a JSON block (model sometimes
         wraps JSON in ```json ... ``` or adds prose around it).
      5. If still failing, raise LLMError.

    Args:
        prompt:        The question to ask.
        system_prompt: Background instructions. "Return ONLY valid JSON." is
                       appended automatically.

    Returns:
        Parsed Python dict or list.

    Raises:
        LLMError: If the model's response cannot be parsed as JSON.

    Example:
        result = call_llm_json(
            prompt='Map ["Dt", "Amt"] to standard column names.',
            system_prompt="You map CSV column names. Return JSON only."
        )
        # result = {"mappings": [{"raw": "Dt", "standard": "date"}, ...]}
    """
    json_instruction = (
        "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no prose, "
        "no explanation — just the raw JSON object or array."
    )
    full_system = system_prompt + json_instruction

    raw_text = call_llm(prompt=prompt, system_prompt=full_system, temperature=0.0)

    return _extract_json(raw_text)


# ─────────────────────────────────────────────────────────────────────────────
# Internal: extract JSON from potentially noisy LLM output
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict[str, Any]:
    """
    Extract and parse JSON from an LLM response that may contain surrounding prose.

    Tries three strategies in order:
      1. Parse the whole string directly.
      2. Find a ```json ... ``` fenced code block.
      3. Find the first { ... } or [ ... ] block using regex.

    Raises:
        LLMError: If no valid JSON could be extracted.
    """
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fenced code block
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first JSON object or array
    raw_json = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", text)
    if raw_json:
        try:
            return json.loads(raw_json.group(1))
        except json.JSONDecodeError:
            pass

    raise LLMError(
        f"LLM returned text that could not be parsed as JSON. "
        f"Response preview: {text[:300]!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Availability check
# ─────────────────────────────────────────────────────────────────────────────
def is_llm_available() -> bool:
    """
    Return True if Ollama is reachable and the configured model responds.
    Used at startup and in the UI to show a friendly warning if AI is offline.
    """
    try:
        call_llm(prompt="Reply with the word OK.", temperature=0.0)
        return True
    except LLMError:
        return False
