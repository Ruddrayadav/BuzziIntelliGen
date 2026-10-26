"""
services/cleaning_service.py
-----------------------------
Cleans a raw, messy Pandas DataFrame and returns a standardised, valid one.

DESIGN PRINCIPLES:
  1. One small function per cleaning rule — easy to test individually.
  2. Nothing in here touches the database or the UI. It only transforms
     DataFrames and returns a CleaningResult object.
  3. Every dropped row is recorded with a reason so the owner can see
     "3 rows had unparseable dates and were dropped".
  4. Input is ALWAYS treated as untrusted text. We never eval() or exec()
     anything from the file — prompt injection defence principle #6.

WHAT THIS FILE DOES NOT DO:
  - It does not decide which CSV column maps to which standard field.
    That's mapping_service.py (Step 1D).
  - It receives a DataFrame that already has the correct standard column
    names (date, product, revenue, etc.).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

# ── Date format strings we'll try, in order of preference ────────────────────
# We try the most specific/common formats first before falling back to
# dateutil's smart (but slower) parser.
_DATE_FORMATS = [
    "%Y-%m-%d",    # 2024-01-03  (ISO 8601 — the gold standard)
    "%d/%m/%Y",    # 03/01/2024  (Indian / European style)
    "%d-%m-%Y",    # 03-01-2024
    "%d-%b-%Y",    # 5-Jan-2024
    "%b %d %Y",    # Jan 4 2024
    "%B %d %Y",    # January 4 2024
    "%d %b %Y",    # 4 Jan 2024
    "%m/%d/%Y",    # 01/03/2024  (US style — lowest priority)
]


# ─────────────────────────────────────────────────────────────────────────────
# Return type
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CleaningResult:
    """
    Everything the caller needs to know about a cleaning run.

    FIELDS:
      clean_df         — The cleaned DataFrame, ready to store in the DB.
      raw_count        — Number of rows in the file BEFORE cleaning.
      clean_count      — Number of rows AFTER cleaning.
      duplicates_removed — How many duplicate rows were dropped.
      invalid_removed  — How many rows were dropped for bad/missing data.
      invalid_removed  — How many rows were dropped for bad/missing data.
      rejected_rows    — List of dicts, each with {"row": dict, "reason": str}.
      warnings         — Human-readable list of notes for the owner.

    USAGE:
      result = clean_dataframe(df, file_type="sales")
      if result.clean_count == 0:
          show_error("No valid rows found after cleaning.")
      else:
          store(result.clean_df)
          show_warning(result.warnings)
    """

    clean_df: pd.DataFrame
    raw_count: int
    clean_count: int
    raw_revenue: float
    clean_revenue: float
    duplicates_removed: int
    invalid_removed: int
    saved_with_warnings: int = 0
    rejected_rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if at least some rows survived cleaning."""
        return self.clean_count > 0

    def summary(self) -> str:
        """One-line human-readable summary for the owner."""
        parts = [f"{self.clean_count} valid rows loaded from {self.raw_count} in the file."]
        if self.duplicates_removed:
            parts.append(f"{self.duplicates_removed} duplicate rows removed.")
        if self.invalid_removed:
            parts.append(f"{self.invalid_removed} rows dropped (missing or invalid data).")
        return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: parse money values
# ─────────────────────────────────────────────────────────────────────────────
def _parse_money(value) -> Optional[float]:
    """
    Convert a messy money string to a float.

    Handles:
      "₹640"      →  640.0
      "₹1,200"    →  1200.0
      "₹25,000"   →  25000.0
      "320"       →  320.0
      1200        →  1200.0   (already numeric)
      ""          →  None
      "N/A"       →  None

    WHY NOT just pd.to_numeric()?
      pd.to_numeric() chokes on "₹640" and "₹1,200" because of the
      currency symbol and comma. We strip those first.
    """
    if pd.isna(value) or str(value).strip() == "":
        return None

    # Convert to string so we can use string methods
    s = str(value).strip()

    # Remove currency symbols and thousands-separator commas
    # re.sub replaces all characters matching the pattern with ""
    s = re.sub(r"[₹$€£,\s]", "", s)

    try:
        return float(s)
    except ValueError:
        logger.debug("Could not parse money value: %r", value)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: parse dates
# ─────────────────────────────────────────────────────────────────────────────
def _parse_date(value) -> Optional[date]:
    """
    Try to parse a date from messy string or existing date/datetime object.

    Strategy:
      1. If pandas already parsed it as a Timestamp, convert directly.
      2. Try each format in _DATE_FORMATS (fast, no ambiguity).
      3. Fall back to dateutil.parser (slower but handles "Jan 4 2024").

    Returns None if the value is empty or cannot be parsed by any method.

    WHY NOT just pd.to_datetime() on the whole column?
      pd.to_datetime(errors='coerce') silently turns bad values into NaT
      without telling us WHY. We want to count and log the failures.
    """
    if pd.isna(value) or str(value).strip() == "":
        return None

    # Already a proper date/datetime from pandas
    if isinstance(value, (pd.Timestamp, date)):
        if isinstance(value, pd.Timestamp):
            return value.date()
        return value

    s = str(value).strip()

    # Try each explicit format first (fast path)
    for fmt in _DATE_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt).date()
        except (ValueError, TypeError):
            continue

    # Fall back to dateutil's smart parser
    try:
        # dayfirst=True because Indian dates are DD/MM/YYYY, not MM/DD/YYYY
        return dateutil_parser.parse(s, dayfirst=True).date()
    except (ValueError, OverflowError):
        logger.debug("Could not parse date value: %r", value)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: normalise text (product names, categories)
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_text(value, title_case: bool = True) -> Optional[str]:
    """
    Clean up a text value: strip whitespace, collapse multiple spaces,
    optionally apply Title Case.

    Examples:
      "  butter  chicken "  →  "Butter Chicken"
      "BUTTER CHICKEN"      →  "Butter Chicken"
      "main course  "       →  "Main Course"
      ""                    →  None
      NaN                   →  None

    WHY TITLE CASE?
      "butter chicken" and "Butter Chicken" are the same product.
      Normalising to Title Case lets us group them correctly later.
      Without this, GROUP BY product would treat them as different items.
    """
    if pd.isna(value) or str(value).strip() == "":
        return None

    # Strip leading/trailing whitespace, collapse internal double-spaces
    s = " ".join(str(value).split())

    if title_case:
        s = s.title()

    return s if s else None


# ─────────────────────────────────────────────────────────────────────────────
# Category Normalisation (Synonyms & Plurals)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_SYNONYMS = {
    # Raw Material variants
    "raw material": "Raw Material",
    "raw materials": "Raw Material",
    "material": "Raw Material",
    "materials": "Raw Material",
    "ingredient": "Raw Material",
    "ingredients": "Raw Material",
    "raw food": "Raw Material",

    # Rent variants
    "rent": "Rent",
    "rents": "Rent",
    "office rent": "Rent",
    "shop rent": "Rent",
    "building rent": "Rent",

    # Salaries / Payroll
    "salary": "Salaries",
    "salaries": "Salaries",
    "payroll": "Salaries",
    "wage": "Salaries",
    "wages": "Salaries",
    "staff salary": "Salaries",
    "employee salary": "Salaries",

    # Utilities
    "utility": "Utilities",
    "utilities": "Utilities",
    "electricity": "Utilities",
    "water": "Utilities",
    "power": "Utilities",
    "internet": "Utilities",
    "wifi": "Utilities",
    "electric bill": "Utilities",

    # Marketing
    "marketing": "Marketing",
    "advertising": "Marketing",
    "advertisement": "Marketing",
    "ads": "Marketing",
    "promotions": "Marketing",
    "promotion": "Marketing",

    # Maintenance
    "maintenance": "Maintenance",
    "repair": "Maintenance",
    "repairs": "Maintenance",
    "upkeep": "Maintenance",

    # Supplies
    "supply": "Supplies",
    "supplies": "Supplies",
    "office supplies": "Supplies",
    "store supplies": "Supplies",

    # Logistics / Transport
    "transport": "Transport",
    "transportation": "Transport",
    "travel": "Transport",
    "logistics": "Transport",
    "delivery": "Transport",
    "shipping": "Transport",

    # Taxes
    "tax": "Taxes",
    "taxes": "Taxes",
    "gst": "Taxes",
    "vat": "Taxes",

    # Insurance
    "insurance": "Insurance",

    # Miscellaneous
    "misc": "Miscellaneous",
    "miscellaneous": "Miscellaneous",
    "other": "Miscellaneous",
    "others": "Miscellaneous",
    "general": "Miscellaneous",

    # Cash expense
    "cash expense": "Cash Expense",
    "cash expenses": "Cash Expense",
}


def normalize_category(val: Any) -> str:
    """
    Normalise expense and cash-book categories:
    - trim and collapse spaces
    - case-insensitive
    - simple plural handling (e.g. 'Raw Materials' -> 'Raw Material')
    - small synonym map
    Defaults missing or empty to 'Uncategorised'.
    """
    if pd.isna(val) or val is None:
        return "Uncategorised"
    s = " ".join(str(val).strip().split())
    if not s:
        return "Uncategorised"

    s_lower = s.lower()
    if s_lower in CATEGORY_SYNONYMS:
        return CATEGORY_SYNONYMS[s_lower]

    # Simple plural handling
    if s_lower.endswith("s") and not s_lower.endswith("ss"):
        cand = s_lower[:-1]
        if cand in CATEGORY_SYNONYMS:
            return CATEGORY_SYNONYMS[cand]
        words = s.split()
        if len(words) > 0 and words[-1].lower().endswith("s") and not words[-1].lower().endswith("ss"):
            words[-1] = words[-1][:-1]
        return " ".join(words).title()

    return s.title()


def _format_raw_dict(row: pd.Series) -> dict[str, str]:
    """Format raw row as dictionary of strings, keeping empty strings for missing/null values."""
    out = {}
    for k, v in row.items():
        if pd.isna(v) or v is None or str(v).strip().lower() in ("nan", "none", "null"):
            out[str(k)] = ""
        elif isinstance(v, float) and v.is_integer():
            out[str(k)] = str(int(v))
        else:
            out[str(k)] = str(v)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sales cleaning pipeline
# ─────────────────────────────────────────────────────────────────────────────
def clean_sales(df: pd.DataFrame) -> CleaningResult:
    """
    Clean a sales DataFrame that already has standard column names:
      date, order_id, product, category, quantity, unit_price, revenue

    Validation rules:
      - Reject rows with missing date (cell is empty) -> "Missing date"
      - Reject rows with invalid date (unparseable text) -> "Invalid date"
      - Reject rows with invalid revenue (text in numeric) -> "Revenue is not a number"
      - Reject rows with quantity <= 0 or revenue <= 0 -> "negative or zero quantity/revenue"
      - Missing product name: keep row, set "Unknown item", count as saved with warning
      - Raw rejected row stored as exact strings (no nulls, no parsed floats)
    """
    raw_count = len(df)
    warnings: list[str] = []
    rejected_rows: list[dict] = []
    clean_rows: list[dict] = []
    saved_with_warnings = 0
    raw_revenue = 0.0

    for idx, row in df.iterrows():
        raw_dict = _format_raw_dict(row)

        val_date = row.get("date")
        val_rev = row.get("revenue")
        val_qty = row.get("quantity")
        val_prod = row.get("product")
        val_cat = row.get("category")
        val_price = row.get("unit_price")
        val_oid = row.get("order_id")

        rejection_reason = None

        # 1. Date validation
        parsed_date = None
        if pd.isna(val_date) or str(val_date).strip() == "":
            rejection_reason = "Missing date"
        else:
            parsed_date = _parse_date(val_date)
            if parsed_date is None:
                rejection_reason = "Invalid date"

        # 2. Revenue validation
        parsed_rev = None
        if rejection_reason is None:
            if pd.isna(val_rev) or str(val_rev).strip() == "":
                rejection_reason = "Revenue is not a number"
            else:
                parsed_rev = _parse_money(val_rev)
                if parsed_rev is None:
                    rejection_reason = "Revenue is not a number"
                elif parsed_rev <= 0:
                    rejection_reason = "negative or zero quantity/revenue"

        # 3. Quantity validation
        parsed_qty = 1.0
        if rejection_reason is None:
            if val_qty is not None and not (pd.isna(val_qty) or str(val_qty).strip() == ""):
                try:
                    clean_q_str = str(val_qty).replace(",", "").strip()
                    parsed_qty = float(clean_q_str)
                    if parsed_qty <= 0:
                        rejection_reason = "negative or zero quantity/revenue"
                except (ValueError, TypeError):
                    rejection_reason = "negative or zero quantity/revenue"
            else:
                parsed_qty = 1.0

        if parsed_rev is not None and parsed_rev > 0:
            raw_revenue += parsed_rev

        if rejection_reason is not None:
            rejected_rows.append({
                "original_index": idx,
                "row": raw_dict,
                "reason": rejection_reason,
            })
            continue

        # Product name: missing -> store "Unknown item", count warning
        is_row_warned = False
        if pd.isna(val_prod) or str(val_prod).strip() == "":
            product = "Unknown item"
            is_row_warned = True
        else:
            product = _normalize_text(val_prod, title_case=True) or "Unknown item"

        # Category
        if val_cat is not None and not pd.isna(val_cat) and str(val_cat).strip():
            category = _normalize_text(val_cat, title_case=True) or "Uncategorised"
        else:
            category = "Uncategorised"

        unit_price = _parse_money(val_price) if val_price is not None else None
        order_id = str(val_oid).strip() if (val_oid is not None and pd.notna(val_oid) and str(val_oid).strip()) else None

        if is_row_warned:
            saved_with_warnings += 1

        clean_rows.append({
            "date": parsed_date,
            "order_id": order_id,
            "product": product,
            "category": category,
            "quantity": parsed_qty,
            "unit_price": unit_price,
            "revenue": float(parsed_rev),
        })

    clean_df = pd.DataFrame(clean_rows)
    if clean_df.empty:
        clean_df = pd.DataFrame(columns=["date", "order_id", "product", "category", "quantity", "unit_price", "revenue"])
    else:
        clean_df["revenue"] = clean_df["revenue"].astype(float)
        clean_df["quantity"] = clean_df["quantity"].astype(float)

    clean_count = len(clean_df)
    clean_revenue = float(clean_df["revenue"].sum()) if not clean_df.empty else 0.0
    invalid_removed = len(rejected_rows)

    if invalid_removed > 0:
        warnings.append(f"{invalid_removed} invalid row(s) skipped.")
    if saved_with_warnings > 0:
        warnings.append(f"{saved_with_warnings} row(s) saved with warnings.")

    return CleaningResult(
        clean_df=clean_df,
        raw_count=raw_count,
        clean_count=clean_count,
        raw_revenue=raw_revenue,
        clean_revenue=clean_revenue,
        duplicates_removed=0,
        invalid_removed=invalid_removed,
        saved_with_warnings=saved_with_warnings,
        rejected_rows=rejected_rows,
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Expenses cleaning pipeline
# ─────────────────────────────────────────────────────────────────────────────
def clean_expenses(df: pd.DataFrame) -> CleaningResult:
    """
    Clean an expenses DataFrame that already has standard column names:
      date, category, description, amount

    Validation rules:
      - Reject rows with missing date (cell is empty) -> "Missing date"
      - Reject rows with invalid date (unparseable text) -> "Invalid date"
      - Reject rows with invalid amount (text in numeric) -> "Amount is not a number"
      - Reject rows with amount <= 0 -> "negative or zero amount"
      - Missing category: save as "Uncategorised", count as saved with warning
      - Raw rejected row stored as exact strings (no nulls, no parsed floats)
    """
    raw_count = len(df)
    warnings: list[str] = []
    rejected_rows: list[dict] = []
    clean_rows: list[dict] = []
    saved_with_warnings = 0
    raw_revenue = 0.0

    for idx, row in df.iterrows():
        raw_dict = _format_raw_dict(row)

        val_date = row.get("date")
        val_amt = row.get("amount")
        val_cat = row.get("category")
        val_desc = row.get("description")

        rejection_reason = None

        # 1. Date validation
        parsed_date = None
        if pd.isna(val_date) or str(val_date).strip() == "":
            rejection_reason = "Missing date"
        else:
            parsed_date = _parse_date(val_date)
            if parsed_date is None:
                rejection_reason = "Invalid date"

        # 2. Amount validation
        parsed_amt = None
        if rejection_reason is None:
            if pd.isna(val_amt) or str(val_amt).strip() == "":
                rejection_reason = "Amount is not a number"
            else:
                parsed_amt = _parse_money(val_amt)
                if parsed_amt is None:
                    rejection_reason = "Amount is not a number"
                elif parsed_amt <= 0:
                    rejection_reason = "negative or zero amount"

        if parsed_amt is not None and parsed_amt > 0:
            raw_revenue += parsed_amt

        if rejection_reason is not None:
            rejected_rows.append({
                "original_index": idx,
                "row": raw_dict,
                "reason": rejection_reason,
            })
            continue

        # Category: missing -> save as "Uncategorised", count warning
        is_row_warned = False
        if pd.isna(val_cat) or str(val_cat).strip() == "":
            category = "Uncategorised"
            is_row_warned = True
        else:
            category = normalize_category(val_cat)
            if category == "Uncategorised":
                is_row_warned = True

        description = _normalize_text(val_desc, title_case=False) if (val_desc is not None and pd.notna(val_desc) and str(val_desc).strip()) else None

        if is_row_warned:
            saved_with_warnings += 1

        clean_rows.append({
            "date": parsed_date,
            "category": category,
            "description": description,
            "amount": float(parsed_amt),
        })

    clean_df = pd.DataFrame(clean_rows)
    if clean_df.empty:
        clean_df = pd.DataFrame(columns=["date", "category", "description", "amount"])
    else:
        clean_df["amount"] = clean_df["amount"].astype(float)

    clean_count = len(clean_df)
    clean_revenue = float(clean_df["amount"].sum()) if not clean_df.empty else 0.0
    invalid_removed = len(rejected_rows)

    if invalid_removed > 0:
        warnings.append(f"{invalid_removed} invalid row(s) skipped.")
    if saved_with_warnings > 0:
        warnings.append(f"{saved_with_warnings} row(s) saved with warnings.")

    return CleaningResult(
        clean_df=clean_df,
        raw_count=raw_count,
        clean_count=clean_count,
        raw_revenue=raw_revenue,
        clean_revenue=clean_revenue,
        duplicates_removed=0,
        invalid_removed=invalid_removed,
        saved_with_warnings=saved_with_warnings,
        rejected_rows=rejected_rows,
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def clean_dataframe(df: pd.DataFrame, file_type: str) -> CleaningResult:
    """
    Route a raw DataFrame to the correct cleaner based on file_type.

    This is the ONLY function that upload_service.py (and tests) should call.
    Keeping a single entry point makes it easy to add new file types later.

    Args:
        df:        Raw DataFrame with standard column names already applied.
        file_type: "sales" or "expenses"

    Returns:
        CleaningResult

    Raises:
        ValueError: If file_type is not "sales" or "expenses".
    """
    file_type = file_type.strip().lower()
    if file_type == "sales":
        return clean_sales(df)
    elif file_type == "expenses":
        return clean_expenses(df)
    else:
        raise ValueError(
            f"Unknown file_type {file_type!r}. Expected 'sales' or 'expenses'."
        )
