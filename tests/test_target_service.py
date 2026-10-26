"""
tests/test_target_service.py
-----------------------------
Unit tests for monthly revenue targets, real-time pacing calculations,
projections, and safe schema upserts.
"""

from datetime import date
import pytest

from db.database import get_db, init_db
from db.models import RevenueTarget, Sales, UploadLog
from services.target_service import (
    delete_monthly_target,
    get_target_pacing,
    set_monthly_target,
)

TENANT = "test_target_tenant"


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db() as db:
        db.query(RevenueTarget).filter_by(tenant_id=TENANT).delete()
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(UploadLog).filter_by(tenant_id=TENANT).delete()
        db.commit()

    yield

    with get_db() as db:
        db.query(RevenueTarget).filter_by(tenant_id=TENANT).delete()
        db.query(Sales).filter_by(tenant_id=TENANT).delete()
        db.query(UploadLog).filter_by(tenant_id=TENANT).delete()
        db.commit()


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError, match="Invalid month"):
        set_monthly_target(TENANT, "2024-13", 1000.0)

    with pytest.raises(ValueError, match="Invalid month"):
        set_monthly_target(TENANT, "invalid-date", 1000.0)

    with pytest.raises(ValueError, match="greater than zero"):
        set_monthly_target(TENANT, "2024-01", 0.0)

    with pytest.raises(ValueError, match="greater than zero"):
        set_monthly_target(TENANT, "2024-01", -500.0)


def test_empty_tenant_has_no_target():
    pacing = get_target_pacing(TENANT, month="2024-01")
    assert pacing is not None
    assert pacing["has_target"] is False
    assert pacing["target_amount"] == 0.0
    assert pacing["current_revenue"] == 0.0
    assert pacing["days_in_month"] == 31


def test_set_and_update_monthly_target():
    res = set_monthly_target(TENANT, "2024-01", 50000.0)
    assert res["has_target"] is True
    assert res["target_amount"] == 50000.0
    assert res["month"] == "2024-01"

    # Updating target (upsert)
    updated = set_monthly_target(TENANT, "2024-01", 60000.0)
    assert updated["has_target"] is True
    assert updated["target_amount"] == 60000.0


def test_pacing_ahead_and_behind_calculations():
    # Insert sales records for Jan 1 and Jan 2, 2024
    with get_db() as db:
        ul = UploadLog(tenant_id=TENANT, filename="test.csv", file_type="sales", row_count_raw=2, row_count_clean=2)
        db.add(ul)
        db.flush()

        db.add_all([
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 1), product="Coffee", quantity=5, revenue=500.0),
            Sales(tenant_id=TENANT, upload_id=ul.id, date=date(2024, 1, 2), product="Pastry", quantity=5, revenue=500.0),
        ])
        db.commit()

    # Total revenue for Jan 2024 is 1000.0, anchor date is Jan 2 (days_elapsed = 2, days_in_month = 31)

    # Case 1: Target = 3100. Expected pace by day 2 is (3100 / 31) * 2 = 200. Actual = 1000 > 200 => Ahead
    ahead_pacing = set_monthly_target(TENANT, "2024-01", 3100.0)
    assert ahead_pacing["current_revenue"] == 1000.0
    assert ahead_pacing["days_elapsed"] == 2
    assert ahead_pacing["expected_pace_amount"] == 200.0
    assert ahead_pacing["pace_status"] == "ahead"
    assert ahead_pacing["projected_revenue"] == (1000.0 / 2) * 31  # 15,500.0
    assert "Ahead of pace" in ahead_pacing["headline"]

    # Case 2: Target = 31000. Expected pace by day 2 is 2000 > actual 1000 => Behind
    behind_pacing = set_monthly_target(TENANT, "2024-01", 31000.0)
    assert behind_pacing["pace_status"] == "behind"
    assert "Behind pace" in behind_pacing["headline"]
    assert behind_pacing["daily_needed_remaining"] > 0

    # Case 3: Target achieved (target = 800 <= current 1000)
    achieved_pacing = set_monthly_target(TENANT, "2024-01", 800.0)
    assert achieved_pacing["pace_status"] == "achieved"
    assert "Target achieved" in achieved_pacing["headline"]


def test_delete_monthly_target():
    set_monthly_target(TENANT, "2024-01", 10000.0)
    pacing = get_target_pacing(TENANT, "2024-01")
    assert pacing["has_target"] is True

    deleted = delete_monthly_target(TENANT, "2024-01")
    assert deleted is True

    # Pacing now has has_target = False
    pacing_after = get_target_pacing(TENANT, "2024-01")
    assert pacing_after["has_target"] is False
