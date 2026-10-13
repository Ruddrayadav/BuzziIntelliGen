"""
config.py
---------
Central configuration for the entire application.

WHY THIS EXISTS:
  Instead of scattering magic strings (file paths, model names, limits) across
  every file, we define them once here. When you move from SQLite to PostgreSQL,
  or swap gemma3 for a different model, you change ONE line — here.

USAGE:
  from config import settings
  print(settings.DB_URL)
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Paths ────────────────────────────────────────────────────────────────────
# Path(__file__) is the location of THIS file (config.py).
# .parent gives the project root folder.
PROJECT_ROOT = Path(__file__).parent


class Settings(BaseSettings):
    """
    All application settings in one place.

    Pydantic's BaseSettings lets you override any value via environment
    variables or a .env file without changing code — useful for deployment.
    For example: export DB_URL="postgresql://user:pass@localhost/biz_db"
    """

    model_config = SettingsConfigDict(
        env_file=".env",          # optional: override settings in a .env file
        env_file_encoding="utf-8",
        extra="ignore",           # ignore unknown env vars silently
    )

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite stores everything in a single file — perfect for development.
    # The triple slash (///) means "relative path from the current directory".
    DB_URL: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'biz_intelligence.db'}"

    # ── LLM / Ollama ─────────────────────────────────────────────────────────
    # The model name must exactly match what `ollama list` shows.
    # Change this one line to swap models globally.
    LLM_MODEL: str = "gemma3:4b"

    # Base URL where Ollama is running locally.
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Maximum tokens the LLM can return per response.
    LLM_MAX_TOKENS: int = 1024

    # ── File Upload ───────────────────────────────────────────────────────────
    UPLOAD_DIR: Path = PROJECT_ROOT / "data" / "uploads"

    # Maximum file size in bytes (10 MB).
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024

    # Accepted file extensions (lowercase).
    ALLOWED_EXTENSIONS: list[str] = [".csv", ".xlsx", ".xls"]

    # ── Data Cleaning ─────────────────────────────────────────────────────────
    # Duplicate rows with ALL these columns identical are dropped.
    SALES_DEDUP_COLUMNS: list[str] = ["date", "order_id", "product", "revenue"]
    EXPENSES_DEDUP_COLUMNS: list[str] = ["date", "category", "amount"]

    # ── App Display ───────────────────────────────────────────────────────────
    APP_NAME: str = "BizIntel — Business Intelligence for Small Businesses"
    APP_ICON: str = "📊"

    # ── Security ─────────────────────────────────────────────────────────────
    # Row limit for LLM-generated SQL queries (Phase 4 safety net).
    SQL_FALLBACK_ROW_LIMIT: int = 500

    # Timeout in seconds for SQL fallback queries.
    SQL_FALLBACK_TIMEOUT_SECONDS: int = 10


# Create the single shared instance. Every other file imports THIS object.
settings = Settings()

# Ensure the upload directory exists at startup.
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
