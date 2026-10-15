"""
services/target_service.py
--------------------------
Calculates monthly revenue targets, real-time pacing, and month-end projections.

PRINCIPLES (never break these):
1. The LLM never calculates. All numbers come strictly from Python/SQL.
2. Every number is checkable: headlines are built in code.
3. tenant_id comes only from the signed session, never from the request.
"""

import calendar
from datetime import date, datetime
import re
from typing import Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy import func

from db.database import get_db
from db.models import RevenueTarget, Sales

MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validate_month_string(month_str: str) -> None:
    if not month_str or not MONTH_REGEX.match(month_str.strip()):
        raise ValueError(f"Invalid month '{month_str}'. Must be formatted as YYYY-MM (e.g. '2026-09').")


def set_monthly_target(tenant_id: str, month: str, target_amount: float) -> dict[str, Any]:
    """
    Upsert a monthly revenue target for a tenant.
    """
    clean_month = month.strip()
    validate_month_string(clean_month)

    try:
        val = float(target_amount)
    except (ValueError, TypeError):
        raise ValueError("Target amount must be a valid positive number.")

    if val <= 0:
        raise ValueError("Target amount must be greater than zero.")

    with get_db() as db:
        existing = (
            db.query(RevenueTarget)
            .filter(RevenueTarget.tenant_id == tenant_id, RevenueTarget.month == clean_month)
            .first()
        )
        if existing:
            existing.target_amount = round(val, 2)
            existing.updated_at = datetime.utcnow()
        else:
            new_target = RevenueTarget(
                tenant_id=tenant_id,
                month=clean_month,
                target_amount=round(val, 2),
            )
            db.add(new_target)
        db.commit()

    return get_target_pacing(tenant_id, month=clean_month) or {}


def delete_monthly_target(tenant_id: str, month: str) -> bool:
    """
    Remove a monthly target if the owner wishes to reset it.
    """
    clean_month = month.strip()
    validate_month_string(clean_month)

    with get_db() as db:
        target = (
            db.query(RevenueTarget)
            .filter(RevenueTarget.tenant_id == tenant_id, RevenueTarget.month == clean_month)
            .first()
        )
        if target:
            db.delete(target)
            db.commit()
            return True
        return False


def get_target_pacing(tenant_id: str, month: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    Calculate target pacing, progress, projected month-end revenue, and daily run-rate needed.
    Anchors days elapsed to the tenant's latest sales transaction.
    """
    with get_db() as db:
        anchor_date = db.query(func.max(Sales.date)).filter(Sales.tenant_id == tenant_id).scalar()

        # If month not provided, default to anchor_date's month or current month
        if not month:
            if anchor_date:
                active_month = anchor_date.strftime("%Y-%m")
            else:
                active_month = datetime.utcnow().strftime("%Y-%m")
        else:
            active_month = month.strip()
            validate_month_string(active_month)

        target_row = (
            db.query(RevenueTarget)
            .filter(RevenueTarget.tenant_id == tenant_id, RevenueTarget.month == active_month)
            .first()
        )

        target_amount = float(target_row.target_amount) if target_row else None

        year, mon = int(active_month[:4]), int(active_month[5:7])
        month_start = date(year, mon, 1)
        days_in_month = calendar.monthrange(year, mon)[1]
        month_end = date(year, mon, days_in_month)

        # Calculate actual revenue earned in that month
        actual_rev = (
            db.query(func.coalesce(func.sum(Sales.revenue), 0.0))
            .filter(
                Sales.tenant_id == tenant_id,
                Sales.date >= month_start,
                Sales.date <= month_end,
            )
            .scalar()
        )
        current_revenue = float(round(actual_rev or 0.0, 2))

    if target_amount is None:
        return {
            "has_target": False,
            "month": active_month,
            "month_label": date(year, mon, 1).strftime("%B %Y"),
            "target_amount": 0.0,
            "current_revenue": current_revenue,
            "progress_pct": 0.0,
            "days_in_month": days_in_month,
            "days_elapsed": 0,
            "days_remaining": days_in_month,
            "expected_pace_amount": 0.0,
            "pace_difference": 0.0,
            "pace_pct": 0.0,
            "pace_status": "none",
            "projected_revenue": 0.0,
            "daily_needed_remaining": 0.0,
            "headline": f"No revenue target set for {date(year, mon, 1).strftime('%B %Y')}.",
        }

    # Determine days elapsed
    if anchor_date:
        if anchor_date.year == year and anchor_date.month == mon:
            days_elapsed = min(days_in_month, max(1, anchor_date.day))
        elif date(year, mon, 1) < date(anchor_date.year, anchor_date.month, 1):
            days_elapsed = days_in_month
        else:
            days_elapsed = 0
    else:
        today = date.today()
        if today.year == year and today.month == mon:
            days_elapsed = min(days_in_month, max(1, today.day))
        elif date(year, mon, 1) < date(today.year, today.month, 1):
            days_elapsed = days_in_month
        else:
            days_elapsed = 0

    days_remaining = max(0, days_in_month - days_elapsed)
    progress_pct = round((current_revenue / target_amount) * 100.0, 1) if target_amount > 0 else 0.0

    # Expected pace amount
    expected_pace_amount = round((target_amount / days_in_month) * days_elapsed, 2)
    pace_diff = round(current_revenue - expected_pace_amount, 2)
    pace_pct = (
        round(((current_revenue - expected_pace_amount) / expected_pace_amount) * 100.0, 1)
        if expected_pace_amount > 0
        else 0.0
    )

    # Status classification
    if current_revenue >= target_amount:
        pace_status = "achieved"
    elif current_revenue >= expected_pace_amount:
        pace_status = "ahead"
    elif current_revenue >= expected_pace_amount * 0.85:
        pace_status = "on_track"
    else:
        pace_status = "behind"

    # Month-end projection
    if days_elapsed > 0:
        daily_velocity = current_revenue / days_elapsed
        projected_revenue = round(daily_velocity * days_in_month, 2)
    else:
        projected_revenue = current_revenue

    # Daily run-rate needed
    remaining_to_target = max(0.0, target_amount - current_revenue)
    if days_remaining > 0:
        daily_needed_remaining = round(remaining_to_target / days_remaining, 2)
    else:
        daily_needed_remaining = 0.0

    month_name = date(year, mon, 1).strftime("%B %Y")

    # Code-built headline (Principle 1 & 2)
    if pace_status == "achieved":
        headline = (
            f"Target achieved! You have generated ₹{current_revenue:,.2f} against your ₹{target_amount:,.2f} "
            f"goal ({progress_pct}% completed) with {days_remaining} days left in {month_name}."
        )
    elif pace_status == "ahead":
        headline = (
            f"Ahead of pace: You have achieved ₹{current_revenue:,.2f} ({progress_pct}%) of your ₹{target_amount:,.2f} "
            f"goal with {days_remaining} days remaining. On track to reach ₹{projected_revenue:,.2f}."
        )
    elif pace_status == "on_track":
        headline = (
            f"On track: You've earned ₹{current_revenue:,.2f} ({progress_pct}%) of your ₹{target_amount:,.2f} "
            f"target. Maintain ₹{daily_needed_remaining:,.2f}/day over the next {days_remaining} days to reach your goal."
        )
    else:
        headline = (
            f"Behind pace: You've reached ₹{current_revenue:,.2f} ({progress_pct}%) of your ₹{target_amount:,.2f} "
            f"target with {days_remaining} days left. You need ₹{daily_needed_remaining:,.2f}/day to hit your goal."
        )

    return {
        "has_target": True,
        "month": active_month,
        "month_label": month_name,
        "target_amount": target_amount,
        "current_revenue": current_revenue,
        "progress_pct": progress_pct,
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "expected_pace_amount": expected_pace_amount,
        "pace_difference": pace_diff,
        "pace_pct": pace_pct,
        "pace_status": pace_status,
        "projected_revenue": projected_revenue,
        "daily_needed_remaining": daily_needed_remaining,
        "headline": headline,
    }
