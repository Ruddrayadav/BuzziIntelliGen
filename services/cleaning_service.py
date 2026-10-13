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
from typing import Optional

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
# Sales cleaning pipeline
# ─────────────────────────────────────────────────────────────────────────────
def clean_sales(df: pd.DataFrame) -> CleaningResult:
    """
    Clean a sales DataFrame that already has standard column names:
      date, order_id, product, category, quantity, unit_price, revenue

    Steps (in order):
      1. Work on a copy — never mutate the caller's DataFrame.
      2. Apply _parse_money to revenue and unit_price.
      3. Apply _parse_date to date.
      4. Normalize product and category text.
      5. Drop rows where revenue is missing/zero (they're useless for analysis).
      6. Drop rows where date is missing (can't place them on a timeline).
      7. Deduplicate on (date, product, revenue).
      8. Reset index and return CleaningResult.

    Args:
        df: Raw DataFrame with standard sales column names.

    Returns:
        CleaningResult with the cleaned DataFrame and a report.
    """
    raw_count = len(df)
    warnings: list[str] = []
    rejected_rows: list[dict] = []

    # Step 1: Work on a copy
    df = df.copy()

    # Step 2: Parse money columns
    # Apply our helper to every cell in these columns.
    # `.apply()` calls the function once per cell.
    df["revenue"] = df["revenue"].apply(_parse_money)
    df["unit_price"] = df["unit_price"].apply(_parse_money) if "unit_price" in df.columns else None
    df["quantity"] = pd.to_numeric(df.get("quantity"), errors="coerce")

    # Step 3: Parse dates
    df["date"] = df["date"].apply(_parse_date)

    # Step 4: Normalize text
    df["product"] = df["product"].apply(_normalize_text)
    df["category"] = df["category"].apply(lambda v: _normalize_text(v, title_case=True))
    if "order_id" in df.columns:
        df["order_id"] = df["order_id"].apply(
            lambda v: str(v).strip() if pd.notna(v) and str(v).strip() else None
        )

    # Step 5: Fill missing descriptive metadata
    df["product"] = df["product"].fillna("Unknown")
    df["category"] = df["category"].fillna("Uncategorized")

    # Compute raw revenue before dropping anything
    raw_revenue = float(df["revenue"].fillna(0).sum())

    # Step 6: Drop rows with missing financial data (revenue or date)
    # We find specific reasons instead of a generic one
    invalid_mask = df["revenue"].isna() | df["date"].isna()
    if invalid_mask.any():
        dropped = df[invalid_mask]
        for idx, row in dropped.iterrows():
            reasons = []
            if pd.isna(row["date"]):
                reasons.append("Missing date")
            if pd.isna(row["revenue"]):
                reasons.append("Missing revenue")
            
            reason_str = " and ".join(reasons)
            rejected_rows.append({
                "original_index": idx,
                "row": row.to_dict(), 
                "reason": f"❌ {reason_str}"
            })
        df = df[~invalid_mask]
        invalid_removed = len(dropped)
        warnings.append(
            f"{invalid_removed} row(s) dropped: missing revenue or date."
        )
    else:
        invalid_removed = 0

    # Also drop rows where revenue == 0 (meaningless for analysis)
    zero_mask = df["revenue"] == 0
    if zero_mask.any():
        dropped = df[zero_mask]
        for idx, row in dropped.iterrows():
            rejected_rows.append({
                "original_index": idx,
                "row": row.to_dict(), 
                "reason": "❌ Revenue is zero"
            })
        df = df[~zero_mask]
        warnings.append(f"{len(dropped)} row(s) dropped: revenue was zero.")
        invalid_removed += len(dropped)

    # Deduplication removed: Identical rows (e.g. 2 identical sales on the same day) are perfectly valid.
    duplicates_removed = 0

    # Step 8: Ensure correct column dtypes and reset index
    df["revenue"] = df["revenue"].astype(float)
    clean_revenue = float(df["revenue"].sum())
    df = df.reset_index(drop=True)

    logger.info(
        "Sales cleaning complete: raw=%d, clean=%d, dupes=%d, invalid=%d",
        raw_count, len(df), duplicates_removed, invalid_removed,
    )

    return CleaningResult(
        clean_df=df,
        raw_count=raw_count,
        clean_count=len(df),
        raw_revenue=raw_revenue,
        clean_revenue=clean_revenue,
        duplicates_removed=duplicates_removed,
        invalid_removed=invalid_removed,
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

    Same pipeline as clean_sales but simpler (no product/qty/unit_price).
    Deduplication key: (date, category, amount).

    Args:
        df: Raw DataFrame with standard expenses column names.

    Returns:
        CleaningResult with the cleaned DataFrame and a report.
    """
    raw_count = len(df)
    warnings: list[str] = []
    rejected_rows: list[dict] = []

    df = df.copy()

    # Parse money and dates
    df["amount"] = df["amount"].apply(_parse_money)
    df["date"] = df["date"].apply(_parse_date)

    # Normalize text
    df["category"] = df["category"].apply(lambda v: _normalize_text(v, title_case=True))
    df["description"] = df["description"].apply(lambda v: _normalize_text(v, title_case=False))

    # Fill missing category
    df["category"] = df["category"].fillna("Uncategorized")

    # Compute raw revenue before dropping
    raw_revenue = float(df["amount"].fillna(0).sum())

    # Drop rows missing amount or date
    invalid_mask = df["amount"].isna() | df["date"].isna()
    if invalid_mask.any():
        dropped = df[invalid_mask]
        for idx, row in dropped.iterrows():
            reasons = []
            if pd.isna(row["date"]):
                reasons.append("Missing date")
            if pd.isna(row["amount"]):
                reasons.append("Missing amount")
            
            reason_str = " and ".join(reasons)
            rejected_rows.append({
                "original_index": idx,
                "row": row.to_dict(), 
                "reason": f"❌ {reason_str}"
            })
        df = df[~invalid_mask]
        invalid_removed = len(dropped)
        warnings.append(
            f"{invalid_removed} row(s) dropped: missing amount or date."
        )
    else:
        invalid_removed = 0

    # Drop zero-amount rows
    zero_mask = df["amount"] == 0
    if zero_mask.any():
        dropped = df[zero_mask]
        for idx, row in dropped.iterrows():
            rejected_rows.append({
                "original_index": idx,
                "row": row.to_dict(), 
                "reason": "❌ Amount is zero"
            })
        df = df[~zero_mask]
        warnings.append(f"{len(dropped)} row(s) dropped: amount was zero.")
        invalid_removed += len(dropped)

    # Deduplication removed: Identical expenses (e.g. 2 identical LPG cylinders bought) are valid.
    duplicates_removed = 0

    df["amount"] = df["amount"].astype(float)
    clean_revenue = float(df["amount"].sum())
    df = df.reset_index(drop=True)

    logger.info(
        "Expenses cleaning complete: raw=%d, clean=%d, dupes=%d, invalid=%d",
        raw_count, len(df), duplicates_removed, invalid_removed,
    )

    return CleaningResult(
        clean_df=df,
        raw_count=raw_count,
        clean_count=len(df),
        raw_revenue=raw_revenue,
        clean_revenue=clean_revenue,
        duplicates_removed=duplicates_removed,
        invalid_removed=invalid_removed,
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
