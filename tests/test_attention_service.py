"""
tests/test_attention_service.py
-------------------------------
Unit tests for the Decision Support Engine: "What Needs Your Attention".
Tests the 5 core rules, 30-day stalled product logic, ranking, and healthy states.
"""

from datetime import date, timedelta
import pytest

from db.database import get_db, init_db
from db.models import Sales, Expenses, UploadLog
from services.attention_service import (
    check_profit_drop,
    check_expense_faster_than_revenue,
    check_biggest_expense_jump,
    check_stalled_products,
    check_recent_anomalies,
    get_attention_items,
    _get_tenant_anchor_date,
)

TENANT = "test_tenant_attention"


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(Expenses).filter_by(tenant_id=TENANT).delete()
        db.query(UploadLog).filter_by(tenant_id=TENANT).delete()

        ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=1, row_count_clean=1)
        db.add(ul)
        db.flush()

        # Month 1: January 2024 (Prior Month)
        # Revenue = 1,000, Expenses = 200, Profit = 800
        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 5), product="Burger", revenue=600, quantity=6),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), product="Salad", revenue=400, quantity=4),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 10), category="Supplies", amount=150, description="Monthly supplies"),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 15), category="Utilities", amount=50, description="Power bill"),
        ])

        # Month 2: February 2024 (Current Month)
        # Revenue = 900 (down -10%), Expenses = 500 (up +150%), Profit = 400 (down -50%)
        # "Salad" not sold at all in February (stalled product)
        # "Utilities" jumped from 50 to 250 (+400% surge, outpacing revenue drop)
        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 5), product="Burger", revenue=500, quantity=5),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 18), product="Burger", revenue=400, quantity=4),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 10), category="Supplies", amount=250, description="Restock supplies"),
            Expenses(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 2, 15), category="Utilities", amount=250, description="Extreme power surge"),
        ])
        db.commit()


def test_anchor_date():
    anchor = _get_tenant_anchor_date(TENANT)
    assert anchor == date(2024, 2, 18)


def test_profit_drop_rule():
    item = check_profit_drop(TENANT)
    assert item is not None
    assert item.id == "profit_drop"
    assert "Profit Dropped" in item.title
    assert "Net profit shifted by" in item.message
    assert item.action_tab == "diagnostics"
    assert item.severity in ("critical", "warning")


def test_expense_faster_than_revenue_rule():
    item = check_expense_faster_than_revenue(TENANT)
    assert item is not None
    assert "Outpacing Revenue" in item.title
    assert item.action_tab == "comparison"
    assert "outpacing your revenue growth" in item.message


def test_biggest_expense_jump_rule():
    item = check_biggest_expense_jump(TENANT)
    assert item is not None
    assert "Cost Surge" in item.title
    assert item.action_tab == "comparison"
    assert item.severity in ("warning", "info")


def test_stalled_products_rule():
    # In setup_db, "Salad" was sold in January (date <= 2024-01-18)
    # Anchor date is 2024-02-18, so cutoff is 2024-01-19.
    # In the 30 days prior to Feb 18, only "Burger" was sold. "Salad" had 0 sales.
    item = check_stalled_products(TENANT)
    assert item is not None
    assert item.id == "stalled_products"
    assert "Not Sold in 30 Days" in item.title
    assert "'Salad'" in item.message
    assert item.action_tab == "overview"


def test_get_attention_items_ranked():
    items = get_attention_items(TENANT, limit=5)
    assert len(items) >= 2
    assert len(items) <= 5

    # Check that highest severity or score items are ordered first
    first_item = items[0]
    assert first_item["severity"] in ("critical", "warning")

    # Verify all expected dictionary keys
    for it in items:
        assert "id" in it
        assert "title" in it
        assert "message" in it
        assert "severity" in it
        assert "action_tab" in it
        assert "action_label" in it


def test_attention_items_all_clear_when_healthy():
    EMPTY_TENANT = "healthy_tenant_clean"
    with get_db() as db:
        db.query(Sales).filter_by(tenant_id=EMPTY_TENANT).delete()
        db.query(Expenses).filter_by(tenant_id=EMPTY_TENANT).delete()

    items = get_attention_items(EMPTY_TENANT)
    assert len(items) == 1
    assert items[0]["id"] == "all_clear"
    assert "Healthy" in items[0]["title"]
