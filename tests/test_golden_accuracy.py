"""
tests/test_golden_accuracy.py
-----------------------------
Golden test to assert that data loaded into the database EXACTLY matches
the sums and row counts of valid data from the raw CSV files.

This prevents silent data loss due to over-aggressive deduplication or 
flawed cleaning logic.
"""

import pytest
import pandas as pd
from sqlalchemy import func

from db.database import get_db, init_db
from db.models import Sales, Expenses
from services.upload_service import suggest_mapping_from_file, execute_upload

TENANT = "golden_tenant"

def _parse_money_raw(val):
    if pd.isna(val): return 0.0
    s = str(val).replace("₹", "").replace(",", "").strip()
    try: return float(s)
    except: return 0.0

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(Expenses).filter_by(tenant_id=TENANT).delete()
        db.commit()

class TestGoldenAccuracy:
    def test_golden_sales_accuracy(self):
        filepath = "data/samples/sample_sales.csv"
        try:
            raw_df = pd.read_csv(filepath)
        except FileNotFoundError:
            pytest.skip(f"{filepath} not found.")

        # 1. Manual pandas calculation of valid rows
        # Drop rows missing essential financial fields to mimic valid data
        valid_raw = raw_df.dropna(subset=["date", "total"])
        valid_raw = valid_raw[valid_raw["total"].apply(_parse_money_raw) != 0]
        
        expected_count = len(valid_raw)
        expected_sum = valid_raw["total"].apply(_parse_money_raw).sum()
        
        # 2. Run through application pipeline
        with open(filepath, "rb") as f:
            file_bytes = f.read()
            
        preview = suggest_mapping_from_file(file_bytes, "sample_sales.csv", "sales", use_llm=False)
        
        # Build confirmed mapping (using rule-based suggestions)
        confirmed = preview.suggested.to_rename_dict()
        
        result = execute_upload(
            raw_df=preview.raw_df,
            confirmed_mapping=confirmed,
            file_type="sales",
            filename="sample_sales.csv",
            tenant_id=TENANT
        )
        
        assert result.success is True
        
        # 3. Assert DB equals Expected
        with get_db() as db:
            db_count = db.query(func.count(Sales.id)).filter_by(tenant_id=TENANT).scalar()
            db_sum = db.query(func.sum(Sales.revenue)).filter_by(tenant_id=TENANT).scalar() or 0.0
            
            assert db_count == expected_count, f"Row count mismatch! DB: {db_count}, Expected: {expected_count}"
            # Compare floats with small tolerance
            assert abs(db_sum - expected_sum) < 0.01, f"Sum mismatch! DB: {db_sum}, Expected: {expected_sum}"

    def test_golden_expenses_accuracy(self):
        filepath = "data/samples/sample_expenses.csv"
        try:
            raw_df = pd.read_csv(filepath)
        except FileNotFoundError:
            pytest.skip(f"{filepath} not found.")

        valid_raw = raw_df.dropna(subset=["Date", "Amount"])
        valid_raw = valid_raw[valid_raw["Amount"].apply(_parse_money_raw) != 0]
        
        expected_count = len(valid_raw)
        expected_sum = valid_raw["Amount"].apply(_parse_money_raw).sum()
        
        with open(filepath, "rb") as f:
            file_bytes = f.read()
            
        preview = suggest_mapping_from_file(file_bytes, "sample_expenses.csv", "expenses", use_llm=False)
        confirmed = preview.suggested.to_rename_dict()
        
        result = execute_upload(
            raw_df=preview.raw_df,
            confirmed_mapping=confirmed,
            file_type="expenses",
            filename="sample_expenses.csv",
            tenant_id=TENANT
        )
        
        assert result.success is True
        
        with get_db() as db:
            db_count = db.query(func.count(Expenses.id)).filter_by(tenant_id=TENANT).scalar()
            db_sum = db.query(func.sum(Expenses.amount)).filter_by(tenant_id=TENANT).scalar() or 0.0
            
            assert db_count == expected_count, f"Row count mismatch! DB: {db_count}, Expected: {expected_count}"
            assert abs(db_sum - expected_sum) < 0.01, f"Sum mismatch! DB: {db_sum}, Expected: {expected_sum}"
