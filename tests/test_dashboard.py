"""
tests/test_dashboard.py
-----------------------
Tests for dashboard service calculations:
- Core KPIs (Revenue, Expenses, Profit, AOV)
- New Step 1.1 additions (Transactions, Units Sold, Category Performance, Quantity Velocity)
- Date range filtering (start_date, end_date)
- Financial trend with expenses
- Code-built takeaway sentences
"""

from datetime import date
import pytest
import pandas as pd

from db.database import get_db, init_db
from db.models import Sales, Expenses, UploadLog
from services.dashboard_service import (
    get_dashboard_data,
    get_revenue_trend,
    get_day_of_week_insights,
    get_slow_movers,
    DashboardData,
)

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
        ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=4, row_count_clean=4)
        db.add(ul)
        db.flush()
        
        # Add Sales with category and quantity
        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), order_id="O1", product="Burger", category="Food", quantity=2, revenue=100),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), order_id="O1", product="Fries", category="Food", quantity=1, revenue=50),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), order_id="O2", product="Burger", category="Food", quantity=2, revenue=100),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), order_id=None, product="Soda", category="Drinks", quantity=1, revenue=20),
        ])
        
        # Add Expenses with descriptions
        db.add_all([
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), category="Food", description="Raw beef and buns", amount=80),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), category="Rent", description="January shop rent", amount=100),
        ])
        
        db.commit()


class TestDashboardService:

    def test_empty_tenant_returns_zeros_and_empty_dfs(self):
        data = get_dashboard_data("empty_tenant")
        
        assert data.total_revenue == 0.0
        assert data.total_expenses == 0.0
        assert data.net_profit == 0.0
        assert data.average_order_value == 0.0
        assert data.total_transactions == 0
        assert data.total_units_sold == 0.0
        
        assert len(data.revenue_trend) == 0
        assert len(data.expense_trend) == 0
        assert len(data.top_products) == 0
        assert len(data.category_performance) == 0
        assert len(data.expense_breakdown) == 0

    def test_kpis_and_volume_calculated_correctly(self):
        _insert_sample_data()
        data = get_dashboard_data(TENANT)
        
        # Revenue: 100 + 50 + 100 + 20 = 270
        assert data.total_revenue == 270.0
        # Expenses: 80 + 100 = 180
        assert data.total_expenses == 180.0
        # Profit: 270 - 180 = 90
        assert data.net_profit == 90.0
        # AOV: 270 / 3 = 90
        assert data.average_order_value == 90.0
        # Transactions: O1, O2, None -> 3
        assert data.total_transactions == 3
        # Units sold: 2 + 1 + 2 + 1 = 6
        assert data.total_units_sold == 6.0

    def test_category_performance_grouping(self):
        _insert_sample_data()
        data = get_dashboard_data(TENANT)
        
        cat_df = data.category_performance
        assert len(cat_df) == 2
        # Food is #1 category
        food_row = cat_df[cat_df["category"] == "Food"].iloc[0]
        assert food_row["revenue"] == 250.0
        assert food_row["units_sold"] == 5.0
        assert food_row["order_count"] == 3
        assert food_row["share_pct"] == pytest.approx(92.6, 0.1)

        drinks_row = cat_df[cat_df["category"] == "Drinks"].iloc[0]
        assert drinks_row["revenue"] == 20.0
        assert drinks_row["units_sold"] == 1.0
        assert drinks_row["share_pct"] == pytest.approx(7.4, 0.1)

    def test_top_and_bottom_products_by_quantity(self):
        _insert_sample_data()
        data = get_dashboard_data(TENANT)

        # Top product by quantity: Burger (4 pcs)
        top_qty = data.top_products_by_qty
        assert top_qty.iloc[0]["product"] == "Burger"
        assert top_qty.iloc[0]["quantity"] == 4.0

        # Bottom products by quantity
        bottom_qty = data.bottom_products_by_qty
        assert len(bottom_qty) == 3
        assert bottom_qty.iloc[0]["quantity"] == 1.0

    def test_date_range_filtering(self):
        _insert_sample_data()
        
        # Filter strictly to 2024-01-02
        filtered = get_dashboard_data(TENANT, start_date="2024-01-02", end_date="2024-01-02")
        
        # Jan 2 has Burger (100) + Soda (20) = 120 revenue
        assert filtered.total_revenue == 120.0
        # Jan 2 has Rent = 100 expenses
        assert filtered.total_expenses == 100.0
        assert filtered.net_profit == 20.0
        # Transactions on Jan 2: O2 + None = 2
        assert filtered.total_transactions == 2
        # Units on Jan 2: 2 + 1 = 3
        assert filtered.total_units_sold == 3.0

    def test_financial_trend_with_expenses(self):
        _insert_sample_data()
        
        daily = get_revenue_trend(TENANT, "daily")
        assert len(daily) == 2
        assert "revenue" in daily.columns
        assert "expenses" in daily.columns
        
        # Day 1: Revenue 150, Expenses 80
        day1 = daily.iloc[0]
        assert day1["label"] == "01 Jan 2024"
        assert day1["revenue"] == 150.0
        assert day1["expenses"] == 80.0

        # Day 2: Revenue 120, Expenses 100
        day2 = daily.iloc[1]
        assert day2["label"] == "02 Jan 2024"
        assert day2["revenue"] == 120.0
        assert day2["expenses"] == 100.0

        # Weekly trend aligns both revenue and expenses
        weekly = get_revenue_trend(TENANT, "weekly")
        assert len(weekly) == 1
        assert weekly.iloc[0]["revenue"] == 270.0
        assert weekly.iloc[0]["expenses"] == 180.0

    def test_code_built_takeaways_exist(self):
        _insert_sample_data()
        data = get_dashboard_data(TENANT)
        
        assert "revenue_trend" in data.takeaways
        assert "category_performance" in data.takeaways
        assert "top_products" in data.takeaways
        assert "product_volume" in data.takeaways
        assert "expense_breakdown" in data.takeaways
        
        assert "Food" in data.takeaways["category_performance"]
        assert "Burger" in data.takeaways["top_products"]
        assert "Rent" in data.takeaways["expense_breakdown"]

    def test_day_of_week_insights_calculation(self):
        # Empty tenant returns None
        assert get_day_of_week_insights("empty_tenant") is None

        _insert_sample_data()
        insight = get_day_of_week_insights(TENANT)

        assert insight is not None
        assert "days" in insight
        assert len(insight["days"]) == 7

        # Mon 2024-01-01: 150 revenue; Tue 2024-01-02: 120 revenue
        assert insight["best_day"] == "Monday"
        assert insight["lowest_day"] == "Tuesday"
        assert insight["best_avg_revenue"] == 150.0
        assert insight["lowest_avg_revenue"] == 120.0

        # Headline verification
        assert "Mondays earn +25.0% more than Tuesdays" in insight["headline"]
        assert "headline" in insight
        assert "weekend_headline" in insight

        # Date filter check
        filtered_dow = get_day_of_week_insights(TENANT, start_date="2024-01-02", end_date="2024-01-02")
        assert filtered_dow is not None
        assert filtered_dow["best_day"] == "Tuesday"

    def test_slow_movers_velocity_and_recommendations(self):
        # Empty tenant returns empty list
        assert get_slow_movers("empty_tenant") == []

        _insert_sample_data()

        # Add an older item to trigger "Stalled" status (last sold > 30 days before 2024-01-02)
        with get_db() as db:
            ul = db.query(UploadLog).filter_by(tenant_id=TENANT).first()
            db.add(
                Sales(
                    tenant_id=TENANT,
                    upload_id=ul.id,
                    date=date(2023, 11, 1),
                    order_id="OLD1",
                    product="Old Salad",
                    category="Food",
                    quantity=1,
                    revenue=40,
                )
            )
            db.commit()

        slow = get_slow_movers(TENANT, limit=10)
        assert len(slow) == 4

        # Verify old item is flagged as Stalled
        stalled_item = next(item for item in slow if item["product"] == "Old Salad")
        assert stalled_item["status"] == "Stalled"
        assert stalled_item["days_since_last_sale"] > 30
        assert "30+ days" in stalled_item["recommendation"]

        # Results must be ordered by velocity ascending
        assert slow[0]["weekly_velocity"] <= slow[-1]["weekly_velocity"]

        # Dashboard data also exposes both fields
        data = get_dashboard_data(TENANT)
        assert data.day_of_week_insight is not None
        assert len(data.slow_movers) == 4
