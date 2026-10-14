"""
tests/test_dashboard.py
-----------------------
Tests for the dashboard service logic.

Verifies that KPIs (Total Revenue, Expenses, Net Profit, AOV) and 
chart data groupings are calculated correctly directly from the database.
"""

from datetime import date
import pytest
import pandas as pd

from db.database import get_db, init_db
from db.models import Sales, Expenses, UploadLog
from services.dashboard_service import get_dashboard_data, get_revenue_trend, DashboardData

TENANT = "test_tenant_dash"

@pytest.fixture(autouse=True)
def setup_db():
    """Initialize DB and clean up tenant data before and after each test."""
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


def _insert_sample_data():
    with get_db() as db:
        # Create an upload log to satisfy the foreign key constraint
        ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=4, row_count_clean=4)
        db.add(ul)
        db.flush()
        
        # Add Sales
        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), order_id="O1", product="Burger", revenue=100),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), order_id="O1", product="Fries", revenue=50),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), order_id="O2", product="Burger", revenue=100),
            # No order ID on this one
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), order_id=None, product="Soda", revenue=20),
        ])
        
        # Add Expenses
        db.add_all([
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), category="Food", amount=80),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), category="Rent", amount=100),
        ])
        
        db.commit()

class TestDashboardService:

    def test_empty_tenant_returns_zeros(self):
        data = get_dashboard_data("empty_tenant")
        
        assert data.total_revenue == 0.0
        assert data.total_expenses == 0.0
        assert data.net_profit == 0.0
        assert data.average_order_value == 0.0
        
        assert len(data.revenue_trend) == 0
        assert len(data.top_products) == 0
        assert len(data.expense_breakdown) == 0

    def test_kpis_calculated_correctly(self):
        _insert_sample_data()
        data = get_dashboard_data(TENANT)
        
        # Total Revenue: 100 + 50 + 100 + 20 = 270
        assert data.total_revenue == 270.0
        
        # Total Expenses: 80 + 100 = 180
        assert data.total_expenses == 180.0
        
        # Net Profit: 270 - 180 = 90
        assert data.net_profit == 90.0
        
        # AOV: 
        # Orders: O1 (150), O2 (100), None (20) -> 3 distinct orders
        # Total Revenue (270) / 3 orders = 90
        assert data.average_order_value == 90.0

    def test_chart_data_groupings(self):
        _insert_sample_data()
        data = get_dashboard_data(TENANT)
        
        # Top Products: Burger (200), Fries (50), Soda (20)
        assert len(data.top_products) == 3
        # Ensure it's sorted descending
        assert data.top_products.iloc[0]["product"] == "Burger"
        assert data.top_products.iloc[0]["revenue"] == 200.0
        
        # Expense Breakdown: Food (80), Rent (100)
        assert len(data.expense_breakdown) == 2
        food_expense = data.expense_breakdown[data.expense_breakdown["category"] == "Food"].iloc[0]["amount"]
        assert food_expense == 80.0
        
        # Revenue Trend: 2024-01-01 (150), 2024-01-02 (120)
        assert len(data.revenue_trend) == 2
        rev_jan1 = data.revenue_trend[data.revenue_trend["date"] == date(2024, 1, 1)].iloc[0]["revenue"]
        assert rev_jan1 == 150.0

    def test_revenue_trend_service_granularities(self):
        _insert_sample_data()
        
        # 1. Daily trend
        daily = get_revenue_trend(TENANT, "daily")
        assert len(daily) == 2
        assert daily.iloc[0]["label"] == "01 Jan 2024"
        assert daily.iloc[0]["revenue"] == 150.0

        # 2. Weekly ISO trend (2024-01-01 was Monday, ISO week 1 of 2024)
        weekly = get_revenue_trend(TENANT, "weekly")
        assert len(weekly) == 1
        assert weekly.iloc[0]["label"] == "W01 2024"
        assert weekly.iloc[0]["revenue"] == 270.0

        # 3. Monthly trend
        monthly = get_revenue_trend(TENANT, "monthly")
        assert len(monthly) == 1
        assert monthly.iloc[0]["label"] == "Jan 2024"
        assert monthly.iloc[0]["revenue"] == 270.0

    def test_revenue_trend_invalid_granularity(self):
        with pytest.raises(ValueError, match="Unsupported granularity"):
            get_revenue_trend(TENANT, "yearly")

