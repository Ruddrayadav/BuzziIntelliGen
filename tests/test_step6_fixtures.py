"""
tests/test_step6_fixtures.py
----------------------------
Integration and verification fixture tests for Step 6:
  - 1_messy_sales.csv: 8 clean + 1 warning, 4 rejected; rev 2,310, units 16, 9 orders, AOV 256.67.
    Rejection reasons and stored raw rows without nulls.
  - 2_messy_expenses.csv: 5 clean + 1 warning, 3 rejected; total 52,800.
    Rejection reasons and stored raw rows without nulls.
  - 6_shop_sales.csv + 6_shop_expenses.csv: rev 2,715, expenses 15,450,
    dates 5–7 March 2024, top product Rice 5kg (1,650).
  - 8_empty.csv & 8_header_only.csv: return HTTP 400 with 0 saved.
"""

from collections import defaultdict
from datetime import date
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.database import get_db, init_db
from db.models import Expenses, RejectedRow, Sales, UploadLog, User
from services.upload_service import execute_upload, suggest_mapping_from_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def clean_fixtures_db():
    init_db()
    tenants = [
        "tenant_step6_sales",
        "tenant_step6_expenses",
        "tenant_step6_shop",
        "tenant_step6_empty",
    ]
    with get_db() as db:
        for t in tenants:
            db.query(RejectedRow).filter(RejectedRow.tenant_id == t).delete()
            db.query(Sales).filter(Sales.tenant_id == t).delete()
            db.query(Expenses).filter(Expenses.tenant_id == t).delete()
            db.query(UploadLog).filter(UploadLog.tenant_id == t).delete()
            db.query(User).filter(User.username == t).delete()
        db.commit()
    yield
    with get_db() as db:
        for t in tenants:
            db.query(RejectedRow).filter(RejectedRow.tenant_id == t).delete()
            db.query(Sales).filter(Sales.tenant_id == t).delete()
            db.query(Expenses).filter(Expenses.tenant_id == t).delete()
            db.query(UploadLog).filter(UploadLog.tenant_id == t).delete()
            db.query(User).filter(User.username == t).delete()
        db.commit()


def test_1_messy_sales_fixture():
    tenant = "tenant_step6_sales"
    file_path = FIXTURES_DIR / "1_messy_sales.csv"
    data = file_path.read_bytes()

    preview = suggest_mapping_from_file(data, "1_messy_sales.csv", "sales", use_llm=False)
    mapping = preview.suggested.to_rename_dict()
    result = execute_upload(preview.raw_df, mapping, "sales", "1_messy_sales.csv", tenant)

    assert result.success is True
    # 8 clean + 1 warning = 9 rows saved
    assert result.clean_count == 9
    assert result.saved_with_warnings == 1
    assert result.invalid_removed == 4
    assert result.clean_revenue == pytest.approx(2310.0)

    with get_db() as db:
        # Check sales rows saved
        sales = db.query(Sales).filter_by(tenant_id=tenant).all()
        assert len(sales) == 9

        units = sum(s.quantity for s in sales)
        assert units == 16.0

        revenue = sum(s.revenue for s in sales)
        assert revenue == pytest.approx(2310.0)

        # 9 distinct orders/rows
        orders = len(sales)
        assert orders == 9

        aov = revenue / orders
        assert round(aov, 2) == 256.67

        # Missing product row saved as "Unknown item"
        warning_rows = [s for s in sales if s.product == "Unknown item"]
        assert len(warning_rows) == 1
        assert warning_rows[0].revenue == 100.0

        # Check rejected rows
        rejections = db.query(RejectedRow).filter_by(tenant_id=tenant, upload_id=result.upload_log_id).all()
        assert len(rejections) == 4

        reasons = {r.reason for r in rejections}
        assert reasons == {
            "Missing date",
            "Revenue is not a number",
            "negative or zero quantity/revenue",
            "Invalid date",
        }

        # Check stored raw rows are strings and contain no null
        for r in rejections:
            row_dict = json.loads(r.row_data)
            for k, v in row_dict.items():
                assert isinstance(v, str), f"Field {k} in rejected row is not string: {v!r}"
                assert v != "null", f"Field {k} should not be 'null'"


def test_2_messy_expenses_fixture():
    tenant = "tenant_step6_expenses"
    file_path = FIXTURES_DIR / "2_messy_expenses.csv"
    data = file_path.read_bytes()

    preview = suggest_mapping_from_file(data, "2_messy_expenses.csv", "expenses", use_llm=False)
    mapping = preview.suggested.to_rename_dict()
    result = execute_upload(preview.raw_df, mapping, "expenses", "2_messy_expenses.csv", tenant)

    assert result.success is True
    # 5 clean + 1 warning = 6 rows saved
    assert result.clean_count == 6
    assert result.saved_with_warnings == 1
    assert result.invalid_removed == 3
    assert result.clean_revenue == pytest.approx(52800.0)

    with get_db() as db:
        expenses = db.query(Expenses).filter_by(tenant_id=tenant).all()
        assert len(expenses) == 6

        total_amount = sum(e.amount for e in expenses)
        assert total_amount == pytest.approx(52800.0)

        # Missing category row saved as "Uncategorised"
        warning_rows = [e for e in expenses if e.category == "Uncategorised"]
        assert len(warning_rows) == 1
        assert warning_rows[0].amount == 900.0

        # Check rejected rows
        rejections = db.query(RejectedRow).filter_by(tenant_id=tenant, upload_id=result.upload_log_id).all()
        assert len(rejections) == 3

        reasons = {r.reason for r in rejections}
        assert reasons == {
            "Missing date",
            "Amount is not a number",
            "negative or zero amount",
        }

        # Check stored raw rows are strings and contain no null
        for r in rejections:
            row_dict = json.loads(r.row_data)
            for k, v in row_dict.items():
                assert isinstance(v, str), f"Field {k} in rejected row is not string: {v!r}"
                assert v != "null", f"Field {k} should not be 'null'"


def test_6_shop_sales_and_expenses_fixtures():
    tenant = "tenant_step6_shop"

    sales_path = FIXTURES_DIR / "6_shop_sales.csv"
    sales_data = sales_path.read_bytes()
    sales_prev = suggest_mapping_from_file(sales_data, "6_shop_sales.csv", "sales", use_llm=False)
    sales_res = execute_upload(sales_prev.raw_df, sales_prev.suggested.to_rename_dict(), "sales", "6_shop_sales.csv", tenant)

    assert sales_res.success is True
    assert sales_res.clean_count == 7
    assert sales_res.clean_revenue == pytest.approx(2715.0)

    expenses_path = FIXTURES_DIR / "6_shop_expenses.csv"
    expenses_data = expenses_path.read_bytes()
    expenses_prev = suggest_mapping_from_file(expenses_data, "6_shop_expenses.csv", "expenses", use_llm=False)
    expenses_res = execute_upload(expenses_prev.raw_df, expenses_prev.suggested.to_rename_dict(), "expenses", "6_shop_expenses.csv", tenant)

    assert expenses_res.success is True
    assert expenses_res.clean_count == 3
    assert expenses_res.clean_revenue == pytest.approx(15450.0)

    with get_db() as db:
        sales = db.query(Sales).filter_by(tenant_id=tenant).all()
        dates = {s.date for s in sales}
        # Dates must be 5-7 March 2024, not May-July
        assert dates == {date(2024, 3, 5), date(2024, 3, 6), date(2024, 3, 7)}

        # Top product by revenue: Rice 5kg = 1,650
        prod_rev = defaultdict(float)
        for s in sales:
            prod_rev[s.product] += s.revenue
        top_product, top_rev = max(prod_rev.items(), key=lambda x: x[1])
        assert "rice 5kg" in top_product.lower()
        assert top_rev == pytest.approx(1650.0)

        # Net profit
        total_rev = sum(s.revenue for s in sales)
        expenses = db.query(Expenses).filter_by(tenant_id=tenant).all()
        total_exp = sum(e.amount for e in expenses)
        net_profit = total_rev - total_exp
        assert net_profit == pytest.approx(-12735.0)


def test_empty_and_header_only_fixtures_return_400():
    client = TestClient(app)
    tenant = "tenant_step6_empty"

    # Register & login
    client.post("/api/auth/register", json={"username": tenant, "password": "SafePassword123!", "business_name": "Step6 Empty Store"})
    client.post("/api/auth/login", json={"username": tenant, "password": "SafePassword123!"})

    for fname in ["8_empty.csv", "8_header_only.csv"]:
        data = (FIXTURES_DIR / fname).read_bytes()

        # Preview returns 400
        preview_resp = client.post(
            "/api/upload/preview",
            files={"file": (fname, data, "text/csv")},
            data={"file_type": "sales"},
        )
        assert preview_resp.status_code == 400
        assert "message" in preview_resp.json() or "detail" in preview_resp.json()

        # Commit returns 400
        commit_resp = client.post(
            "/api/upload/commit",
            files={"file": (fname, data, "text/csv")},
            data={"file_type": "sales", "confirmed_mapping": "{}"},
        )
        assert commit_resp.status_code == 400

    # Ensure 0 rows saved in DB
    with get_db() as db:
        saved_sales = db.query(Sales).filter_by(tenant_id=tenant).count()
        saved_expenses = db.query(Expenses).filter_by(tenant_id=tenant).count()
        saved_logs = db.query(UploadLog).filter_by(tenant_id=tenant).count()
        assert saved_sales == 0
        assert saved_expenses == 0
        assert saved_logs == 0
