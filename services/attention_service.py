"""
services/attention_service.py
-----------------------------
Decision Support Engine: "What Needs Your Attention".
Built entirely in Python/SQL code from existing analytical results (Principle 1 & 2).

Evaluates 5 critical business signals:
  1. Profit Drop: Profit shifted downward and identifies primary root-cause driver.
  2. Expense Growing Faster Than Revenue: Expense category % growth outpaces revenue growth.
  3. Biggest Expense Jump: Single expense category with largest absolute cost increase.
  4. Stalled Products: Catalog items with zero sales in the last 30 days (relative to tenant anchor date).
  5. Statistical Anomalies: Unusually severe revenue drops or expense spikes.

Ranks items by severity and impact score (max 5 items).
"""

from dataclasses import dataclass, asdict
from datetime import date, timedelta
import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import func

from db.database import get_db
from db.models import Sales, Expenses
from services.analytics_service import (
    compare_periods,
    detect_anomalies,
    diagnose_profit_drop,
    get_complete_months,
)

logger = logging.getLogger(__name__)


@dataclass
class AttentionItem:
    id: str
    title: str
    message: str
    severity: str  # "critical" | "warning" | "info"
    action_tab: str  # "overview" | "comparison" | "anomalies" | "diagnostics"
    action_label: str
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_tenant_anchor_date(tenant_id: str) -> Optional[date]:
    """Return the most recent date recorded in sales or expenses for this tenant."""
    with get_db() as db:
        max_s = db.query(func.max(Sales.date)).filter(Sales.tenant_id == tenant_id).scalar()
        max_e = db.query(func.max(Expenses.date)).filter(Expenses.tenant_id == tenant_id).scalar()
    valid_dates = [d for d in (max_s, max_e) if d is not None]
    return max(valid_dates) if valid_dates else None


def check_profit_drop(tenant_id: str) -> Optional[AttentionItem]:
    """Check if latest month experienced a net profit drop and identify its driver."""
    try:
        diag = diagnose_profit_drop(tenant_id)
        if not diag or not diag.is_profit_down:
            return None

        drop_val = abs(diag.profit_change)
        drop_pct = abs(diag.profit_change_pct)
        driver = diag.primary_driver or "rising expenses or lower sales volume"

        severity = "critical" if drop_pct >= 15.0 or drop_val >= 5000.0 else "warning"
        score = 100.0 + min(50.0, drop_pct)

        return AttentionItem(
            id="profit_drop",
            title="Profit Dropped vs Prior Month",
            message=(
                f"Net profit shifted by -₹{drop_val:,.2f} ({diag.profit_change_pct:+.1f}%), "
                f"primarily driven by {driver}."
            ),
            severity=severity,
            action_tab="diagnostics",
            action_label="Investigate Profit Shift",
            score=score,
        )
    except Exception as exc:
        logger.debug(f"check_profit_drop skipped: {exc}")
        return None


def check_expense_faster_than_revenue(tenant_id: str) -> Optional[AttentionItem]:
    """Check if any expense category percentage growth outpaces revenue growth."""
    try:
        comp = compare_periods(tenant_id)
        if not comp or comp.prior.period_label == "None":
            return None

        rev_growth = comp.revenue_delta_pct
        rev_growth_val = float(rev_growth) if rev_growth is not None else 0.0
        rev_growth_str = f"{rev_growth:+.1f}%" if rev_growth is not None else "new"
        worst_category = None
        max_gap = 0.0
        worst_cat_growth = 0.0
        worst_cat_amount = 0.0

        shifts = (
            comp.expense_shifts.to_dict("records")
            if isinstance(comp.expense_shifts, pd.DataFrame)
            else (comp.expense_shifts or [])
        )

        for shift in shifts:
            cat = str(shift.get("category", ""))
            raw_pct = shift.get("delta_pct") if shift.get("delta_pct") is not None else shift.get("change_pct", 0.0)
            raw_change = shift.get("delta") if shift.get("delta") is not None else shift.get("change", 0.0)
            cat_growth = float(raw_pct or 0.0)
            cat_amount = float(shift.get("current_amount", 0.0))
            change = float(raw_change or 0.0)

            if change > 0 and (cat_growth - rev_growth_val) > 10.0:
                gap = cat_growth - rev_growth_val
                if gap > max_gap:
                    max_gap = gap
                    worst_category = cat
                    worst_cat_growth = cat_growth
                    worst_cat_amount = cat_amount

        if worst_category:
            severity = "warning"
            score = 80.0 + min(20.0, max_gap)
            return AttentionItem(
                id=f"expense_pacing_{worst_category.lower().replace(' ', '_')}",
                title=f"'{worst_category}' Costs Outpacing Revenue",
                message=(
                    f"'{worst_category}' expenses jumped {worst_cat_growth:+.1f}% (to ₹{worst_cat_amount:,.2f}), "
                    f"outpacing your revenue growth of {rev_growth_str}."
                ),
                severity=severity,
                action_tab="comparison",
                action_label="Review Expense Breakdown",
                score=score,
            )
        return None
    except Exception as exc:
        logger.debug(f"check_expense_faster_than_revenue skipped: {exc}")
        return None


def check_biggest_expense_jump(tenant_id: str) -> Optional[AttentionItem]:
    """Identify the single expense category with the largest absolute currency surge."""
    try:
        comp = compare_periods(tenant_id)
        if not comp or comp.prior.period_label == "None":
            return None

        shifts = (
            comp.expense_shifts.to_dict("records")
            if isinstance(comp.expense_shifts, pd.DataFrame)
            else (comp.expense_shifts or [])
        )
        if not shifts:
            return None

        def _get_shift_delta(s: dict) -> float:
            d = s.get("delta") if s.get("delta") is not None else s.get("change", 0.0)
            return float(d or 0.0)

        def _get_shift_delta_pct(s: dict) -> float:
            dp = s.get("delta_pct") if s.get("delta_pct") is not None else s.get("change_pct", 0.0)
            return float(dp or 0.0)

        surges = [s for s in shifts if _get_shift_delta(s) > 0]
        if not surges:
            return None

        surges.sort(key=_get_shift_delta, reverse=True)
        top_surge = surges[0]
        jump_amt = _get_shift_delta(top_surge)
        cat = str(top_surge.get("category", ""))
        jump_pct = _get_shift_delta_pct(top_surge)

        if jump_amt < 100.0:
            return None

        severity = "warning" if jump_amt >= 1000.0 else "info"
        score = 65.0 + min(25.0, jump_amt / 100.0)

        jump_pct_str = f"{jump_pct:+.1f}% vs prior month" if top_surge.get("delta_pct") is not None else "new category"
        return AttentionItem(
            id=f"expense_surge_{cat.lower().replace(' ', '_')}",
            title=f"Cost Surge in '{cat}'",
            message=(
                f"'{cat}' had the largest cost increase this period, surging by +₹{jump_amt:,.2f} "
                f"({jump_pct_str})."
            ),
            severity=severity,
            action_tab="comparison",
            action_label="Compare Expenses",
            score=score,
        )
    except Exception as exc:
        logger.debug(f"check_biggest_expense_jump skipped: {exc}")
        return None


def check_stalled_products(tenant_id: str) -> Optional[AttentionItem]:
    """
    Find catalog products with zero sales in the 30 days prior to the tenant's latest transaction date.
    Only checks products that were active previously (established catalog items).
    """
    try:
        anchor = _get_tenant_anchor_date(tenant_id)
        if not anchor:
            return None

        cutoff = anchor - timedelta(days=30)

        with get_db() as db:
            # Historical products sold before cutoff
            hist_products = {
                p[0]
                for p in db.query(Sales.product)
                .filter(Sales.tenant_id == tenant_id, Sales.date <= cutoff)
                .distinct()
                .all()
                if p[0]
            }

            if not hist_products:
                return None

            # Products sold within last 30 days
            recent_products = {
                p[0]
                for p in db.query(Sales.product)
                .filter(Sales.tenant_id == tenant_id, Sales.date > cutoff)
                .distinct()
                .all()
                if p[0]
            }

        stalled = sorted(list(hist_products - recent_products))
        if not stalled:
            return None

        count = len(stalled)
        sample_str = ", ".join(f"'{p}'" for p in stalled[:3])
        if count > 3:
            sample_str += f" and {count - 3} more"

        severity = "warning" if count >= 3 else "info"
        score = 55.0 + min(20.0, count * 5.0)

        return AttentionItem(
            id="stalled_products",
            title=f"{count} Product{'s' if count != 1 else ''} Not Sold in 30 Days",
            message=(
                f"{count} established item{'s have' if count != 1 else ' has'} had no sales "
                f"in the 30 days up to {anchor.strftime('%d %b %Y')} ({sample_str})."
            ),
            severity=severity,
            action_tab="overview",
            action_label="View Products",
            score=score,
        )
    except Exception as exc:
        logger.debug(f"check_stalled_products skipped: {exc}")
        return None


def check_recent_anomalies(tenant_id: str) -> Optional[AttentionItem]:
    """Surface severe recent statistical anomalies in revenue or expense activity."""
    try:
        report = detect_anomalies(tenant_id)
        all_anomalies = report.revenue_anomalies + report.expense_anomalies
        if not all_anomalies:
            return None

        # Filter for critical or warning anomalies
        severe = [a for a in all_anomalies if a.severity in ("critical", "warning")]
        if not severe:
            return None

        # Sort by date descending, then deviation %
        severe.sort(key=lambda a: (a.date, abs(a.deviation_pct)), reverse=True)
        top = severe[0]

        severity = top.severity
        score = 90.0 if severity == "critical" else 70.0

        return AttentionItem(
            id=f"anomaly_{top.metric}_{top.date}",
            title=f"Unusual {top.metric.title()} {top.anomaly_type.title()}",
            message=(
                f"{top.description} on {top.date.strftime('%d %b %Y')} "
                f"({top.deviation_pct:+.1f}% deviation from normal baseline)."
            ),
            severity=severity,
            action_tab="anomalies",
            action_label="Inspect Anomaly Radar",
            score=score,
        )
    except Exception as exc:
        logger.debug(f"check_recent_anomalies skipped: {exc}")
        return None


def get_attention_items(tenant_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Evaluate all 5 decision-support rules, rank by score/severity, and return max 5 items.
    If no issues are detected, returns a positive healthy state.
    """
    candidates: List[AttentionItem] = []

    # 1. Profit drop with primary driver
    item_profit = check_profit_drop(tenant_id)
    if item_profit:
        candidates.append(item_profit)

    # 2. Expense category outgrowing revenue
    item_pacing = check_expense_faster_than_revenue(tenant_id)
    if item_pacing:
        candidates.append(item_pacing)

    # 3. Biggest expense surge (if not already duplicate category)
    item_surge = check_biggest_expense_jump(tenant_id)
    if item_surge:
        # Avoid duplicate alert if pacing already flagged the same category
        pacing_id = item_pacing.id if item_pacing else ""
        if item_surge.id.replace("expense_surge_", "") not in pacing_id:
            candidates.append(item_surge)

    # 4. Products not sold in 30 days
    item_stalled = check_stalled_products(tenant_id)
    if item_stalled:
        candidates.append(item_stalled)

    # 5. Statistical anomalies
    item_anomaly = check_recent_anomalies(tenant_id)
    if item_anomaly:
        candidates.append(item_anomaly)

    # If no issues were detected, return an all-clear healthy notification
    if not candidates:
        return [
            AttentionItem(
                id="all_clear",
                title="Operations Look Healthy",
                message="No profit drops, stalled products, or unusual expense surges were detected in your records.",
                severity="info",
                action_tab="overview",
                action_label="View Overview",
                score=10.0,
            ).to_dict()
        ]

    # Rank by score descending, then return top `limit`
    candidates.sort(key=lambda x: x.score, reverse=True)
    return [item.to_dict() for item in candidates[:limit]]
