"""
tests/test_analytics.py
-----------------------
Unit tests for the advanced analytics service (Phase 5).
Verifies:
1. Period-over-period comparison (MoM, WoW, delta calculations, product/expense shifts).
2. Statistical anomaly detection (spikes, drops, severity, rolling baselines).
3. Root cause profit drop and margin diagnostics (attribution, waterfall breakdown).
"""

from datetime import date
import pytest
import pandas as pd

from db.database import get_db, init_db
from db.models import Sales, Expenses, UploadLog
from services.analytics_service import (
    get_available_months,
    get_month_data_availability,
    get_complete_months,
    compare_periods,
    detect_anomalies,
    diagnose_profit_drop,
    PeriodComparison,
    AnomalyReport,
    ProfitDiagnosis,
)

TENANT = "test_tenant_analytics"


@pytest.fixture(autouse=True)
def setup_db():
    """Initialize DB and isolate tenant data before and after each test."""
    init_db()
    with get_db() as db:
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(Expenses).filter_by(tenant_id=TENANT).delete()
        db.query(UploadLog).filter_by(tenant_id=TENANT).delete()
        db.commit()

    yield

    with get_db() as db:
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(Expenses).filter_by(tenant_id=TENANT).delete()
        db.query(UploadLog).filter_by(tenant_id=TENANT).delete()
        db.commit()


def _seed_two_month_data():
    """Seeds two months: Jan 2024 (good) and Feb 2024 (profit drop)."""
    with get_db() as db:
        ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=10, row_count_clean=10)
        db.add(ul)
        db.flush()

        # Month 1 (January 2024):
        # Revenue: Burger (1000) + Fries (500) = 1500
        # Expenses: Rent (400) + Raw Materials (200) = 600
        # Net profit = 900
        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 5), order_id="O1", product="Burger", revenue=600),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), order_id="O2", product="Burger", revenue=400),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 15), order_id="O3", product="Fries", revenue=500),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), category="Rent", amount=400),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 15), category="Raw Materials", amount=200),
        ])

        # Month 2 (February 2024):
        # Revenue: Burger drops to 300 (-700), Fries stays at 500 = 800 (Total Rev = 800, -700)
        # Expenses: Rent (400) + Raw Materials surges to 600 (+400) = 1000 (Total Exp = 1000, +400)
        # Net profit = 800 - 1000 = -200 (Drop = -1100)
        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 5), order_id="O4", product="Burger", revenue=300),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 12), order_id="O5", product="Fries", revenue=500),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 1), category="Rent", amount=400),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 15), category="Raw Materials", amount=600),
        ])
        db.commit()


class TestAnalyticsService:

    def test_available_months_empty(self):
        months = get_available_months("non_existent_tenant")
        assert months == []

    def test_available_months_populated(self):
        _seed_two_month_data()
        months = get_available_months(TENANT)
        assert months == ["2024-01", "2024-02"]

    def test_compare_periods_empty_tenant(self):
        result = compare_periods("empty_tenant")
        assert result is None

    def test_compare_periods_calculation(self):
        _seed_two_month_data()
        comp = compare_periods(TENANT, current_month="2024-02", prior_month="2024-01")
        assert comp is not None

        # Prior (Jan): Rev = 1500, Exp = 600, Profit = 900
        assert comp.prior.revenue == 1500.0
        assert comp.prior.expenses == 600.0
        assert comp.prior.net_profit == 900.0
        assert comp.prior.order_count == 3
        assert comp.prior.average_order_value == 500.0

        # Current (Feb): Rev = 800, Exp = 1000, Profit = -200
        assert comp.current.revenue == 800.0
        assert comp.current.expenses == 1000.0
        assert comp.current.net_profit == -200.0
        assert comp.current.order_count == 2
        assert comp.current.average_order_value == 400.0

        # Deltas
        assert comp.revenue_delta == -700.0
        assert comp.expense_delta == 400.0
        assert comp.profit_delta == -1100.0
        assert comp.aov_delta == -100.0

        # Product Shifts
        assert len(comp.top_decliners) >= 1
        burger_decliner = [d for d in comp.top_decliners if d["product"] == "Burger"][0]
        assert burger_decliner["delta"] == -700.0
        assert burger_decliner["prior_revenue"] == 1000.0
        assert burger_decliner["current_revenue"] == 300.0

        # Expense shifts
        exp_df = comp.expense_shifts
        rm_row = exp_df[exp_df["category"] == "Raw Materials"].iloc[0]
        assert rm_row["delta"] == 400.0

    def test_diagnose_profit_drop_root_cause(self):
        _seed_two_month_data()
        diag = diagnose_profit_drop(TENANT, current_month="2024-02", prior_month="2024-01")
        assert diag is not None

        assert diag.is_profit_down is True
        assert diag.profit_change == -1100.0
        assert "Dual Drag" in diag.primary_driver

        # Check top revenue drag
        assert len(diag.top_revenue_drags) >= 1
        assert diag.top_revenue_drags[0]["product"] == "Burger"
        assert diag.top_revenue_drags[0]["drop_amount"] == 700.0

        # Check top expense surge
        assert len(diag.top_expense_surges) >= 1
        assert diag.top_expense_surges[0]["category"] == "Raw Materials"
        assert diag.top_expense_surges[0]["increase_amount"] == 400.0

        # Check insights and recommendations
        assert len(diag.key_insights) > 0
        assert len(diag.recommendations) > 0

        # Check waterfall data
        assert len(diag.waterfall_df) == 4
        measures = list(diag.waterfall_df["measure"])
        assert measures == ["absolute", "relative", "relative", "total"]

    def test_detect_anomalies_empty_data(self):
        report = detect_anomalies("empty_tenant")
        assert report.total_anomalies == 0
        assert len(report.revenue_anomalies) == 0

    def test_detect_anomalies_with_spike_and_drop(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=10, row_count_clean=10)
            db.add(ul)
            db.flush()

            # Create 10 normal days with revenue around 100
            for d in range(1, 11):
                db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 3, d), product="Item", revenue=100.0))

            # Add an extreme spike on day 12 (revenue = 1000)
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 3, 12), product="Item", revenue=1000.0))
            db.commit()

        report = detect_anomalies(TENANT, sensitivity=2.0)
        assert report.total_anomalies >= 1
        assert len(report.revenue_anomalies) >= 1

        spike = [a for a in report.revenue_anomalies if a.anomaly_type == "spike"][0]
        assert spike.date == date(2024, 3, 12)
        assert spike.actual_value == 1000.0
        assert spike.z_score >= 2.0

    def test_detect_anomalies_drop(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=10, row_count_clean=10)
            db.add(ul)
            db.flush()

            for d in range(1, 15):
                db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 4, d), product="Item", revenue=500.0))
            # Sudden drop to 10 on day 15
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 4, 15), product="Item", revenue=10.0))
            db.commit()

        report = detect_anomalies(TENANT, sensitivity=2.0)
        drops = [a for a in report.revenue_anomalies if a.anomaly_type == "drop"]
        assert len(drops) >= 1
        assert drops[0].actual_value == 10.0

    def test_detect_expense_anomalies_includes_descriptions(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test_exp.csv", file_type="expenses", row_count_raw=10, row_count_clean=10)
            db.add(ul)
            db.flush()

            # Normal expense days
            for d in range(1, 10):
                db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 5, d), category="Supplies", description="Daily milk", amount=50.0))

            # Major expense spike on day 10
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 5, 10), category="Equipment", description="New Espresso Machine", amount=2500.0))
            db.commit()

        report = detect_anomalies(TENANT, sensitivity=2.0)
        assert len(report.expense_anomalies) >= 1
        spike = report.expense_anomalies[0]
        assert "New Espresso Machine" in spike.description
        assert len(spike.expense_details) >= 1
        assert spike.expense_details[0]["description"] == "New Espresso Machine"
        assert spike.expense_details[0]["category"] == "Equipment"
        assert spike.expense_details[0]["amount"] == 2500.0

    def test_diagnose_profit_growth(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=4, row_count_clean=4)
            db.add(ul)
            db.flush()

            # Jan: Rev 500, Exp 400, Profit 100
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), product="Item", revenue=500.0))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), category="Rent", amount=400.0))

            # Feb: Rev 1000, Exp 300, Profit 700 (Profit up +600)
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), product="Item", revenue=1000.0))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), category="Rent", amount=300.0))
            db.commit()

        diag = diagnose_profit_drop(TENANT, current_month="2024-02", prior_month="2024-01")
        assert diag is not None
        assert diag.is_profit_down is False
        assert diag.profit_change == 600.0
        assert "Expansion" in diag.primary_driver or "Growth" in diag.primary_driver
        assert len(diag.key_insights) > 0

    def test_month_availability_and_complete_months(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=3, row_count_clean=3)
            db.add(ul)
            db.flush()
            # Jan 2024: sales only
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), product="A", revenue=100))
            # Feb 2024: expenses only
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), category="Rent", amount=100))
            # Mar 2024: both
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 3, 10), product="A", revenue=200))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 3, 10), category="Rent", amount=50))
            db.commit()

        avail = get_month_data_availability(TENANT)
        assert avail["2024-01"] == {"has_sales": True, "has_expenses": False, "has_both": False}
        assert avail["2024-02"] == {"has_sales": False, "has_expenses": True, "has_both": False}
        assert avail["2024-03"] == {"has_sales": True, "has_expenses": True, "has_both": True}

        complete = get_complete_months(TENANT)
        assert complete == ["2024-03"]

    def test_compare_periods_rejects_invalid_month_format(self):
        with pytest.raises(ValueError, match="Invalid month format"):
            compare_periods(TENANT, current_month="2024-13")

        with pytest.raises(ValueError, match="Invalid month format"):
            compare_periods(TENANT, current_month="invalid")

    def test_compare_periods_rejects_month_with_only_sales(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=3, row_count_clean=3)
            db.add(ul)
            db.flush()
            # Jan: sales only
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), product="A", revenue=100))
            # Feb: both
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), product="A", revenue=200))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), category="Rent", amount=50))
            db.commit()

        with pytest.raises(ValueError, match="only has sales data"):
            compare_periods(TENANT, current_month="2024-02", prior_month="2024-01")

    def test_compare_periods_rejects_month_with_only_expenses(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="expenses", row_count_raw=3, row_count_clean=3)
            db.add(ul)
            db.flush()
            # Jan: expenses only
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), category="Rent", amount=100))
            # Feb: both
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), product="A", revenue=200))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), category="Rent", amount=50))
            db.commit()

        with pytest.raises(ValueError, match="only has expense data"):
            compare_periods(TENANT, current_month="2024-02", prior_month="2024-01")

    def test_compare_periods_auto_selects_only_complete_months(self):
        with get_db() as db:
            ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=5, row_count_clean=5)
            db.add(ul)
            db.flush()
            # Jan: sales only
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), product="A", revenue=100))
            # Feb: both
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), product="A", revenue=200))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), category="Rent", amount=50))
            # Mar: both
            db.add(Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 3, 10), product="A", revenue=300))
            db.add(Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 3, 10), category="Rent", amount=70))
            db.commit()

        comp = compare_periods(TENANT)
        assert comp is not None
        assert comp.current.period_label == "2024-03"
        assert comp.prior.period_label == "2024-02"

