import os
from io import BytesIO
import pandas as pd
import pytest

from db.database import get_db, init_db
from db.models import Sales, Expenses
from services.analytics_service import _calc_pct_change, compare_periods
from services.report_service import _fmt_pct, generate_monthly_pdf_report
from services.ai_service import _get_period_comparison_table, ask_question
from services.upload_service import execute_upload


TENANT = "tenant_step4_new_category"
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(Sales).filter(Sales.tenant_id == TENANT).delete()
        db.query(Expenses).filter(Expenses.tenant_id == TENANT).delete()
        db.commit()
    yield
    with get_db() as db:
        db.query(Sales).filter(Sales.tenant_id == TENANT).delete()
        db.query(Expenses).filter(Expenses.tenant_id == TENANT).delete()
        db.commit()


def test_calc_pct_change_returns_none_for_missing_or_zero_prior():
    # Previous value 0 or missing should return None
    assert _calc_pct_change(5000.0, 0.0) is None
    assert _calc_pct_change(5000.0, None) is None
    assert _calc_pct_change(None, 100.0) is None
    assert _calc_pct_change(0.0, 0.0) == 0.0
    # Normal change
    assert _calc_pct_change(3600.0, 3000.0) == 20.0
    assert _calc_pct_change(1200.0, 1500.0) == -20.0


def test_fmt_pct_shows_new_for_none():
    assert _fmt_pct(None) == "new"
    assert _fmt_pct(float("nan")) == "new"
    assert _fmt_pct(20.0) == "+20.0%"
    assert _fmt_pct(-20.0) == "-20.0%"


def test_new_category_fixtures_metrics_and_comparison():
    sales_path = os.path.join(FIXTURES_DIR, "4_new_category_sales.csv")
    exp_path = os.path.join(FIXTURES_DIR, "4_new_category_expenses.csv")

    df_sales_raw = pd.read_csv(sales_path)
    res_s = execute_upload(
        raw_df=df_sales_raw,
        confirmed_mapping={"Date": "date", "Item": "product", "Quantity": "quantity", "Revenue": "revenue"},
        file_type="sales",
        filename="4_new_category_sales.csv",
        tenant_id=TENANT,
    )
    assert res_s.success

    df_exp_raw = pd.read_csv(exp_path)
    res_e = execute_upload(
        raw_df=df_exp_raw,
        confirmed_mapping={"Date": "date", "Category": "category", "Description": "description", "Amount": "amount"},
        file_type="expenses",
        filename="4_new_category_expenses.csv",
        tenant_id=TENANT,
    )
    assert res_e.success

    # Verify Database Totals per Month
    with get_db() as db:
        s_data = [(r.date, r.revenue) for r in db.query(Sales.date, Sales.revenue).filter(Sales.tenant_id == TENANT).all()]
        e_data = [(r.date, r.amount, r.category) for r in db.query(Expenses.date, Expenses.amount, Expenses.category).filter(Expenses.tenant_id == TENANT).all()]

    df_s = pd.DataFrame(s_data, columns=["date", "revenue"])
    df_s["month"] = pd.to_datetime(df_s["date"]).dt.strftime("%Y-%m")
    s_monthly = df_s.groupby("month")["revenue"].sum().to_dict()

    df_e = pd.DataFrame(e_data, columns=["date", "amount", "category"])
    df_e["month"] = pd.to_datetime(df_e["date"]).dt.strftime("%Y-%m")
    e_monthly = df_e.groupby("month")["amount"].sum().to_dict()

    # Jan and Feb numbers as requested by STEP 4:
    # total expenses Jan 23,000 / Feb 28,600, revenue Jan 2,500 / Feb 2,600
    assert e_monthly["2024-01"] == 23000.0
    assert e_monthly["2024-02"] == 28600.0
    assert s_monthly["2024-01"] == 2500.0
    assert s_monthly["2024-02"] == 2600.0

    # Period comparison Feb vs Jan
    comp = compare_periods(TENANT, current_month="2024-02", prior_month="2024-01")
    assert comp is not None

    # Revenue: 2600 vs 2500 -> +4.0%
    assert comp.revenue_delta == 100.0
    assert comp.revenue_delta_pct == 4.0

    # Expenses: 28600 vs 23000 -> +24.35%
    assert comp.expense_delta == 5600.0
    assert comp.expense_delta_pct == 24.35

    # Expense shifts
    shifts = comp.expense_shifts.to_dict("records")
    shift_by_cat = {s["category"]: s for s in shifts}

    # Utilities +20%, Marketing "new"
    assert "Utilities" in shift_by_cat
    assert shift_by_cat["Utilities"]["delta_pct"] == 20.0

    assert "Marketing" in shift_by_cat
    assert shift_by_cat["Marketing"]["delta_pct"] is None  # None represents new

    # PDF generation test
    pdf_bytes = generate_monthly_pdf_report(TENANT, "2024-02")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000

    # AI comparison table test
    df_table, headline = _get_period_comparison_table(TENANT)
    assert not df_table.empty

    # Find Marketing and Utilities rows in the table
    mkt_row = df_table[df_table["Metric"].str.contains("Marketing", case=False, na=False)]
    assert not mkt_row.empty
    assert mkt_row.iloc[0]["% Change"] == "new"

    util_row = df_table[df_table["Metric"].str.contains("Utilities", case=False, na=False)]
    assert not util_row.empty
    assert util_row.iloc[0]["% Change"] == "+20.0%"
