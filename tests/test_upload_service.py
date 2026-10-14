"""
tests/test_upload_service.py
-----------------------------
Integration tests for services/upload_service.py.

WHAT WE'RE TESTING:
  The full upload pipeline from raw bytes to DB rows:
    file bytes → read → suggest mapping → apply → clean → save → UploadResult

  These tests use a REAL SQLite database (in-memory, via a test engine)
  so they verify the actual DB writes, not just the logic.

HOW TO RUN:
  pytest tests/test_upload_service.py -v

WHY IN-MEMORY DB FOR TESTS?
  An in-memory SQLite DB (:memory:) is created fresh for each test run
  and discarded when the process ends. This means:
  - Tests never pollute the real biz_intelligence.db file.
  - Tests are fast (no disk I/O).
  - Each test run starts clean — no leftover rows from a previous run.
"""

from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"
TENANT = "test_restaurant_01"


def _read_bytes(filename: str) -> bytes:
    """Read a sample file as bytes, simulating what Streamlit sends us."""
    return (SAMPLES_DIR / filename).read_bytes()


# ─────────────────────────────────────────────────────────────────────────────
# Tests for validate_file
# ─────────────────────────────────────────────────────────────────────────────
class TestValidateFile:
    from services.upload_service import validate_file

    def test_valid_csv_passes(self):
        from services.upload_service import validate_file
        data = b"col1,col2\nval1,val2"
        validate_file(data, "sales.csv")  # should not raise

    def test_unsupported_extension_raises(self):
        from services.upload_service import validate_file
        with pytest.raises(ValueError, match="not supported"):
            validate_file(b"data", "file.pdf")

    def test_oversized_file_raises(self):
        from services.upload_service import validate_file
        from config import settings
        big = b"x" * (settings.MAX_UPLOAD_SIZE_BYTES + 1)
        with pytest.raises(ValueError, match="too large"):
            validate_file(big, "big.csv")

    def test_xlsx_passes(self):
        from services.upload_service import validate_file
        validate_file(b"fake", "report.xlsx")  # size OK, extension OK


# ─────────────────────────────────────────────────────────────────────────────
# Tests for read_file
# ─────────────────────────────────────────────────────────────────────────────
class TestReadFile:

    def test_reads_csv(self):
        from services.upload_service import read_file
        data = _read_bytes("sample_sales.csv")
        df = read_file(data, "sample_sales.csv")
        assert len(df) == 60
        assert "item_name" in df.columns

    def test_reads_expenses_csv(self):
        from services.upload_service import read_file
        data = _read_bytes("sample_expenses.csv")
        df = read_file(data, "sample_expenses.csv")
        assert len(df) == 34
        assert "Amount" in df.columns

    def test_empty_csv_raises(self):
        from services.upload_service import read_file
        # pandas raises "No columns to parse from file" for truly empty bytes
        with pytest.raises((ValueError, Exception)):
            read_file(b"", "empty.csv")

    def test_invalid_csv_raises(self):
        from services.upload_service import read_file
        # A file that looks like CSV but is actually random bytes
        with pytest.raises((ValueError, Exception)):
            read_file(b"\x00\x01\x02\x03", "corrupt.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Tests for suggest_mapping_from_file (Phase A)
# ─────────────────────────────────────────────────────────────────────────────
class TestSuggestMappingFromFile:

    def test_returns_upload_preview_for_sales(self):
        from services.upload_service import UploadPreview, suggest_mapping_from_file
        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        assert isinstance(preview, UploadPreview)
        assert preview.file_type == "sales"
        assert preview.raw_row_count == 60

    def test_returns_upload_preview_for_expenses(self):
        from services.upload_service import UploadPreview, suggest_mapping_from_file
        data = _read_bytes("sample_expenses.csv")
        preview = suggest_mapping_from_file(data, "sample_expenses.csv", "expenses", use_llm=False)
        assert isinstance(preview, UploadPreview)
        assert preview.file_type == "expenses"

    def test_mapping_is_complete_for_sample_files(self):
        from services.upload_service import suggest_mapping_from_file
        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        assert preview.suggested.is_complete, (
            f"Mapping incomplete, missing: {preview.suggested.missing_required}"
        )

    def test_sample_rows_returns_at_most_5(self):
        from services.upload_service import suggest_mapping_from_file
        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        assert len(preview.sample_rows) <= 5

    def test_invalid_file_raises_value_error(self):
        from services.upload_service import suggest_mapping_from_file
        with pytest.raises(ValueError):
            suggest_mapping_from_file(b"not a csv at all \\x00\\x01", "bad.pdf", "sales")


# ─────────────────────────────────────────────────────────────────────────────
# Tests for execute_upload (Phase B)
# ─────────────────────────────────────────────────────────────────────────────
class TestExecuteUpload:
    """
    These tests exercise the full pipeline and write to the real SQLite DB.

    After each test we delete the test rows so the DB stays clean.
    We use the tenant_id "pytest_tenant" to identify test data.
    """

    TENANT = "pytest_tenant_upload"

    def _cleanup(self):
        """Remove any rows this test wrote, so tests are idempotent."""
        from db.database import get_db
        from db.models import UploadLog
        with get_db() as db:
            logs = (
                db.query(UploadLog)
                .filter(UploadLog.tenant_id.in_([self.TENANT, "tenant_b_pytest"]))
                .all()
            )
            for log in logs:
                db.delete(log)
            db.commit()

    def setup_method(self):
        """Initialise DB tables and clean up any leftovers before each test."""
        from db.database import init_db
        init_db()
        self._cleanup()

    def teardown_method(self):
        """Clean up after each test."""
        self._cleanup()

    def _run_sales_upload(self) -> "UploadResult":
        from services.upload_service import (
            execute_upload,
            read_file,
            suggest_mapping_from_file,
        )
        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        confirmed = preview.suggested.to_rename_dict()
        return execute_upload(preview.raw_df, confirmed, "sales", "sample_sales.csv", self.TENANT)

    def _run_expenses_upload(self) -> "UploadResult":
        from services.upload_service import (
            execute_upload,
            suggest_mapping_from_file,
        )
        data = _read_bytes("sample_expenses.csv")
        preview = suggest_mapping_from_file(data, "sample_expenses.csv", "expenses", use_llm=False)
        confirmed = preview.suggested.to_rename_dict()
        return execute_upload(preview.raw_df, confirmed, "expenses", "sample_expenses.csv", self.TENANT)

    # ── Result shape ──────────────────────────────────────────────────────────
    def test_sales_upload_returns_upload_result(self):
        from services.upload_service import UploadResult
        result = self._run_sales_upload()
        assert isinstance(result, UploadResult)

    def test_sales_upload_succeeds(self):
        result = self._run_sales_upload()
        assert result.success is True

    def test_expenses_upload_succeeds(self):
        result = self._run_expenses_upload()
        assert result.success is True

    # ── Row counts ────────────────────────────────────────────────────────────
    def test_sales_raw_count_correct(self):
        result = self._run_sales_upload()
        assert result.raw_count == 60

    def test_sales_duplicates_removed(self):
        result = self._run_sales_upload()
        assert result.duplicates_removed == 0

    def test_sales_clean_count_less_than_raw(self):
        result = self._run_sales_upload()
        assert result.clean_count < result.raw_count
        assert result.clean_count > 0

    # ── Database was actually written ─────────────────────────────────────────
    def test_upload_log_row_created_for_sales(self):
        from db.database import SessionLocal
        from db.models import UploadLog

        result = self._run_sales_upload()
        assert result.upload_log_id is not None

        db = SessionLocal()
        try:
            log = db.query(UploadLog).filter_by(id=result.upload_log_id).first()
            assert log is not None
            assert log.tenant_id == self.TENANT
            assert log.file_type == "sales"
            assert log.row_count_clean == result.clean_count
        finally:
            db.close()

    def test_sales_rows_saved_to_db(self):
        from db.database import SessionLocal
        from db.models import Sales

        result = self._run_sales_upload()

        db = SessionLocal()
        try:
            count = db.query(Sales).filter_by(tenant_id=self.TENANT).count()
            assert count == result.clean_count
        finally:
            db.close()

    def test_expense_rows_saved_to_db(self):
        from db.database import SessionLocal
        from db.models import Expenses

        result = self._run_expenses_upload()

        db = SessionLocal()
        try:
            count = db.query(Expenses).filter_by(tenant_id=self.TENANT).count()
            assert count == result.clean_count
        finally:
            db.close()

    def test_tenant_isolation_after_upload(self):
        """Rows saved for our tenant must NOT appear under a different tenant_id."""
        from db.database import SessionLocal
        from db.models import Sales

        self._run_sales_upload()

        db = SessionLocal()
        try:
            other_count = db.query(Sales).filter_by(tenant_id="attacker_id").count()
            assert other_count == 0
        finally:
            db.close()

    def test_revenue_values_correct_in_db(self):
        """Spot-check: Butter Chicken on 2024-01-03 should have revenue 640.0."""
        from datetime import date

        from db.database import SessionLocal
        from db.models import Sales

        self._run_sales_upload()

        db = SessionLocal()
        try:
            row = (
                db.query(Sales)
                .filter_by(
                    tenant_id=self.TENANT,
                    product="Butter Chicken",
                    date=date(2024, 1, 3),
                )
                .first()
            )
            assert row is not None, "Expected Butter Chicken on 2024-01-03"
            assert row.revenue == 640.0
        finally:
            db.close()

    # ── Error handling ────────────────────────────────────────────────────────
    def test_empty_mapping_returns_failure(self):
        """If the confirmed mapping is completely wrong, we get a graceful failure."""
        from services.upload_service import execute_upload
        import pandas as pd

        df = pd.DataFrame({"UNKNOWN_COL": ["a", "b"]})
        result = execute_upload(df, {"NONEXISTENT": "revenue"}, "sales", "bad.csv", self.TENANT)
        assert result.success is False
        assert result.error_message is not None

    def test_summary_string_non_empty_on_success(self):
        result = self._run_sales_upload()
        assert result.success
        assert len(result.summary()) > 0
        assert "✅" in result.summary()

    def test_summary_string_on_failure(self):
        from services.upload_service import UploadResult
        result = UploadResult(
            success=False,
            upload_log_id=None,
            filename="bad.csv",
            file_type="sales",
            raw_count=10,
            clean_count=0,
            raw_revenue=0.0,
            clean_revenue=0.0,
            duplicates_removed=0,
            invalid_removed=0,
            error_message="Something went wrong",
        )
        assert "failed" in result.summary().lower()

    # ── Duplicate detection & Replace behavior ────────────────────────────────
    def test_duplicate_file_hash_detected(self):
        from services.upload_service import execute_upload, suggest_mapping_from_file

        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        confirmed = preview.suggested.to_rename_dict()
        file_hash = "fake_sha256_hash_1234567890abcdef"

        # First upload succeeds
        res1 = execute_upload(
            preview.raw_df, confirmed, "sales", "sample_sales.csv", self.TENANT, file_hash=file_hash
        )
        assert res1.success is True
        assert res1.is_duplicate is False

        # Second upload with same hash detects duplicate
        res2 = execute_upload(
            preview.raw_df, confirmed, "sales", "sample_sales.csv", self.TENANT, file_hash=file_hash, replace_existing=False
        )
        assert res2.success is False
        assert res2.is_duplicate is True
        assert res2.existing_upload_id == res1.upload_log_id
        assert "already been imported" in res2.error_message

    def test_duplicate_file_hash_replace_succeeds(self):
        from db.database import SessionLocal
        from db.models import Sales, UploadLog
        from services.upload_service import execute_upload, suggest_mapping_from_file

        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        confirmed = preview.suggested.to_rename_dict()
        file_hash = "replace_hash_abcdef1234567890"

        # First upload
        res1 = execute_upload(
            preview.raw_df, confirmed, "sales", "sample_sales.csv", self.TENANT, file_hash=file_hash
        )
        assert res1.success is True

        db = SessionLocal()
        try:
            count1 = db.query(Sales).filter_by(tenant_id=self.TENANT).count()
            assert count1 == res1.clean_count
        finally:
            db.close()

        # Second upload with replace_existing=True
        res2 = execute_upload(
            preview.raw_df, confirmed, "sales", "sample_sales.csv", self.TENANT, file_hash=file_hash, replace_existing=True
        )
        assert res2.success is True
        assert res2.is_duplicate is False

        db = SessionLocal()
        try:
            # Row count should be res2.clean_count, NOT count1 + res2.clean_count (no duplicates added!)
            count2 = db.query(Sales).filter_by(tenant_id=self.TENANT).count()
            assert count2 == res2.clean_count
            # Exactly one UploadLog should exist for this tenant
            logs = db.query(UploadLog).filter_by(tenant_id=self.TENANT).all()
            assert len(logs) == 1
            assert logs[0].id == res2.upload_log_id
        finally:
            db.close()

    def test_duplicate_file_hash_tenant_isolation(self):
        """If Tenant A uploads a file, Tenant B uploading the exact same file is NOT blocked."""
        from services.upload_service import execute_upload, suggest_mapping_from_file

        data = _read_bytes("sample_sales.csv")
        preview = suggest_mapping_from_file(data, "sample_sales.csv", "sales", use_llm=False)
        confirmed = preview.suggested.to_rename_dict()
        shared_hash = "shared_sha256_hash_999999999"

        res_a = execute_upload(
            preview.raw_df, confirmed, "sales", "sales_a.csv", self.TENANT, file_hash=shared_hash
        )
        assert res_a.success is True

        # Tenant B uploads the same hash
        res_b = execute_upload(
            preview.raw_df, confirmed, "sales", "sales_b.csv", "tenant_b_pytest", file_hash=shared_hash
        )
        assert res_b.success is True
        assert res_b.is_duplicate is False

