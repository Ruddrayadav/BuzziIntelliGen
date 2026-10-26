"""
tests/test_report_service.py
----------------------------
Tests for monthly executive PDF report generation.
"""

import json
from pathlib import Path
import pytest

from db.database import get_db, init_db
from db.models import Expenses, Sales, User
from services.report_service import (
    _resolve_report_month,
    generate_monthly_pdf_report,
)
from services.target_service import set_monthly_target
from services.upload_service import execute_upload, suggest_mapping_from_file

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def _read_bytes(filename: str) -> bytes:
    with open(DATA_DIR / filename, "rb") as f:
        return f.read()



class TestReportService:
    TENANT_A = "report_tenant_a"
    TENANT_B = "report_tenant_b"

    def setup_method(self):
        init_db()
        with get_db() as db:
            db.query(Sales).filter(Sales.tenant_id.in_([self.TENANT_A, self.TENANT_B])).delete()
            db.query(Expenses).filter(Expenses.tenant_id.in_([self.TENANT_A, self.TENANT_B])).delete()
            db.query(User).filter(User.tenant_id.in_([self.TENANT_A, self.TENANT_B])).delete()
            # Register user
            user_a = User(
                username=self.TENANT_A,
                password_hash="scrypt$test",
                salt="salt",
                tenant_id=self.TENANT_A,
                business_name="Cafe Alpha",
            )
            user_b = User(
                username=self.TENANT_B,
                password_hash="scrypt$test",
                salt="salt",
                tenant_id=self.TENANT_B,
                business_name="Bistro Beta",
            )
            db.add_all([user_a, user_b])
            db.commit()

    def teardown_method(self):
        with get_db() as db:
            db.query(Sales).filter(Sales.tenant_id.in_([self.TENANT_A, self.TENANT_B])).delete()
            db.query(Expenses).filter(Expenses.tenant_id.in_([self.TENANT_A, self.TENANT_B])).delete()
            db.query(User).filter(User.tenant_id.in_([self.TENANT_A, self.TENANT_B])).delete()
            db.commit()

    def test_invalid_month_format_raises_error(self):
        with pytest.raises(ValueError, match="Invalid month format"):
            _resolve_report_month(self.TENANT_A, "invalid-month")

        with pytest.raises(ValueError, match="Invalid month format"):
            _resolve_report_month(self.TENANT_A, "2024-13")

    def test_empty_tenant_raises_error(self):
        with pytest.raises(ValueError, match="No sales or expense records found"):
            generate_monthly_pdf_report(self.TENANT_A)

    def test_pdf_generation_produces_valid_pdf_bytes(self):
        # Ingest sales
        sales_bytes = _read_bytes("sample_sales.csv")
        prev_s = suggest_mapping_from_file(sales_bytes, "sales.csv", "sales", use_llm=False)
        execute_upload(
            prev_s.raw_df,
            prev_s.suggested.to_rename_dict(),
            "sales",
            "sales.csv",
            self.TENANT_A,
            file_hash="hash_rep_s1",
        )

        # Ingest expenses
        exp_bytes = _read_bytes("sample_expenses.csv")
        prev_e = suggest_mapping_from_file(exp_bytes, "expenses.csv", "expenses", use_llm=False)
        execute_upload(
            prev_e.raw_df,
            prev_e.suggested.to_rename_dict(),
            "expenses",
            "expenses.csv",
            self.TENANT_A,
            file_hash="hash_rep_e1",
        )

        # Set target for pacing section
        set_monthly_target(self.TENANT_A, "2024-01", 50000.0)

        # Generate report for 2024-01
        pdf_bytes = generate_monthly_pdf_report(self.TENANT_A, "2024-01")

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        # Valid PDF file signature
        assert pdf_bytes.startswith(b"%PDF-")
        # Contains EOF marker
        assert b"%%EOF" in pdf_bytes

    def test_pdf_generation_resolves_latest_month_when_none_provided(self):
        sales_bytes = _read_bytes("sample_sales.csv")
        prev_s = suggest_mapping_from_file(sales_bytes, "sales.csv", "sales", use_llm=False)
        execute_upload(
            prev_s.raw_df,
            prev_s.suggested.to_rename_dict(),
            "sales",
            "sales.csv",
            self.TENANT_A,
            file_hash="hash_rep_latest",
        )

        # Calling without month should auto-resolve latest date's month
        pdf_bytes = generate_monthly_pdf_report(self.TENANT_A, month=None)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_tenant_isolation_on_pdf_generation(self):
        # Tenant A has data, Tenant B has no data
        sales_bytes = _read_bytes("sample_sales.csv")
        prev_s = suggest_mapping_from_file(sales_bytes, "sales.csv", "sales", use_llm=False)
        execute_upload(
            prev_s.raw_df,
            prev_s.suggested.to_rename_dict(),
            "sales",
            "sales.csv",
            self.TENANT_A,
            file_hash="hash_rep_iso",
        )

        # Tenant A succeeds
        pdf_a = generate_monthly_pdf_report(self.TENANT_A, "2024-01")
        assert len(pdf_a) > 0

        # Tenant B fails with ValueError (strict isolation)
        with pytest.raises(ValueError, match="No sales or expense records found"):
            generate_monthly_pdf_report(self.TENANT_B, month=None)
