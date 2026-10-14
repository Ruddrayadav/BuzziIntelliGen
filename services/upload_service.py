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
from services.cleaning_service import CleaningResult, clean_dataframe
from services.mapping_service import (
    ColumnMapping,
    apply_mapping,
    suggest_mapping,
    validate_confirmed_mapping,
)

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
      file_type       — "sales" or "expenses"
      suggested       — ColumnMapping with rule/LLM suggestions.
      sample_rows     — First 5 rows of the raw DataFrame for preview table.
      raw_row_count   — Total rows in the uploaded file.
    """

    raw_df: pd.DataFrame
    filename: str
    file_type: str
    suggested: ColumnMapping
    raw_row_count: int

    @property
    def sample_rows(self) -> pd.DataFrame:
        """First 5 rows — shown to owner so they can see what the file looks like."""
        return self.raw_df.head(5)

    @property
    def column_names(self) -> list[str]:
        return self.raw_df.columns.tolist()


@dataclass
class UploadResult:
    """
    Returned by Phase B (execute_upload) after data is saved to the database.

    FIELDS:
      success          — True if at least some rows were saved.
      upload_log_id    — The ID of the UploadLog row in the database.
                         Use this to query the saved data later.
      filename         — Original filename.
      file_type        — "sales" or "expenses"
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

    def summary(self) -> str:
        """One-line plain-language summary for the owner."""
        if not self.success:
            return f"Upload failed: {self.error_message}"
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
        file_type:  "sales" or "expenses" — chosen by the owner in the UI.
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
