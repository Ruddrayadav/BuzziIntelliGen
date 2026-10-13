"""
services/analytics_service.py
-----------------------------
Advanced Business Analytics & Decision Support Engine (Phase 5).

Provides:
1. Period-over-Period Comparison (MoM / Custom range, deltas, top gainers/decliners).
2. Statistical Anomaly Detection (Revenue drops/spikes, expense surges, severity scoring).
3. Root Cause Profit Drop & Margin Diagnostics (Decomposition of profit shifts, waterfall analysis).

UI RULE:
  Strictly business logic and data aggregation. No Plotly charts or Streamlit UI code.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
import math
from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
from sqlalchemy import func

from db.database import get_db
from db.models import Sales, Expenses


# ─────────────────────────────────────────────────────────────────────────────
# 1. Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PeriodSummary:
    """Summary of financial metrics for a single period."""
    period_label: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    revenue: float = 0.0
    expenses: float = 0.0
    net_profit: float = 0.0
    order_count: int = 0
    average_order_value: float = 0.0
    profit_margin_pct: float = 0.0


@dataclass
class PeriodComparison:
    """Detailed comparison between two financial periods."""
    current: PeriodSummary
    prior: PeriodSummary
    
    # Deltas (Current - Prior)
    revenue_delta: float = 0.0
    revenue_delta_pct: float = 0.0
    expense_delta: float = 0.0
    expense_delta_pct: float = 0.0
    profit_delta: float = 0.0
    profit_delta_pct: float = 0.0
    aov_delta: float = 0.0
    aov_delta_pct: float = 0.0
    margin_delta_pct: float = 0.0
    
    # Product & Expense Shifts
    product_shifts: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    expense_shifts: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    top_gainers: List[Dict[str, Any]] = field(default_factory=list)
    top_decliners: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Anomaly:
    """A detected anomalous event."""
    date: date
    metric: str           # "revenue" or "expenses"
    actual_value: float
    expected_value: float
    deviation: float      # actual - expected
    deviation_pct: float  # percentage above/below expected
    z_score: float
    anomaly_type: str     # "spike" or "drop"
    severity: str         # "critical", "warning", "info"
    description: str


@dataclass
class AnomalyReport:
    """Complete anomaly analysis for a tenant."""
    total_anomalies: int
    revenue_anomalies: List[Anomaly] = field(default_factory=list)
    expense_anomalies: List[Anomaly] = field(default_factory=list)
    timeline_df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())


@dataclass
class ProfitDiagnosis:
    """Root cause diagnostic report explaining why profit changed."""
    period_label: str
    comparison_label: str
    prior_profit: float
    current_profit: float
    profit_change: float
    profit_change_pct: float
    is_profit_down: bool
    primary_driver: str
    revenue_impact: float
    expense_impact: float
    top_revenue_drags: List[Dict[str, Any]] = field(default_factory=list)
    top_expense_surges: List[Dict[str, Any]] = field(default_factory=list)
    key_insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    waterfall_df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def _calc_pct_change(current: float, prior: float) -> float:
    """Safely calculate percentage change without ZeroDivisionError."""
    if prior == 0.0:
        if current == 0.0:
            return 0.0
        return 100.0 if current > 0 else -100.0
    return round(((current - prior) / abs(prior)) * 100.0, 2)


def get_available_months(tenant_id: str) -> List[str]:
    """
    Returns sorted list of available months in 'YYYY-MM' format for a tenant,
    combining both Sales and Expenses data.
    """
    with get_db() as db:
        sales_dates = db.query(Sales.date).filter(Sales.tenant_id == tenant_id).all()
        exp_dates = db.query(Expenses.date).filter(Expenses.tenant_id == tenant_id).all()
        
    all_dates = [r[0] for r in sales_dates if r[0]] + [r[0] for r in exp_dates if r[0]]
    if not all_dates:
        return []
    
    unique_months = set(d.strftime("%Y-%m") for d in all_dates)
    return sorted(list(unique_months))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Period-over-Period Comparison Logic
# ─────────────────────────────────────────────────────────────────────────────

def compare_periods(
    tenant_id: str,
    current_month: Optional[str] = None,
    prior_month: Optional[str] = None
) -> Optional[PeriodComparison]:
    """
    Compare business performance between two months (e.g. '2024-06' vs '2024-05').
    If months are not specified, defaults to the two most recent available months.
    """
    available_months = get_available_months(tenant_id)
    if not available_months:
        return None
    
    if len(available_months) < 2 and (not current_month or not prior_month):
        # Only one month available: return comparison against zero baseline
        current_month = available_months[0]
        prior_month = None

    if not current_month:
        current_month = available_months[-1]
    if prior_month is None and len(available_months) >= 2:
        curr_idx = available_months.index(current_month) if current_month in available_months else len(available_months) - 1
        prior_month = available_months[curr_idx - 1] if curr_idx > 0 else None

    # Load tenant sales & expenses
    with get_db() as db:
        s_query = db.query(
            Sales.date, Sales.product, Sales.revenue, Sales.order_id
        ).filter(Sales.tenant_id == tenant_id).statement
        sales_df = pd.read_sql(s_query, db.bind)
        
        e_query = db.query(
            Expenses.date, Expenses.category, Expenses.amount
        ).filter(Expenses.tenant_id == tenant_id).statement
        expenses_df = pd.read_sql(e_query, db.bind)

    if sales_df.empty and expenses_df.empty:
        return None

    if not sales_df.empty:
        sales_df["date"] = pd.to_datetime(sales_df["date"])
        sales_df["month"] = sales_df["date"].dt.strftime("%Y-%m")
    else:
        sales_df = pd.DataFrame(columns=["date", "product", "revenue", "order_id", "month"])

    if not expenses_df.empty:
        expenses_df["date"] = pd.to_datetime(expenses_df["date"])
        expenses_df["month"] = expenses_df["date"].dt.strftime("%Y-%m")
    else:
        expenses_df = pd.DataFrame(columns=["date", "category", "amount", "month"])

    # Build Current Summary
    curr_s = sales_df[sales_df["month"] == current_month] if not sales_df.empty else pd.DataFrame()
    curr_e = expenses_df[expenses_df["month"] == current_month] if not expenses_df.empty else pd.DataFrame()
    
    curr_rev = float(curr_s["revenue"].sum()) if not curr_s.empty else 0.0
    curr_exp = float(curr_e["amount"].sum()) if not curr_e.empty else 0.0
    curr_prof = curr_rev - curr_exp
    
    if not curr_s.empty:
        orders_with_id = curr_s["order_id"].dropna().nunique()
        orders_without_id = curr_s["order_id"].isna().sum()
        curr_orders = int(orders_with_id + orders_without_id)
    else:
        curr_orders = 0
    curr_aov = round(curr_rev / curr_orders, 2) if curr_orders > 0 else 0.0
    curr_margin = round((curr_prof / curr_rev * 100.0), 2) if curr_rev > 0 else 0.0

    curr_summary = PeriodSummary(
        period_label=current_month,
        revenue=curr_rev,
        expenses=curr_exp,
        net_profit=curr_prof,
        order_count=curr_orders,
        average_order_value=curr_aov,
        profit_margin_pct=curr_margin
    )

    # Build Prior Summary
    if prior_month:
        prior_s = sales_df[sales_df["month"] == prior_month] if not sales_df.empty else pd.DataFrame()
        prior_e = expenses_df[expenses_df["month"] == prior_month] if not expenses_df.empty else pd.DataFrame()
        
        prior_rev = float(prior_s["revenue"].sum()) if not prior_s.empty else 0.0
        prior_exp = float(prior_e["amount"].sum()) if not prior_e.empty else 0.0
        prior_prof = prior_rev - prior_exp
        
        if not prior_s.empty:
            p_orders_with_id = prior_s["order_id"].dropna().nunique()
            p_orders_without_id = prior_s["order_id"].isna().sum()
            prior_orders = int(p_orders_with_id + p_orders_without_id)
        else:
            prior_orders = 0
        prior_aov = round(prior_rev / prior_orders, 2) if prior_orders > 0 else 0.0
        prior_margin = round((prior_prof / prior_rev * 100.0), 2) if prior_rev > 0 else 0.0
        
        prior_summary = PeriodSummary(
            period_label=prior_month,
            revenue=prior_rev,
            expenses=prior_exp,
            net_profit=prior_prof,
            order_count=prior_orders,
            average_order_value=prior_aov,
            profit_margin_pct=prior_margin
        )
    else:
        prior_s = pd.DataFrame()
        prior_e = pd.DataFrame()
        prior_summary = PeriodSummary(period_label="None")

    # Compute Deltas
    rev_delta = round(curr_summary.revenue - prior_summary.revenue, 2)
    rev_delta_pct = _calc_pct_change(curr_summary.revenue, prior_summary.revenue)
    
    exp_delta = round(curr_summary.expenses - prior_summary.expenses, 2)
    exp_delta_pct = _calc_pct_change(curr_summary.expenses, prior_summary.expenses)
    
    prof_delta = round(curr_summary.net_profit - prior_summary.net_profit, 2)
    prof_delta_pct = _calc_pct_change(curr_summary.net_profit, prior_summary.net_profit)
    
    aov_delta = round(curr_summary.average_order_value - prior_summary.average_order_value, 2)
    aov_delta_pct = _calc_pct_change(curr_summary.average_order_value, prior_summary.average_order_value)
    
    margin_delta_pct = round(curr_summary.profit_margin_pct - prior_summary.profit_margin_pct, 2)

    # Product shifts calculation
    p_shifts_list = []
    if not curr_s.empty or not prior_s.empty:
        curr_prod = curr_s.groupby("product")["revenue"].sum() if not curr_s.empty else pd.Series(dtype=float)
        prior_prod = prior_s.groupby("product")["revenue"].sum() if not prior_s.empty else pd.Series(dtype=float)
        
        all_prods = set(curr_prod.index).union(set(prior_prod.index))
        for p in all_prods:
            c_val = float(curr_prod.get(p, 0.0))
            p_val = float(prior_prod.get(p, 0.0))
            diff = round(c_val - p_val, 2)
            pct = _calc_pct_change(c_val, p_val)
            p_shifts_list.append({
                "product": p,
                "prior_revenue": p_val,
                "current_revenue": c_val,
                "delta": diff,
                "delta_pct": pct
            })
            
    product_shifts_df = pd.DataFrame(p_shifts_list)
    top_gainers = []
    top_decliners = []
    if not product_shifts_df.empty:
        product_shifts_df = product_shifts_df.sort_values("delta", ascending=False)
        top_gainers = product_shifts_df[product_shifts_df["delta"] > 0].head(5).to_dict("records")
        top_decliners = product_shifts_df[product_shifts_df["delta"] < 0].sort_values("delta", ascending=True).head(5).to_dict("records")

    # Expense category shifts calculation
    e_shifts_list = []
    if not curr_e.empty or not prior_e.empty:
        curr_cat = curr_e.groupby("category")["amount"].sum() if not curr_e.empty else pd.Series(dtype=float)
        prior_cat = prior_e.groupby("category")["amount"].sum() if not prior_e.empty else pd.Series(dtype=float)
        
        all_cats = set(curr_cat.index).union(set(prior_cat.index))
        for c in all_cats:
            c_val = float(curr_cat.get(c, 0.0))
            p_val = float(prior_cat.get(c, 0.0))
            diff = round(c_val - p_val, 2)
            pct = _calc_pct_change(c_val, p_val)
            e_shifts_list.append({
                "category": c,
                "prior_amount": p_val,
                "current_amount": c_val,
                "delta": diff,
                "delta_pct": pct
            })
            
    expense_shifts_df = pd.DataFrame(e_shifts_list)
    if not expense_shifts_df.empty:
        expense_shifts_df = expense_shifts_df.sort_values("delta", ascending=False)

    return PeriodComparison(
        current=curr_summary,
        prior=prior_summary,
        revenue_delta=rev_delta,
        revenue_delta_pct=rev_delta_pct,
        expense_delta=exp_delta,
        expense_delta_pct=exp_delta_pct,
        profit_delta=prof_delta,
        profit_delta_pct=prof_delta_pct,
        aov_delta=aov_delta,
        aov_delta_pct=aov_delta_pct,
        margin_delta_pct=margin_delta_pct,
        product_shifts=product_shifts_df,
        expense_shifts=expense_shifts_df,
        top_gainers=top_gainers,
        top_decliners=top_decliners
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Statistical Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_anomalies(
    tenant_id: str,
    sensitivity: float = 2.0,
    window: int = 7
) -> AnomalyReport:
    """
    Detect statistical outliers (spikes and drops) in daily sales and expenses.
    Uses rolling baseline statistics (or global mean/std if time-series is short).
    """
    with get_db() as db:
        s_query = db.query(Sales.date, Sales.revenue).filter(Sales.tenant_id == tenant_id).statement
        sales_df = pd.read_sql(s_query, db.bind)
        
        e_query = db.query(Expenses.date, Expenses.amount).filter(Expenses.tenant_id == tenant_id).statement
        exp_df = pd.read_sql(e_query, db.bind)

    if sales_df.empty and exp_df.empty:
        return AnomalyReport(total_anomalies=0)

    # Prepare daily aggregations
    daily_sales = pd.DataFrame(columns=["date", "revenue"])
    if not sales_df.empty:
        sales_df["date"] = pd.to_datetime(sales_df["date"]).dt.date
        daily_sales = sales_df.groupby("date")["revenue"].sum().reset_index()

    daily_exp = pd.DataFrame(columns=["date", "amount"])
    if not exp_df.empty:
        exp_df["date"] = pd.to_datetime(exp_df["date"]).dt.date
        daily_exp = exp_df.groupby("date")["amount"].sum().reset_index()

    # Merge into a full timeline
    timeline = pd.merge(daily_sales, daily_exp, on="date", how="outer").fillna(0.0)
    timeline = timeline.sort_values("date").reset_index(drop=True)
    timeline["date"] = pd.to_datetime(timeline["date"]).dt.date

    rev_anomalies: List[Anomaly] = []
    exp_anomalies: List[Anomaly] = []

    # 1. Sales Anomalies
    if len(daily_sales) >= 5:
        rev_series = daily_sales["revenue"]
        mean_g = float(rev_series.mean())
        std_g = float(rev_series.std()) if float(rev_series.std()) > 0 else 1.0

        roll_mean = rev_series.rolling(window=window, min_periods=3, center=True).mean().fillna(mean_g)
        roll_std = rev_series.rolling(window=window, min_periods=3, center=True).std().fillna(std_g).replace(0.0, std_g)

        z_global = (rev_series - mean_g) / std_g
        z_roll = (rev_series - roll_mean) / roll_std

        # Pick the more significant z-score magnitude
        use_global = z_global.abs() > z_roll.abs()
        daily_sales["expected"] = np.where(use_global, mean_g, roll_mean)
        daily_sales["z_score"] = np.where(use_global, z_global, z_roll)

        for _, row in daily_sales.iterrows():
            z = float(row["z_score"])
            actual = float(row["revenue"])
            expected = float(row["expected"])
            diff = actual - expected
            
            if abs(z) >= sensitivity:
                anomaly_type = "spike" if z > 0 else "drop"
                dev_pct = _calc_pct_change(actual, expected)
                
                if abs(z) >= 3.0:
                    severity = "critical"
                elif abs(z) >= 2.0:
                    severity = "warning"
                else:
                    severity = "info"
                    
                if anomaly_type == "spike":
                    desc = f"Revenue surged to ₹{actual:,.2f} ({dev_pct:+.1f}% vs expected ₹{expected:,.2f})"
                else:
                    desc = f"Revenue plunged to ₹{actual:,.2f} ({dev_pct:+.1f}% vs expected ₹{expected:,.2f})"

                rev_anomalies.append(Anomaly(
                    date=row["date"],
                    metric="revenue",
                    actual_value=round(actual, 2),
                    expected_value=round(expected, 2),
                    deviation=round(diff, 2),
                    deviation_pct=dev_pct,
                    z_score=round(z, 2),
                    anomaly_type=anomaly_type,
                    severity=severity,
                    description=desc
                ))

    # 2. Expense Anomalies
    if len(daily_exp) >= 5:
        exp_series = daily_exp["amount"]
        mean_g = float(exp_series.mean())
        std_g = float(exp_series.std()) if float(exp_series.std()) > 0 else 1.0

        roll_mean = exp_series.rolling(window=window, min_periods=3, center=True).mean().fillna(mean_g)
        roll_std = exp_series.rolling(window=window, min_periods=3, center=True).std().fillna(std_g).replace(0.0, std_g)

        z_global = (exp_series - mean_g) / std_g
        z_roll = (exp_series - roll_mean) / roll_std
        use_global = z_global.abs() > z_roll.abs()

        daily_exp["expected"] = np.where(use_global, mean_g, roll_mean)
        daily_exp["z_score"] = np.where(use_global, z_global, z_roll)

        for _, row in daily_exp.iterrows():
            z = float(row["z_score"])
            actual = float(row["amount"])
            expected = float(row["expected"])
            diff = actual - expected
            
            # For expenses, alert on spikes
            if z >= sensitivity:
                dev_pct = _calc_pct_change(actual, expected)
                severity = "critical" if z >= 3.0 else ("warning" if z >= 2.0 else "info")
                desc = f"Expense spike of ₹{actual:,.2f} ({dev_pct:+.1f}% vs expected ₹{expected:,.2f})"
                
                exp_anomalies.append(Anomaly(
                    date=row["date"],
                    metric="expenses",
                    actual_value=round(actual, 2),
                    expected_value=round(expected, 2),
                    deviation=round(diff, 2),
                    deviation_pct=dev_pct,
                    z_score=round(z, 2),
                    anomaly_type="spike",
                    severity=severity,
                    description=desc
                ))

    # Sort anomalies chronologically
    rev_anomalies.sort(key=lambda a: a.date, reverse=True)
    exp_anomalies.sort(key=lambda a: a.date, reverse=True)

    return AnomalyReport(
        total_anomalies=len(rev_anomalies) + len(exp_anomalies),
        revenue_anomalies=rev_anomalies,
        expense_anomalies=exp_anomalies,
        timeline_df=timeline
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Root Cause Profit Drop & Margin Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def diagnose_profit_drop(
    tenant_id: str,
    current_month: Optional[str] = None,
    prior_month: Optional[str] = None
) -> Optional[ProfitDiagnosis]:
    """
    Deconstructs why net profit changed between two periods into its
    root causal drivers (Revenue contraction vs Cost inflation vs Product mix).
    """
    comp = compare_periods(tenant_id, current_month, prior_month)
    if not comp or comp.prior.period_label == "None":
        return None

    profit_change = comp.profit_delta
    profit_change_pct = comp.profit_delta_pct
    is_down = profit_change < 0
    
    rev_impact = comp.revenue_delta       # Positive helps profit, negative hurts profit
    exp_impact = -comp.expense_delta      # Positive (lower expenses) helps profit, negative hurts profit

    # 1. Determine Primary Driver
    if is_down:
        if comp.revenue_delta < 0 and comp.expense_delta > 0:
            primary_driver = "Dual Drag (Revenue fell AND Expenses surged)"
        elif comp.revenue_delta < 0:
            primary_driver = "Revenue Contraction (Sales volume or prices dropped)"
        elif comp.expense_delta > 0:
            primary_driver = "Expense Inflation (Operating costs grew faster than sales)"
        else:
            primary_driver = "Margin Compression (Disproportionate cost growth)"
    else:
        if comp.revenue_delta > 0 and comp.expense_delta <= 0:
            primary_driver = "Dual Expansion (Revenue grew while costs stayed disciplined)"
        elif comp.revenue_delta > 0:
            primary_driver = "Revenue Growth (Strong sales expansion outpaced costs)"
        elif comp.expense_delta < 0:
            primary_driver = "Cost Optimization (Reduced overhead boosted net profit)"
        else:
            primary_driver = "Profitable Operations (Healthy operating margin)"

    # 2. Extract Top Revenue Drags (Products with largest decline)
    top_drags: List[Dict[str, Any]] = []
    if comp.top_decliners:
        total_rev_drop = abs(comp.revenue_delta) if comp.revenue_delta < 0 else sum(abs(p["delta"]) for p in comp.top_decliners)
        for item in comp.top_decliners:
            drop_amt = abs(item["delta"])
            contrib_pct = round((drop_amt / total_rev_drop * 100.0), 1) if total_rev_drop > 0 else 0.0
            top_drags.append({
                "product": item["product"],
                "drop_amount": drop_amt,
                "pct_change": item["delta_pct"],
                "contribution_pct": contrib_pct
            })

    # 3. Extract Top Expense Surges (Categories with largest cost inflation)
    top_surges: List[Dict[str, Any]] = []
    if not comp.expense_shifts.empty:
        surging_df = comp.expense_shifts[comp.expense_shifts["delta"] > 0].sort_values("delta", ascending=False)
        total_exp_surge = comp.expense_delta if comp.expense_delta > 0 else surging_df["delta"].sum()
        for _, row in surging_df.head(5).iterrows():
            surge_amt = float(row["delta"])
            contrib_pct = round((surge_amt / total_exp_surge * 100.0), 1) if total_exp_surge > 0 else 0.0
            top_surges.append({
                "category": row["category"],
                "increase_amount": surge_amt,
                "pct_change": row["delta_pct"],
                "contribution_pct": contrib_pct
            })

    # 4. Formulate Actionable Key Insights & Recommendations
    key_insights: List[str] = []
    recommendations: List[str] = []

    if is_down:
        key_insights.append(
            f"Net Profit declined by ₹{abs(profit_change):,.2f} ({profit_change_pct:+.1f}%) from {comp.prior.period_label} to {comp.current.period_label}."
        )
        if comp.revenue_delta < 0:
            key_insights.append(
                f"Revenue drop contributed ₹{abs(comp.revenue_delta):,.2f} ({comp.revenue_delta_pct:+.1f}%) to the deficit."
            )
        if comp.expense_delta > 0:
            key_insights.append(
                f"Expense increase added an extra ₹{comp.expense_delta:,.2f} (+{comp.expense_delta_pct:+.1f}%) to operational costs."
            )
            
        if top_drags:
            top_p = top_drags[0]
            key_insights.append(
                f"Major revenue drag: '{top_p['product']}' dropped by ₹{top_p['drop_amount']:,.2f} ({top_p['pct_change']:+.1f}%)."
            )
            recommendations.append(
                f"Review inventory, customer demand, or promotional pricing for '{top_p['product']}' to recover sales."
            )

        if top_surges:
            top_e = top_surges[0]
            key_insights.append(
                f"Highest cost spike: '{top_e['category']}' jumped by ₹{top_e['increase_amount']:,.2f} ({top_e['pct_change']:+.1f}%)."
            )
            recommendations.append(
                f"Audit vendor invoices and recurring contracts for '{top_e['category']}' to trim unnecessary costs."
            )
            
        if comp.aov_delta < 0:
            recommendations.append(
                f"Average Order Value dropped by ₹{abs(comp.aov_delta):,.2f}. Consider product bundling or combo deals to lift basket size."
            )
    else:
        key_insights.append(
            f"Net Profit grew by ₹{profit_change:,.2f} ({profit_change_pct:+.1f}%) from {comp.prior.period_label} to {comp.current.period_label}."
        )
        if comp.revenue_delta > 0:
            key_insights.append(f"Revenue expanded by ₹{comp.revenue_delta:,.2f} ({comp.revenue_delta_pct:+.1f}%).")
        if comp.expense_delta < 0:
            key_insights.append(f"Operating expenses decreased by ₹{abs(comp.expense_delta):,.2f} ({comp.expense_delta_pct:+.1f}%).")
        recommendations.append("Continue current marketing momentum and maintain cost controls on overhead.")

    # 5. Build Waterfall Chart Data
    # Step 1: Starting Profit
    # Step 2: Revenue Change
    # Step 3: Expense Change (negated: increase hurts profit, decrease helps)
    # Step 4: Ending Profit
    waterfall_rows = [
        {"measure": "absolute", "label": f"{comp.prior.period_label} Profit", "value": comp.prior.net_profit},
        {"measure": "relative", "label": "Revenue Impact", "value": comp.revenue_delta},
        {"measure": "relative", "label": "Expense Impact", "value": -comp.expense_delta},
        {"measure": "total", "label": f"{comp.current.period_label} Profit", "value": comp.current.net_profit},
    ]
    waterfall_df = pd.DataFrame(waterfall_rows)

    return ProfitDiagnosis(
        period_label=comp.current.period_label,
        comparison_label=comp.prior.period_label,
        prior_profit=comp.prior.net_profit,
        current_profit=comp.current.net_profit,
        profit_change=profit_change,
        profit_change_pct=profit_change_pct,
        is_profit_down=is_down,
        primary_driver=primary_driver,
        revenue_impact=rev_impact,
        expense_impact=exp_impact,
        top_revenue_drags=top_drags,
        top_expense_surges=top_surges,
        key_insights=key_insights,
        recommendations=recommendations,
        waterfall_df=waterfall_df
    )
