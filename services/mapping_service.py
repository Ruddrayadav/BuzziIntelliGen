"""
services/mapping_service.py
----------------------------
Suggests a mapping from the user's raw CSV column names to our standard schema.

THE PROBLEM IT SOLVES:
  Every restaurant's CSV has different column names:
    - "Amt", "Total Sale", "₹ Amount", "Revenue", "Net"  → all mean "revenue"
    - "Dt", "Date", "Sale Date", "Transaction Date"       → all mean "date"
    - "Item", "Dish", "Menu Item", "Product Name"         → all mean "product"

  We can't store data from 10 different schemas — our analytics code would
  need 10 different queries. So we standardise FIRST, then store.

HOW IT WORKS:
  1. Rule-based matching: we maintain a dictionary of known aliases for each
     standard field. This handles ~90% of cases instantly and reliably.
  2. LLM for ambiguous names: if a column like "SKU_REF" or "Txn_Amt" doesn't
     match any rule, we ask the LLM. The LLM receives ONLY the column NAME,
     never cell values (prompt injection defence — Core Principle #6).
  3. The UI shows the suggestion. The owner confirms or corrects it.
     Nothing is stored until the owner approves.

SECURITY:
  The LLM never sees uploaded file content. Column names are short strings
  controlled by the file author, not necessarily by the owner — but even
  column names could theoretically contain injection attempts. We sanitise
  column names (strip to printable ASCII) before sending to the LLM.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Standard schema definitions
# ─────────────────────────────────────────────────────────────────────────────

# Required columns — without these we cannot do ANY meaningful analysis.
SALES_REQUIRED: list[str] = ["date", "product", "revenue"]
EXPENSES_REQUIRED: list[str] = ["date", "category", "amount"]

# All standard columns per file type (required + optional)
STANDARD_COLUMNS: dict[str, list[str]] = {
    "sales": ["date", "order_id", "product", "category", "quantity", "unit_price", "revenue"],
    "expenses": ["date", "category", "description", "amount"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Alias dictionaries
# ─────────────────────────────────────────────────────────────────────────────
# WHY SEPARATE ALIAS MAPS PER FILE TYPE?
#   "amount" and "total" can mean revenue (sales) OR expense amount (expenses).
#   Separating the maps lets us resolve this ambiguity based on file_type.
#
# HOW TO READ:
#   "date": ["dt", "sale date", ...]  means: if the raw column, after
#   normalising to lowercase, matches any string in this list, we map it
#   to the "date" standard field.

_SALES_ALIASES: dict[str, list[str]] = {
    "date": [
        "date", "dt", "sale date", "sales date", "transaction date",
        "order date", "dated", "bill date", "invoice date", "entry date",
        "trans date", "trx date",
    ],
    "order_id": [
        "order id", "orderid", "order no", "order number", "order_id",
        "bill no", "bill number", "receipt no", "receipt", "invoice no",
        "invoice number", "transaction id", "txn id", "txn no",
        "voucher no", "ref no", "reference",
    ],
    "product": [
        "product", "item", "item name", "dish", "product name", "menu item",
        "article", "goods", "name", "service", "product description",
        "item description", "food item", "menu", "sku name",
    ],
    "category": [
        "category", "cat", "type", "dept", "department", "section",
        "group", "sub category", "product type", "item type", "class",
        "product category",
    ],
    "quantity": [
        "quantity", "qty", "units", "count", "pieces", "pcs",
        "nos", "unit quantity", "sold", "number of units", "no of units",
        "quantity sold",
    ],
    "unit_price": [
        "unit price", "price", "rate", "mrp", "selling price", "sp",
        "cost price", "per unit", "price per unit", "unit cost",
        "unit_price", "sale price", "item price",
    ],
    "revenue": [
        "revenue", "total", "total amount", "amount", "sales", "sale amount",
        "amt", "gross", "income", "total revenue", "net amount",
        "bill amount", "invoice amount", "value", "subtotal", "net sales",
        "gross amount", "total sale", "sale value", "earning",
    ],
}

_EXPENSES_ALIASES: dict[str, list[str]] = {
    "date": [
        "date", "dt", "expense date", "transaction date", "dated",
        "payment date", "entry date", "bill date", "voucher date",
    ],
    "category": [
        "category", "cat", "type", "expense type", "expense category",
        "dept", "department", "head", "account head", "ledger",
        "nature", "class", "group",
    ],
    "description": [
        "description", "details", "remarks", "notes", "particulars",
        "narration", "memo", "comment", "detail", "note", "info",
        "narrative", "item", "expense details",
    ],
    "amount": [
        "amount", "amt", "total", "expense amount", "cost", "paid",
        "payment", "value", "charge", "fee", "expense", "debit",
        "total amount", "bill amount", "net amount", "gross amount",
    ],
}

_ALIAS_MAP: dict[str, dict[str, list[str]]] = {
    "sales": _SALES_ALIASES,
    "expenses": _EXPENSES_ALIASES,
}


# ─────────────────────────────────────────────────────────────────────────────
# Return type
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ColumnMapping:
    """
    The result of a mapping suggestion run.

    FIELDS:
      file_type    — "sales" or "expenses"
      suggested    — {raw_col: standard_col or None}  e.g. {"Amt": "revenue"}
      method       — {raw_col: "rule" | "llm" | "unmapped"}
                     Tells the UI HOW we made the suggestion (for transparency).

    PROPERTIES:
      mapped_standard  — which standard fields have been mapped (keys of reverse map)
      unmapped_raw     — raw columns we couldn't map to anything
      missing_required — required standard fields still unmapped
      is_complete      — True if all required fields are covered

    USAGE:
      mapping = suggest_mapping(df.columns.tolist(), "sales")
      if not mapping.is_complete:
          show("Please manually map: " + str(mapping.missing_required))
      confirmed = owner_confirms(mapping.suggested)  # UI step
      clean_df = apply_mapping(df, confirmed)
    """

    file_type: str
    suggested: dict[str, Optional[str]] = field(default_factory=dict)
    method: dict[str, str] = field(default_factory=dict)

    @property
    def mapped_standard(self) -> list[str]:
        """Standard field names that have been mapped to at least one raw column."""
        return [v for v in self.suggested.values() if v is not None]

    @property
    def unmapped_raw(self) -> list[str]:
        """Raw column names that couldn't be mapped to any standard field."""
        return [k for k, v in self.suggested.items() if v is None]

    @property
    def missing_required(self) -> list[str]:
        """Required standard fields that have no raw column mapped to them."""
        required = (
            SALES_REQUIRED if self.file_type == "sales" else EXPENSES_REQUIRED
        )
        return [r for r in required if r not in self.mapped_standard]

    @property
    def is_complete(self) -> bool:
        """True if all required fields are covered by the mapping."""
        return len(self.missing_required) == 0

    def to_rename_dict(self) -> dict[str, str]:
        """
        Return only the confirmed (non-None) mappings as {raw: standard}.
        Pass this to apply_mapping().
        """
        return {k: v for k, v in self.suggested.items() if v is not None}

    def summary_lines(self) -> list[str]:
        """Human-readable lines for display in the UI."""
        lines = []
        for raw, std in self.suggested.items():
            how = self.method.get(raw, "?")
            if std:
                lines.append(f"  '{raw}'  →  '{std}'  [{how}]")
            else:
                lines.append(f"  '{raw}'  →  ⚠️ unmapped")
        return lines


# ─────────────────────────────────────────────────────────────────────────────
# Internal: normalise a column name for comparison
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_col(col: str) -> str:
    """
    Prepare a column name for alias matching.

    Steps:
      1. Lowercase
      2. Strip leading/trailing whitespace
      3. Replace underscores and hyphens with spaces
      4. Collapse multiple spaces

    Examples:
      "Order_ID"    → "order id"
      "Sale-Amount" → "sale amount"
      "  Qty  "     → "qty"
      "UNIT_PRICE"  → "unit price"
    """
    col = col.lower().strip()
    col = col.replace("_", " ").replace("-", " ")
    col = " ".join(col.split())   # collapse multiple spaces
    return col


def _sanitize_for_llm(col: str) -> str:
    """
    Strip a column name to printable ASCII before sending to the LLM.
    Prevents any non-ASCII characters in column names from being misinterpreted.
    Only keep letters, digits, spaces, underscores, hyphens, and dots.
    """
    return re.sub(r"[^\w\s.\-]", "", col, flags=re.ASCII).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based matching
# ─────────────────────────────────────────────────────────────────────────────
def _match_by_rules(raw_col: str, file_type: str) -> Optional[str]:
    """
    Try to match a single raw column name to a standard field using aliases.

    Returns the standard field name (e.g. "revenue") if found, else None.

    This is O(n) in the number of aliases — fast, deterministic, and
    requires no network call to Ollama.
    """
    aliases = _ALIAS_MAP.get(file_type, {})
    normalised = _normalize_col(raw_col)

    for standard_col, known_aliases in aliases.items():
        if normalised in known_aliases:
            return standard_col

    return None


# ─────────────────────────────────────────────────────────────────────────────
# LLM-based matching
# ─────────────────────────────────────────────────────────────────────────────
def _match_by_llm(
    unmapped_cols: list[str], file_type: str
) -> dict[str, Optional[str]]:
    """
    Ask the LLM to suggest mappings for column names that rules couldn't match.

    SECURITY:
      - We send ONLY the column names (strings like "SKU_REF"), never cell values.
      - Each name is sanitised through _sanitize_for_llm() first.
      - The system prompt makes it clear this is a naming task only.

    Args:
        unmapped_cols: Column names rules couldn't match.
        file_type:     "sales" or "expenses"

    Returns:
        {raw_col: standard_col_or_None} for each input column.
    """
    from llm.llm import LLMError, call_llm_json

    standard_fields = STANDARD_COLUMNS[file_type]
    # Sanitise column names before sending to LLM
    safe_cols = {col: _sanitize_for_llm(col) for col in unmapped_cols}

    system_prompt = (
        f"You are a data schema expert. Your only job is to match CSV column names "
        f"to standard field names for {file_type} data.\n\n"
        f"Standard fields for {file_type}: {standard_fields}\n\n"
        f"Field definitions:\n"
        + _field_definitions(file_type) +
        "\n\nRules:\n"
        "- Match by meaning, not spelling.\n"
        "- Return null if no standard field fits.\n"
        "- Do NOT look at or mention any data values — only column names.\n"
        "- Return ONLY a JSON array, no prose.\n"
        'Format: [{"raw": "OriginalName", "standard": "field_name_or_null"}]'
    )

    prompt = (
        f"Map these column names to standard {file_type} fields:\n"
        + "\n".join(f"- {v}" for v in safe_cols.values())
    )

    try:
        response = call_llm_json(prompt=prompt, system_prompt=system_prompt)

        # Response should be a list of {"raw": ..., "standard": ...}
        mappings: dict[str, Optional[str]] = {}

        items = response if isinstance(response, list) else response.get("mappings", [])

        # Build a lookup from safe_name → original_name
        safe_to_orig = {v: k for k, v in safe_cols.items()}

        for item in items:
            if not isinstance(item, dict):
                continue
            safe_name = str(item.get("raw", "")).strip()
            standard = item.get("standard")
            # Validate that suggested standard is actually a valid field
            if standard and standard not in standard_fields:
                logger.warning(
                    "LLM suggested invalid field %r for %r — ignoring", standard, safe_name
                )
                standard = None
            orig = safe_to_orig.get(safe_name, safe_name)
            mappings[orig] = standard if standard else None

        # Fill in any columns the LLM missed
        for orig in unmapped_cols:
            if orig not in mappings:
                mappings[orig] = None

        return mappings

    except LLMError as exc:
        logger.warning("LLM mapping failed (%s) — marking columns as unmapped", exc)
        return {col: None for col in unmapped_cols}


def _field_definitions(file_type: str) -> str:
    """Return a short definition of each standard field for the LLM prompt."""
    sales_defs = {
        "date": "The date the sale happened",
        "order_id": "A unique identifier for the transaction or bill",
        "product": "The name of the item or dish sold",
        "category": "The type/group the product belongs to (e.g. Beverages, Main Course)",
        "quantity": "How many units were sold",
        "unit_price": "The price of one unit",
        "revenue": "The total money earned (quantity × unit_price, or just the total amount)",
    }
    expenses_defs = {
        "date": "The date the expense occurred",
        "category": "The type of expense (e.g. Rent, Salaries, Raw Materials)",
        "description": "A free-text note describing what the expense was for",
        "amount": "How much money was spent",
    }
    defs = sales_defs if file_type == "sales" else expenses_defs
    return "\n".join(f"  {k}: {v}" for k, v in defs.items())


# ─────────────────────────────────────────────────────────────────────────────
# Public: suggest mapping
# ─────────────────────────────────────────────────────────────────────────────
def suggest_mapping(
    columns: list[str],
    file_type: str,
    use_llm: bool = True,
) -> ColumnMapping:
    """
    Suggest a mapping from raw CSV column names to the standard schema.

    This is the main public function. Call it with the column names from
    the uploaded DataFrame and let it do the work.

    Args:
        columns:   List of raw column names from the CSV/Excel file.
        file_type: "sales" or "expenses"
        use_llm:   If True (default), call the LLM for columns that rules
                   can't match. Set to False in tests or when Ollama is offline.

    Returns:
        ColumnMapping with suggested mappings and methods.

    Example:
        df = pd.read_csv("upload.csv")
        mapping = suggest_mapping(df.columns.tolist(), file_type="sales")
        print(mapping.missing_required)   # ["revenue"]  ← owner must map this
        print(mapping.summary_lines())
    """
    file_type = file_type.strip().lower()
    if file_type not in _ALIAS_MAP:
        raise ValueError(f"Unknown file_type {file_type!r}. Expected 'sales' or 'expenses'.")

    result = ColumnMapping(file_type=file_type)
    unmapped: list[str] = []

    # ── Pass 1: rule-based matching ──────────────────────────────────────────
    for col in columns:
        standard = _match_by_rules(col, file_type)
        if standard:
            result.suggested[col] = standard
            result.method[col] = "rule"
        else:
            unmapped.append(col)

    logger.info(
        "Rule-based mapping: %d/%d columns matched, %d unmapped",
        len(result.suggested), len(columns), len(unmapped),
    )

    # ── Pass 2: LLM for unmapped columns ────────────────────────────────────
    if unmapped and use_llm:
        logger.info("Asking LLM to help map %d ambiguous columns: %s", len(unmapped), unmapped)
        llm_results = _match_by_llm(unmapped, file_type)
        for col, standard in llm_results.items():
            result.suggested[col] = standard
            result.method[col] = "llm" if standard else "unmapped"
    else:
        # No LLM — mark remaining as unmapped
        for col in unmapped:
            result.suggested[col] = None
            result.method[col] = "unmapped"

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public: apply confirmed mapping to a DataFrame
# ─────────────────────────────────────────────────────────────────────────────
def apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """
    Rename DataFrame columns from raw names to standard names, and drop
    any columns not included in the mapping.

    This is called AFTER the owner has confirmed the suggested mapping in
    the UI. The result is a DataFrame with only the standard column names,
    ready to pass to cleaning_service.clean_dataframe().

    Args:
        df:      Raw DataFrame with original column names.
        mapping: Confirmed {raw_col: standard_col} dict.
                 Use ColumnMapping.to_rename_dict() to build this.

    Returns:
        DataFrame with standard column names, only mapped columns kept.

    Example:
        confirmed = {"Dt": "date", "Item Name": "product", "Amt": "revenue"}
        standard_df = apply_mapping(raw_df, confirmed)
        # standard_df.columns → ["date", "product", "revenue"]
    """
    # Only keep columns that exist in both the DataFrame and the mapping
    valid_mapping = {raw: std for raw, std in mapping.items() if raw in df.columns}

    if not valid_mapping:
        raise ValueError(
            "None of the mapping keys exist in the DataFrame. "
            f"DataFrame columns: {df.columns.tolist()}"
        )

    return df[list(valid_mapping.keys())].rename(columns=valid_mapping).copy()
