"""
tests/test_detector.py
----------------------
Unit and integration tests for api/detector.py and cash-book splitting in services/upload_service.py.

WHAT WE TEST:
  1. Word boundary regex matching:
     - "rent" does NOT match inside "current", "parent", "differential"
     - "cost" does NOT match inside "accost" or "customer"
  2. Realistic column sets and sample file detection:
     - sample_expenses.csv is classified as 'expenses' (fixes the bug where it was labeled sales)
     - sample_sales.csv is classified as 'sales'
     - E-commerce / POS schemas are classified as 'sales'
     - Vendor / voucher schemas are classified as 'expenses'
  3. Cash-book structure detection:
     - Dual Debit / Credit columns detected as 'cashbook'
     - Mixed Type column (Sales + Expenses) detected as 'cashbook'
  4. Cash-book splitting (services/upload_service.py):
     - Debit/Credit column-based splitting
     - Type column-based splitting
     - Signed amount splitting
  5. execute_cashbook_upload:
     - End-to-end DB saving of both sales and expense records from a single file
     - Duplicate detection and replace behavior for cashbooks
"""

from pathlib import Path
import pandas as pd
import pytest

from api.detector import detect_file_type, _has_word
from services.upload_service import (
    split_cashbook,
    execute_cashbook_upload,
)
from db.database import get_db, init_db
from db.models import Sales, Expenses, UploadLog

SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"
TENANT = "test_detector_tenant"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Word Boundary Unit Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestWordBoundaries:

    def test_rent_does_not_match_current(self):
        assert _has_word("current", "rent") is False
        assert _has_word("parent_id", "rent") is False
        assert _has_word("differential_rent", "rent") is True
        assert _has_word("shop rent", "rent") is True

    def test_cost_does_not_match_customer(self):
        assert _has_word("customer", "cost") is False
        assert _has_word("customer_name", "cost") is False
        assert _has_word("total_cost", "cost") is True

    def test_detector_with_current_does_not_label_expense(self):
        # A file with 'date', 'current_balance', 'amount' should NOT be labeled expenses just because of 'current'
        file_type = detect_file_type(["date", "current", "amount"])
        assert file_type != "expenses" or file_type == "sales"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Real Sample & Schema Classification Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestFileTypeDetection:

    def test_sample_expenses_csv_detected_as_expenses(self):
        """sample_expenses.csv (Date, Type, Details, Amount) MUST be classified as expenses."""
        df = pd.read_csv(SAMPLES_DIR / "sample_expenses.csv")
        detected = detect_file_type(df.columns.tolist(), df)
        assert detected == "expenses", f"Expected 'expenses', got '{detected}'"

    def test_sample_sales_csv_detected_as_sales(self):
        """sample_sales.csv MUST be classified as sales."""
        df = pd.read_csv(SAMPLES_DIR / "sample_sales.csv")
        detected = detect_file_type(df.columns.tolist(), df)
        assert detected == "sales", f"Expected 'sales', got '{detected}'"

    def test_pos_sales_schema_detected_as_sales(self):
        cols = ["Order Number", "Order Date", "Menu Item", "Item Category", "Qty Sold", "Price", "Subtotal"]
        assert detect_file_type(cols) == "sales"

    def test_vendor_expense_schema_detected_as_expenses(self):
        cols = ["Voucher No", "Payment Date", "Vendor Name", "Expense Category", "Bill Amount"]
        assert detect_file_type(cols) == "expenses"

    def test_salary_sheet_detected_as_expenses(self):
        cols = ["Employee ID", "Month", "Salary Paid", "Bank Transfer Ref"]
        assert detect_file_type(cols) == "expenses"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cash-Book Structure Detection Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestCashbookDetection:

    def test_debit_credit_columns_detected_as_cashbook(self):
        cols = ["Date", "Description", "Debit", "Credit"]
        assert detect_file_type(cols) == "cashbook"

    def test_dr_cr_columns_detected_as_cashbook(self):
        cols = ["Txn Date", "Particulars", "Dr", "Cr"]
        assert detect_file_type(cols) == "cashbook"

    def test_money_in_money_out_detected_as_cashbook(self):
        cols = ["Date", "Narration", "Money In", "Money Out"]
        assert detect_file_type(cols) == "cashbook"

    def test_type_column_with_mixed_values_detected_as_cashbook(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-01", "2024-01-02"],
            "Description": ["Counter sale", "Store rent", "Catering payment"],
            "Amount": [15000, 25000, 8000],
            "Type": ["Sale", "Expense", "Income"],
        })
        assert detect_file_type(df.columns.tolist(), df) == "cashbook"

    def test_type_column_with_only_expenses_is_not_cashbook(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-02"],
            "Details": ["Office rent", "Staff salary"],
            "Amount": [25000, 18000],
            "Type": ["Rent", "Salary"],
        })
        assert detect_file_type(df.columns.tolist(), df) == "expenses"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cash-Book Splitting Logic Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestCashbookSplitting:

    def test_split_by_debit_credit_columns(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "Particulars": ["Counter Sales Jan 1", "Shop Rent", "Counter Sales Jan 2", "Electricity Bill"],
            "Debit": [0, 25000, 0, 3200],
            "Credit": [15000, 0, 18500, 0],
        })
        res = split_cashbook(df)
        assert res.split_method == "debit_credit"
        assert res.sales_count == 2
        assert res.expenses_count == 2
        assert res.sales_total == 33500.0
        assert res.expenses_total == 28200.0
        assert "Counter Sales Jan 1" in res.sales_df["product"].values
        assert "Shop Rent" in res.expenses_df["category"].values

    def test_split_by_type_column(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "Description": ["Cash sales", "Cleaning service", "Zomato payouts", "Vegetables"],
            "Amount": ["₹12,000", "₹1,500", "₹9,500", "₹3,200"],
            "Type": ["Credit", "Debit", "Sale", "Expense"],
        })
        res = split_cashbook(df)
        assert res.split_method == "type_column"
        assert res.sales_count == 2
        assert res.expenses_count == 2
        assert res.sales_total == 21500.0
        assert res.expenses_total == 4700.0

    def test_split_by_signed_amount(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-01", "2024-01-02"],
            "Memo": ["Daily collection", "Kitchen repair", "Card payments"],
            "Amount": [14000, -3500, 8200],
        })
        res = split_cashbook(df)
        assert res.split_method == "amount_sign"
        assert res.sales_count == 2
        assert res.expenses_count == 1
        assert res.sales_total == 22200.0
        assert res.expenses_total == 3500.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. execute_cashbook_upload End-to-End Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestExecuteCashbookUpload:

    def _cleanup(self):
        init_db()
        with get_db() as db:
            logs = db.query(UploadLog).filter_by(tenant_id=TENANT).all()
            for log in logs:
                db.delete(log)
            db.commit()

    def setup_method(self):
        self._cleanup()

    def teardown_method(self):
        self._cleanup()

    def test_execute_cashbook_upload_saves_both_sales_and_expenses(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "Particulars": ["Jan 1 Sales", "Shop Rent", "Jan 2 Sales", "Utility Bill"],
            "Debit": [0, 25000, 0, 3200],
            "Credit": [15000, 0, 18500, 0],
        })

        res = execute_cashbook_upload(
            raw_df=df,
            filename="cashbook_jan.csv",
            tenant_id=TENANT,
            file_hash="cb_hash_12345",
        )

        assert res.success is True
        assert res.is_cashbook is True
        assert res.clean_count == 4
        assert "Split into 2 sales" in res.cashbook_summary

        # Verify DB writes
        with get_db() as db:
            sales_rows = db.query(Sales).filter_by(tenant_id=TENANT).all()
            exp_rows = db.query(Expenses).filter_by(tenant_id=TENANT).all()
            assert len(sales_rows) == 2
            assert len(exp_rows) == 2
            assert sum(r.revenue for r in sales_rows) == 33500.0
            assert sum(r.amount for r in exp_rows) == 28200.0

    def test_execute_cashbook_duplicate_and_replace(self):
        df = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-01"],
            "Description": ["Counter Sale", "Supplies"],
            "Debit": [0, 5000],
            "Credit": [12000, 0],
        })
        file_hash = "cb_dupe_hash_999"

        # First upload succeeds
        res1 = execute_cashbook_upload(df, "cb.csv", TENANT, file_hash=file_hash)
        assert res1.success is True

        # Second upload detects duplicate
        res2 = execute_cashbook_upload(df, "cb.csv", TENANT, file_hash=file_hash, replace_existing=False)
        assert res2.success is False
        assert res2.is_duplicate is True
        assert "already been imported" in res2.error_message

        # Third upload with replace_existing=True succeeds and replaces
        res3 = execute_cashbook_upload(df, "cb.csv", TENANT, file_hash=file_hash, replace_existing=True)
        assert res3.success is True

        with get_db() as db:
            sales_count = db.query(Sales).filter_by(tenant_id=TENANT).count()
            exp_count = db.query(Expenses).filter_by(tenant_id=TENANT).count()
            assert sales_count == 1
            assert exp_count == 1
