"""
services/upload_service.py
---------------------------
Coordinator for the file upload pipeline.

THIS FILE'S ONE JOB:
  Glue together file reading, column mapping, cleaning, and DB storage.
  It calls the other services — it doesn't duplicate their logic.

TWO-PHASE DESIGN (important):
  Phase A — suggest_mapping_from_file()
    Reads the file and suggests a column mapping. Returns an UploadPreview.
    Does NOT touch the database. Safe to call multiple times.

  Phase B — execute_upload()
    Applies the user-confirmed mapping, cleans the data, and saves to DB.
    Only called after the owner has approved the mapping in the UI.

UI RULE:
  Streamlit will call these two functions and display the results.
  No Pandas or SQL lives in the Streamlit file — just calls to these
  functions and rendering of the returned objects.

WHAT THIS FILE DOES NOT DO:
  - It does not contain prompt text (that's llm.py and ai_service.py later).
  - It does not render UI elements.
  - It does not decide how to clean data (that's cleaning_service.py).
  - It does not decide how to map columns (that's mapping_service.py).
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings
from db.database import get_db, init_db
from db.models import Expenses, Sales, UploadLog, RejectedRow
from services.cleaning_service import CleaningResult, clean_dataframe, _parse_money
from services.mapping_service import (
    ColumnMapping,
    apply_mapping,
    suggest_mapping,
    validate_confirmed_mapping,
)
from api.detector import _has_word

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Return types
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class UploadPreview:
    """
    Returned by Phase A (suggest_mapping_from_file).

    Contains everything the UI needs to show the owner a preview and
    let them confirm or correct the column mapping. Does NOT contain
    a database ID — nothing has been saved yet.

    FIELDS:
      raw_df          — Full raw DataFrame (all original columns, no changes).
      filename        — Original filename for display.
      file_type       — "sales" or "expenses" or "cashbook"
      suggested       — ColumnMapping with rule/LLM suggestions.
      sample_rows     — First 5 rows of the raw DataFrame for preview table.
      raw_row_count   — Total rows in the uploaded file.
    """

    raw_df: pd.DataFrame
    filename: str
    file_type: str
    suggested: ColumnMapping
    raw_row_count: int
    is_cashbook: bool = False
    cashbook_summary: Optional[dict] = None

    @property
    def sample_rows(self) -> pd.DataFrame:
        """First 5 rows — shown to owner so they can see what the file looks like."""
        return self.raw_df.head(5)

    @property
    def column_names(self) -> list[str]:
        return self.raw_df.columns.tolist()


@dataclass
class CashbookSplitResult:
    """Holds partitioned sales and expense DataFrames produced from a cash-book file."""
    sales_df: pd.DataFrame
    expenses_df: pd.DataFrame
    sales_count: int
    expenses_count: int
    sales_total: float
    expenses_total: float
    split_column: str
    split_method: str  # "debit_credit" | "type_column" | "amount_sign"
    summary_message: str

    def to_dict(self) -> dict:
        return {
            "sales_count": self.sales_count,
            "expenses_count": self.expenses_count,
            "sales_total": self.sales_total,
            "expenses_total": self.expenses_total,
            "split_column": self.split_column,
            "split_method": self.split_method,
            "message": self.summary_message,
        }


@dataclass
class UploadResult:
    """
    Returned by Phase B (execute_upload) after data is saved to the database.

    FIELDS:
      success          — True if at least some rows were saved.
      upload_log_id    — The ID of the UploadLog row in the database.
                         Use this to query the saved data later.
      filename         — Original filename.
      file_type        — "sales", "expenses", or "cashbook"
      raw_count        — Rows in the original file.
      clean_count      — Rows actually saved to the database.
      duplicates_removed — Rows removed as duplicates.
      invalid_removed  — Rows removed due to missing/invalid data.
      warnings         — Human-readable notes for the owner.
      error_message    — Set if success=False. Never show a stack trace.
    """

    success: bool
    upload_log_id: Optional[int]
    filename: str
    file_type: str
    raw_count: int
    clean_count: int
    raw_revenue: float
    clean_revenue: float
    duplicates_removed: int
    invalid_removed: int
    rejected_rows_detailed: list[dict] = field(default_factory=list)
    rejected_rows_with_revenue_count: int = 0
    rejected_revenue_excluded: float = 0.0
    warnings: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    is_duplicate: bool = False
    existing_upload_id: Optional[int] = None
    is_cashbook: bool = False
    cashbook_summary: Optional[str] = None
    sales_upload_id: Optional[int] = None
    expenses_upload_id: Optional[int] = None

    def summary(self) -> str:
        """One-line plain-language summary for the owner."""
        if not self.success:
            return f"Upload failed: {self.error_message}"
        if self.is_cashbook and self.cashbook_summary:
            return f"✅ Cash-book imported: {self.cashbook_summary}"
        parts = [f"✅ {self.clean_count} rows saved from '{self.filename}'."]
        if self.duplicates_removed:
            parts.append(f"{self.duplicates_removed} duplicates removed.")
        if self.invalid_removed:
            parts.append(f"{self.invalid_removed} invalid rows skipped.")
        return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# File validation
# ─────────────────────────────────────────────────────────────────────────────
def validate_file(file_bytes: bytes, filename: str) -> None:
    """
    Check that the uploaded file is safe to process.

    Checks:
      1. File size is within the configured limit.
      2. File extension is in the allowed list.

    Raises:
        ValueError: With a friendly human-readable message (safe to show the owner).

    WHY VALIDATE BEFORE READING?
      Reading a 500 MB file with pd.read_csv() will crash the server.
      We check size first using just len(file_bytes) — O(1) and safe.
    """
    size_mb = len(file_bytes) / (1024 * 1024)
    max_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)

    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(
            f"File is too large ({size_mb:.1f} MB). Maximum allowed is {max_mb:.0f} MB."
        )

    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type '{ext}' is not supported. "
            f"Please upload a {', '.join(settings.ALLOWED_EXTENSIONS)} file."
        )

    logger.info("File validation passed: %s (%.2f MB)", filename, size_mb)


# ─────────────────────────────────────────────────────────────────────────────
# File reading
# ─────────────────────────────────────────────────────────────────────────────
def read_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Read a CSV or Excel file from bytes into a Pandas DataFrame.

    WHY BYTES AND NOT A FILE PATH?
      Streamlit gives us an uploaded file object (BytesIO), not a path.
      FastAPI will give us bytes from a multipart form upload.
      Using bytes makes this function work with both frontends.

    Args:
        file_bytes: Raw file content as bytes.
        filename:   Original filename — used to decide the format.

    Returns:
        Raw DataFrame with all original columns. No cleaning yet.

    Raises:
        ValueError: If the file cannot be parsed.
    """
    ext = Path(filename).suffix.lower()
    buffer = io.BytesIO(file_bytes)

    try:
        if ext == ".csv":
            # Try UTF-8 first; fall back to latin-1 for files from Indian software
            try:
                df = pd.read_csv(buffer, encoding="utf-8")
            except UnicodeDecodeError:
                buffer.seek(0)
                df = pd.read_csv(buffer, encoding="latin-1")
                logger.warning("File %s read with latin-1 encoding fallback", filename)

        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(buffer, engine="openpyxl" if ext == ".xlsx" else "xlrd")

        else:
            raise ValueError(f"Unsupported extension: {ext}")

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(
            f"Could not read '{filename}'. Is it a valid {ext} file? "
            f"Detail: {exc}"
        ) from exc

    if df.empty:
        raise ValueError(f"'{filename}' appears to be empty — no rows found.")

    logger.info("File read: %s — %d rows, %d columns", filename, len(df), len(df.columns))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Cash-book Splitting
# ─────────────────────────────────────────────────────────────────────────────
def split_cashbook(raw_df: pd.DataFrame) -> CashbookSplitResult:
    """
    Split a combined cash-book DataFrame into separate sales and expenses DataFrames.

    Supports three common small-business accounting formats:
      1. Dual Debit / Credit columns:
         - Credit / Inflow rows -> Sales (revenue = Credit)
         - Debit / Outflow rows -> Expenses (amount = Debit)
      2. Single Amount + Type column:
         - Type matching Inflow (Sale, Credit, Income, Receipt) -> Sales
         - Type matching Outflow (Expense, Debit, Purchase, Payment) -> Expenses
      3. Single Amount with positive/negative signs:
         - Positive (> 0) -> Sales
         - Negative (< 0) -> Expenses (amount = abs(val))

    Returns:
        CashbookSplitResult containing sales_df, expenses_df, counts, totals, and a summary message.
    """
    if raw_df.empty:
        return CashbookSplitResult(
            sales_df=pd.DataFrame(columns=["date", "product", "revenue"]),
            expenses_df=pd.DataFrame(columns=["date", "category", "amount"]),
            sales_count=0,
            expenses_count=0,
            sales_total=0.0,
            expenses_total=0.0,
            split_column="none",
            split_method="empty",
            summary_message="Empty cash-book file.",
        )

    col_names = raw_df.columns.tolist()
    col_lower = {c: str(c).strip().lower().replace("_", " ").replace("-", " ") for c in col_names}

    # 1. Identify Date column
    date_col = None
    for c in col_names:
        cl = col_lower[c]
        if any(_has_word(cl, kw) for kw in ("date", "txn date", "transaction date", "entry date", "day")):
            date_col = c
            break
    if not date_col:
        date_col = col_names[0]

    # 2. Identify Description / Particulars column
    desc_col = None
    for c in col_names:
        if c == date_col:
            continue
        cl = col_lower[c]
        if any(_has_word(cl, kw) for kw in ("description", "particulars", "particular", "details", "narration", "memo", "remarks", "party", "payee", "item", "name")):
            desc_col = c
            break
    if not desc_col:
        for c in col_names:
            if c != date_col and (pd.api.types.is_string_dtype(raw_df[c]) or pd.api.types.is_object_dtype(raw_df[c])):
                desc_col = c
                break
    if not desc_col:
        desc_col = date_col

    # 3. Strategy A: Check for Debit and Credit columns
    debit_col = None
    credit_col = None
    for c in col_names:
        cl = col_lower[c]
        if any(_has_word(cl, kw) for kw in ("debit", "dr", "paid", "withdrawal", "money out", "cash out", "outflow", "expense")):
            debit_col = c
        if any(_has_word(cl, kw) for kw in ("credit", "cr", "received", "deposit", "money in", "cash in", "inflow", "receipt")):
            credit_col = c

    if debit_col and credit_col:
        dr_vals = raw_df[debit_col].apply(_parse_money).fillna(0.0)
        cr_vals = raw_df[credit_col].apply(_parse_money).fillna(0.0)
        sales_mask = cr_vals > 0
        exp_mask = dr_vals > 0

        sales_df = pd.DataFrame({
            "date": raw_df.loc[sales_mask, date_col],
            "product": raw_df.loc[sales_mask, desc_col].fillna("Cash Sale").astype(str),
            "revenue": cr_vals.loc[sales_mask],
        })
        expenses_df = pd.DataFrame({
            "date": raw_df.loc[exp_mask, date_col],
            "category": raw_df.loc[exp_mask, desc_col].fillna("Cash Expense").astype(str),
            "amount": dr_vals.loc[exp_mask],
            "description": raw_df.loc[exp_mask, desc_col].fillna("Cash Expense").astype(str),
        })

        sales_cnt = len(sales_df)
        exp_cnt = len(expenses_df)
        sales_tot = round(float(sales_df["revenue"].sum()), 2) if sales_cnt > 0 else 0.0
        exp_tot = round(float(expenses_df["amount"].sum()), 2) if exp_cnt > 0 else 0.0
        msg = f"Split into {sales_cnt} sales transactions (₹{sales_tot:,.2f}) and {exp_cnt} expense entries (₹{exp_tot:,.2f}) by '{debit_col} / {credit_col}'."

        return CashbookSplitResult(
            sales_df=sales_df,
            expenses_df=expenses_df,
            sales_count=sales_cnt,
            expenses_count=exp_cnt,
            sales_total=sales_tot,
            expenses_total=exp_tot,
            split_column=f"{debit_col} / {credit_col}",
            split_method="debit_credit",
            summary_message=msg,
        )

    # 4. Strategy B: Check for Type column + Amount column
    type_col = None
    amt_col = None
    for c in col_names:
        cl = col_lower[c]
        if any(_has_word(cl, kw) for kw in ("type", "txn type", "transaction type", "entry type", "dr cr", "cr dr", "d c")):
            type_col = c
        if any(_has_word(cl, kw) for kw in ("amount", "total", "value", "net", "rs", "inr")):
            amt_col = c

    if type_col and amt_col:
        amt_vals = raw_df[amt_col].apply(_parse_money).fillna(0.0).abs()
        type_str = raw_df[type_col].astype(str).str.strip().str.lower()
        sales_mask = type_str.apply(lambda s: any(_has_word(s, kw) for kw in ("sale", "sales", "credit", "cr", "income", "receipt", "in", "deposit"))) & (amt_vals > 0)
        exp_mask = type_str.apply(lambda s: any(_has_word(s, kw) for kw in ("expense", "expenses", "debit", "dr", "payment", "purchase", "out", "withdrawal"))) & (amt_vals > 0)

        sales_df = pd.DataFrame({
            "date": raw_df.loc[sales_mask, date_col],
            "product": raw_df.loc[sales_mask, desc_col].fillna("Cash Sale").astype(str),
            "revenue": amt_vals.loc[sales_mask],
        })
        expenses_df = pd.DataFrame({
            "date": raw_df.loc[exp_mask, date_col],
            "category": raw_df.loc[exp_mask, desc_col].fillna("Cash Expense").astype(str),
            "amount": amt_vals.loc[exp_mask],
            "description": raw_df.loc[exp_mask, desc_col].fillna("Cash Expense").astype(str),
        })

        sales_cnt = len(sales_df)
        exp_cnt = len(expenses_df)
        sales_tot = round(float(sales_df["revenue"].sum()), 2) if sales_cnt > 0 else 0.0
        exp_tot = round(float(expenses_df["amount"].sum()), 2) if exp_cnt > 0 else 0.0
        msg = f"Split into {sales_cnt} sales transactions (₹{sales_tot:,.2f}) and {exp_cnt} expense entries (₹{exp_tot:,.2f}) by '{type_col}'."

        return CashbookSplitResult(
            sales_df=sales_df,
            expenses_df=expenses_df,
            sales_count=sales_cnt,
            expenses_count=exp_cnt,
            sales_total=sales_tot,
            expenses_total=exp_tot,
            split_column=type_col,
            split_method="type_column",
            summary_message=msg,
        )

    # 5. Strategy C: Check for signed Amount column (positive vs negative)
    if amt_col:
        signed_vals = raw_df[amt_col].apply(_parse_money).fillna(0.0)
        if (signed_vals > 0).any() and (signed_vals < 0).any():
            sales_mask = signed_vals > 0
            exp_mask = signed_vals < 0

            sales_df = pd.DataFrame({
                "date": raw_df.loc[sales_mask, date_col],
                "product": raw_df.loc[sales_mask, desc_col].fillna("Cash Sale").astype(str),
                "revenue": signed_vals.loc[sales_mask],
            })
            expenses_df = pd.DataFrame({
                "date": raw_df.loc[exp_mask, date_col],
                "category": raw_df.loc[exp_mask, desc_col].fillna("Cash Expense").astype(str),
                "amount": signed_vals.loc[exp_mask].abs(),
                "description": raw_df.loc[exp_mask, desc_col].fillna("Cash Expense").astype(str),
            })

            sales_cnt = len(sales_df)
            exp_cnt = len(expenses_df)
            sales_tot = round(float(sales_df["revenue"].sum()), 2) if sales_cnt > 0 else 0.0
            exp_tot = round(float(expenses_df["amount"].sum()), 2) if exp_cnt > 0 else 0.0
            msg = f"Split into {sales_cnt} sales transactions (₹{sales_tot:,.2f}) and {exp_cnt} expense entries (₹{exp_tot:,.2f}) by '{amt_col}' sign."

            return CashbookSplitResult(
                sales_df=sales_df,
                expenses_df=expenses_df,
                sales_count=sales_cnt,
                expenses_count=exp_cnt,
                sales_total=sales_tot,
                expenses_total=exp_tot,
                split_column=amt_col,
                split_method="amount_sign",
                summary_message=msg,
            )

    return CashbookSplitResult(
        sales_df=pd.DataFrame(columns=["date", "product", "revenue"]),
        expenses_df=pd.DataFrame(columns=["date", "category", "amount"]),
        sales_count=0,
        expenses_count=0,
        sales_total=0.0,
        expenses_total=0.0,
        split_column="none",
        split_method="unrecognized",
        summary_message="Could not find debit/credit columns or type column to split cash-book.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase A — Suggest mapping (no DB write)
# ─────────────────────────────────────────────────────────────────────────────
def suggest_mapping_from_file(
    file_bytes: bytes,
    filename: str,
    file_type: str,
    use_llm: bool = True,
) -> UploadPreview:
    """
    Phase A of the upload: read the file and suggest a column mapping.

    This function is SAFE TO CALL MULTIPLE TIMES — it never writes to
    the database. The owner can re-upload or change the file_type without
    worrying about partial data in the database.

    Args:
        file_bytes: Raw file bytes from the upload widget.
        filename:   Original filename (used for format detection + display).
        file_type:  "sales", "expenses", or "cashbook"
        use_llm:    Whether to use the LLM for ambiguous column names.
                    Set to False in tests or when Ollama is offline.

    Returns:
        UploadPreview with the raw DataFrame and suggested column mapping.

    Raises:
        ValueError: If the file is invalid or cannot be read.
    """
    # Validate before reading (cheap check first)
    validate_file(file_bytes, filename)

    # Read the file into a DataFrame
    raw_df = read_file(file_bytes, filename)

    # If cash-book, split into sales and expenses preview
    if file_type == "cashbook":
        split_res = split_cashbook(raw_df)
        mapping = ColumnMapping(
            file_type="cashbook",
            suggested={},
            method={},
        )
        return UploadPreview(
            raw_df=raw_df,
            filename=filename,
            file_type="cashbook",
            suggested=mapping,
            raw_row_count=len(raw_df),
            is_cashbook=True,
            cashbook_summary=split_res.to_dict(),
        )

    # Suggest mapping (rules + optional LLM)
    mapping = suggest_mapping(
        columns=raw_df.columns.tolist(),
        file_type=file_type,
        use_llm=use_llm,
    )

    logger.info(
        "Mapping suggested for %s (%s): complete=%s, missing=%s",
        filename, file_type, mapping.is_complete, mapping.missing_required,
    )

    return UploadPreview(
        raw_df=raw_df,
        filename=filename,
        file_type=file_type,
        suggested=mapping,
        raw_row_count=len(raw_df),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal: DB row builders
# ─────────────────────────────────────────────────────────────────────────────
def _nan_to_none(value):
    """
    Convert NaN or NaT to Python None for safe DB insertion.

    WHY THIS EXISTS:
      SQLAlchemy handles None correctly as SQL NULL. But if we pass
      float('nan') to a Float column, some DB drivers raise errors.
      This is a tiny helper that makes all nullable columns safe.
    """
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _build_sales_rows(
    clean_df: pd.DataFrame,
    tenant_id: str,
    upload_id: int,
) -> list[Sales]:
    """
    Convert a cleaned sales DataFrame into a list of Sales ORM objects.

    We build the full list in memory first, then insert all at once
    (bulk insert is much faster than inserting row-by-row in a loop).
    """
    rows = []
    for _, row in clean_df.iterrows():
        rows.append(
            Sales(
                tenant_id=tenant_id,
                upload_id=upload_id,
                date=row["date"],
                order_id=_nan_to_none(row.get("order_id")),
                product=row["product"],
                category=_nan_to_none(row.get("category")),
                quantity=_nan_to_none(row.get("quantity")),
                unit_price=_nan_to_none(row.get("unit_price")),
                revenue=float(row["revenue"]),
            )
        )
    return rows


def _build_expense_rows(
    clean_df: pd.DataFrame,
    tenant_id: str,
    upload_id: int,
) -> list[Expenses]:
    """Convert a cleaned expenses DataFrame into Expenses ORM objects."""
    rows = []
    for _, row in clean_df.iterrows():
        rows.append(
            Expenses(
                tenant_id=tenant_id,
                upload_id=upload_id,
                date=row["date"],
                category=row["category"],
                description=_nan_to_none(row.get("description")),
                amount=float(row["amount"]),
            )
        )
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Phase B — Execute upload (DB write)
# ─────────────────────────────────────────────────────────────────────────────
def execute_upload(
    raw_df: pd.DataFrame,
    confirmed_mapping: dict[str, str],
    file_type: str,
    filename: str,
    tenant_id: str,
    file_hash: Optional[str] = None,
    replace_existing: bool = False,
) -> UploadResult:
    """
    Phase B of the upload: apply mapping, clean, and save to the database.

    This is called AFTER the owner has reviewed and confirmed the column
    mapping in the UI. It is the ONLY function that writes to the database
    during the upload flow.

    Steps:
      0. Validate confirmed mapping server-side (required fields, no duplicates).
      0.5 Check file_hash duplicate for this tenant; reject (409) or replace old import.
      1. Apply confirmed_mapping to raw_df → standard column names.
      2. Run cleaning pipeline → CleaningResult.
      3. If zero clean rows remain → return failure (don't write to DB).
      4. Create UploadLog record (with file_hash).
      5. Bulk-insert Sales or Expenses rows linked to that UploadLog.
      6. Commit everything atomically (all or nothing).
      7. Return UploadResult.
    """
    # Ensure DB tables exist (idempotent — safe to call every time)
    init_db()

    raw_count = len(raw_df)

    # ── Step 0.5: Duplicate detection via file_hash ───────────────────────────
    if file_hash:
        with get_db() as db:
            existing = (
                db.query(UploadLog)
                .filter(UploadLog.tenant_id == tenant_id, UploadLog.file_hash == file_hash)
                .first()
            )
            if existing and not replace_existing:
                return UploadResult(
                    success=False,
                    upload_log_id=None,
                    filename=filename,
                    file_type=file_type,
                    raw_count=raw_count,
                    clean_count=0,
                    raw_revenue=0.0,
                    clean_revenue=0.0,
                    duplicates_removed=0,
                    invalid_removed=0,
                    is_duplicate=True,
                    existing_upload_id=existing.id,
                    error_message=(
                        f"This file has already been imported on {existing.uploaded_at.strftime('%d %b %Y')} "
                        f"as '{existing.filename}'. You can skip it or replace the previous import."
                    ),
                )

    try:
        # ── Step 0: Validate confirmed mapping server-side ────────────────────
        validate_confirmed_mapping(confirmed_mapping, file_type, raw_df.columns.tolist())

        # ── Step 1: Apply confirmed mapping ──────────────────────────────────
        standard_df = apply_mapping(raw_df, confirmed_mapping)
        logger.info(
            "Mapping applied for %s: columns → %s",
            filename, standard_df.columns.tolist()
        )

        # ── Step 2: Clean ─────────────────────────────────────────────────────
        clean_result: CleaningResult = clean_dataframe(standard_df, file_type)
        logger.info(
            "Cleaning done for %s: raw=%d clean=%d dupes=%d invalid=%d",
            filename,
            clean_result.raw_count,
            clean_result.clean_count,
            clean_result.duplicates_removed,
            clean_result.invalid_removed,
        )

        # ── Step 2.5: Process rejected rows for UI & DB ──────────────────────
        rejected_detailed = []
        rejected_with_revenue = 0
        rejected_rev_total = 0.0
        
        for r in clean_result.rejected_rows:
            idx = r.get("original_index")
            if idx is not None and idx in raw_df.index:
                orig_row_dict = raw_df.loc[idx].to_dict()
            else:
                orig_row_dict = r["row"]
            
            # Check if it had valid revenue despite being rejected
            rev_val = r["row"].get("revenue") or r["row"].get("amount")
            if pd.notna(rev_val):
                try:
                    f_val = float(rev_val)
                    if f_val > 0:
                        rejected_with_revenue += 1
                        rejected_rev_total += f_val
                except (ValueError, TypeError):
                    pass

            rejected_detailed.append({
                "original_index": idx if idx is not None else -1,
                "original_row": orig_row_dict,
                "reason": r["reason"]
            })

        # ── Step 3: Guard — nothing to save ──────────────────────────────────
        if clean_result.clean_count == 0:
            return UploadResult(
                success=False,
                upload_log_id=None,
                filename=filename,
                file_type=file_type,
                raw_count=raw_count,
                clean_count=0,
                raw_revenue=clean_result.raw_revenue,
                clean_revenue=0.0,
                duplicates_removed=clean_result.duplicates_removed,
                invalid_removed=clean_result.invalid_removed,
                rejected_rows_detailed=rejected_detailed,
                rejected_rows_with_revenue_count=rejected_with_revenue,
                rejected_revenue_excluded=rejected_rev_total,
                warnings=clean_result.warnings,
                error_message=(
                    "No valid rows remained after cleaning. "
                    "Please check your file and try again."
                ),
            )

        # ── Steps 4-6: Write to DB atomically ────────────────────────────────
        with get_db() as db:
            # If replacing an existing upload, remove previous UploadLog and cascaded rows
            if file_hash and replace_existing:
                old_logs = (
                    db.query(UploadLog)
                    .filter(UploadLog.tenant_id == tenant_id, UploadLog.file_hash == file_hash)
                    .all()
                )
                for old_log in old_logs:
                    db.delete(old_log)
                db.flush()

            # Create the UploadLog record
            upload_log = UploadLog(
                tenant_id=tenant_id,
                filename=filename,
                file_type=file_type,
                file_hash=file_hash,
                row_count_raw=raw_count,
                row_count_clean=clean_result.clean_count,
                status="success" if not clean_result.warnings else "partial",
                notes="; ".join(clean_result.warnings) if clean_result.warnings else None,
            )
            db.add(upload_log)


            # db.flush() runs the INSERT and populates upload_log.id WITHOUT
            # committing. We need the ID to link Sales/Expenses rows to this log.
            db.flush()

            # Build and insert the data rows
            if file_type == "sales":
                data_rows = _build_sales_rows(
                    clean_result.clean_df, tenant_id, upload_log.id
                )
            else:
                data_rows = _build_expense_rows(
                    clean_result.clean_df, tenant_id, upload_log.id
                )

            db.add_all(data_rows)

            if rejected_detailed:
                import json
                for rd in rejected_detailed:
                    db.add(RejectedRow(
                        tenant_id=tenant_id,
                        upload_id=upload_log.id,
                        row_data=json.dumps(rd["original_row"], default=str),
                        reason=rd["reason"]
                    ))

            # get_db() context manager calls db.commit() on __exit__
            upload_log_id = upload_log.id

        logger.info(
            "Upload committed: upload_log_id=%d, %d rows saved for tenant=%s",
            upload_log_id, clean_result.clean_count, tenant_id,
        )

        return UploadResult(
            success=True,
            upload_log_id=upload_log_id,
            filename=filename,
            file_type=file_type,
            raw_count=raw_count,
            clean_count=clean_result.clean_count,
            raw_revenue=clean_result.raw_revenue,
            clean_revenue=clean_result.clean_revenue,
            duplicates_removed=clean_result.duplicates_removed,
            invalid_removed=clean_result.invalid_removed,
            rejected_rows_detailed=rejected_detailed,
            rejected_rows_with_revenue_count=rejected_with_revenue,
            rejected_revenue_excluded=rejected_rev_total,
            warnings=clean_result.warnings,
        )

    except ValueError as exc:
        # Mapping or cleaning raised a user-facing error
        logger.warning("Upload failed for %s: %s", filename, exc)
        return UploadResult(
            success=False,
            upload_log_id=None,
            filename=filename,
            file_type=file_type,
            raw_count=raw_count,
            clean_count=0,
            raw_revenue=0.0,
            clean_revenue=0.0,
            duplicates_removed=0,
            invalid_removed=0,
            error_message=str(exc),
        )

    except Exception as exc:
        # Unexpected error — log the full trace but show only a friendly message
        logger.exception("Unexpected error during upload of %s", filename)
        return UploadResult(
            success=False,
            upload_log_id=None,
            filename=filename,
            file_type=file_type,
            raw_count=raw_count,
            clean_count=0,
            raw_revenue=0.0,
            clean_revenue=0.0,
            duplicates_removed=0,
            invalid_removed=0,
            error_message=(
                "An unexpected error occurred while processing your file. "
                "Please try again or contact support."
            ),
        )


def execute_cashbook_upload(
    raw_df: pd.DataFrame,
    filename: str,
    tenant_id: str,
    file_hash: Optional[str] = None,
    replace_existing: bool = False,
) -> UploadResult:
    """
    Execute an upload for a cash-book file by splitting it into sales and expenses.

    Atomically saves both halves under the tenant_id, linking them to separate UploadLog entries.
    """
    init_db()

    # 1. Duplicate check across cash-book logs
    if file_hash:
        with get_db() as db:
            existing = (
                db.query(UploadLog)
                .filter(
                    UploadLog.tenant_id == tenant_id,
                    UploadLog.file_hash.in_([file_hash, f"{file_hash}:sales", f"{file_hash}:expenses"])
                )
                .first()
            )
            if existing and not replace_existing:
                return UploadResult(
                    success=False,
                    upload_log_id=None,
                    filename=filename,
                    file_type="cashbook",
                    raw_count=len(raw_df),
                    clean_count=0,
                    raw_revenue=0.0,
                    clean_revenue=0.0,
                    duplicates_removed=0,
                    invalid_removed=0,
                    is_duplicate=True,
                    existing_upload_id=existing.id,
                    error_message=(
                        f"This cash-book has already been imported on {existing.uploaded_at.strftime('%d %b %Y')} "
                        f"as '{existing.filename}'. You can skip it or replace the previous import."
                    ),
                    is_cashbook=True,
                )

    # 2. If replace_existing, clean up old logs for this file_hash
    if file_hash and replace_existing:
        with get_db() as db:
            old_logs = (
                db.query(UploadLog)
                .filter(
                    UploadLog.tenant_id == tenant_id,
                    UploadLog.file_hash.in_([file_hash, f"{file_hash}:sales", f"{file_hash}:expenses"])
                )
                .all()
            )
            for old_log in old_logs:
                db.delete(old_log)
            db.commit()

    # 3. Split the cash-book
    split_res = split_cashbook(raw_df)
    if split_res.sales_count == 0 and split_res.expenses_count == 0:
        return UploadResult(
            success=False,
            upload_log_id=None,
            filename=filename,
            file_type="cashbook",
            raw_count=len(raw_df),
            clean_count=0,
            raw_revenue=0.0,
            clean_revenue=0.0,
            duplicates_removed=0,
            invalid_removed=0,
            error_message="Could not find any valid sales or expense rows to import from this cash-book.",
            is_cashbook=True,
        )

    # 4. Execute sales portion
    sales_res = None
    if split_res.sales_count > 0:
        sales_res = execute_upload(
            raw_df=split_res.sales_df,
            confirmed_mapping={"date": "date", "product": "product", "revenue": "revenue"},
            file_type="sales",
            filename=f"{filename} (Sales)",
            tenant_id=tenant_id,
            file_hash=f"{file_hash}:sales" if file_hash else None,
            replace_existing=False,
        )
        if not sales_res.success:
            return sales_res

    # 5. Execute expenses portion
    expenses_res = None
    if split_res.expenses_count > 0:
        expenses_res = execute_upload(
            raw_df=split_res.expenses_df,
            confirmed_mapping={"date": "date", "category": "category", "amount": "amount"},
            file_type="expenses",
            filename=f"{filename} (Expenses)",
            tenant_id=tenant_id,
            file_hash=f"{file_hash}:expenses" if file_hash else None,
            replace_existing=False,
        )
        if not expenses_res.success:
            return expenses_res

    # 6. Combine results
    clean_count = (sales_res.clean_count if sales_res else 0) + (expenses_res.clean_count if expenses_res else 0)
    raw_rev = sales_res.raw_revenue if sales_res else 0.0
    clean_rev = sales_res.clean_revenue if sales_res else 0.0
    dupes = (sales_res.duplicates_removed if sales_res else 0) + (expenses_res.duplicates_removed if expenses_res else 0)
    invalids = (sales_res.invalid_removed if sales_res else 0) + (expenses_res.invalid_removed if expenses_res else 0)
    rejected = (sales_res.rejected_rows_detailed if sales_res else []) + (expenses_res.rejected_rows_detailed if expenses_res else [])
    warnings = (sales_res.warnings if sales_res else []) + (expenses_res.warnings if expenses_res else [])

    return UploadResult(
        success=True,
        upload_log_id=sales_res.upload_log_id if sales_res else expenses_res.upload_log_id,
        filename=filename,
        file_type="cashbook",
        raw_count=len(raw_df),
        clean_count=clean_count,
        raw_revenue=raw_rev,
        clean_revenue=clean_rev,
        duplicates_removed=dupes,
        invalid_removed=invalids,
        rejected_rows_detailed=rejected,
        warnings=warnings,
        is_cashbook=True,
        cashbook_summary=split_res.summary_message,
        sales_upload_id=sales_res.upload_log_id if sales_res else None,
        expenses_upload_id=expenses_res.upload_log_id if expenses_res else None,
    )

