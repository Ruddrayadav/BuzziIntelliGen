"""
services/dashboard_service.py
-----------------------------
Calculates KPIs and chart data for the business dashboard.

UI RULE:
  This service only queries the database and returns raw data dictionaries
  or DataFrames. It does NOT create Plotly charts or use Streamlit functions.
  The UI layer is responsible for rendering.

PRINCIPLE 1 & 2:
  The LLM never calculates. All numbers come from Python/SQL.
  Takeaway sentences are built strictly in Python code from computed numbers.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import numpy as np
import pandas as pd
from sqlalchemy import func

from db.database import get_db
from db.models import Sales, Expenses
from services.attention_service import get_attention_items


@dataclass
class DashboardData:
    """
    All data needed to render the dashboard.
    """
    # Core KPIs
    total_revenue: float
    total_expenses: float
    net_profit: float
    average_order_value: float
    
    # Existing Chart Data (DataFrames)
    revenue_trend: pd.DataFrame
    top_products: pd.DataFrame
    expense_breakdown: pd.DataFrame

    # Phase 1 additions
    total_transactions: int = 0
    total_units_sold: float = 0.0
    expense_trend: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["date", "amount"]))
    top_products_by_qty: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["product", "quantity", "revenue"]))
    bottom_products_by_qty: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["product", "quantity", "revenue"]))
    category_performance: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["category", "revenue", "units_sold", "order_count", "share_pct"]))
    takeaways: dict[str, str] = field(default_factory=dict)
    attention_items: list[dict[str, Any]] = field(default_factory=list)
    day_of_week_insight: Optional[dict[str, Any]] = None
    slow_movers: list[dict[str, Any]] = field(default_factory=list)


def _parse_filter_date(d_str: Optional[str]):
    if not d_str:
        return None
    try:
        return pd.to_datetime(d_str.strip()).date()
    except Exception:
        return None


def get_dashboard_data(
    tenant_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> DashboardData:
    """
    Fetch and calculate all dashboard metrics for a specific tenant,
    optionally filtered by start_date and end_date (YYYY-MM-DD).
    """
    start_dt = _parse_filter_date(start_date)
    end_dt = _parse_filter_date(end_date)

    with get_db() as db:
        # ── 1. Calculate KPIs ────────────────────────────────────────────────
        rev_q = db.query(func.sum(Sales.revenue)).filter(Sales.tenant_id == tenant_id)
        exp_q = db.query(func.sum(Expenses.amount)).filter(Expenses.tenant_id == tenant_id)
        
        uniq_orders_q = db.query(func.count(func.distinct(Sales.order_id))).filter(
            Sales.tenant_id == tenant_id,
            Sales.order_id != None,  # noqa: E711
        )
        no_order_id_q = db.query(func.count(Sales.id)).filter(
            Sales.tenant_id == tenant_id,
            Sales.order_id == None,  # noqa: E711
        )
        units_q = db.query(func.sum(Sales.quantity)).filter(Sales.tenant_id == tenant_id)

        if start_dt:
            rev_q = rev_q.filter(Sales.date >= start_dt)
            exp_q = exp_q.filter(Expenses.date >= start_dt)
            uniq_orders_q = uniq_orders_q.filter(Sales.date >= start_dt)
            no_order_id_q = no_order_id_q.filter(Sales.date >= start_dt)
            units_q = units_q.filter(Sales.date >= start_dt)

        if end_dt:
            rev_q = rev_q.filter(Sales.date <= end_dt)
            exp_q = exp_q.filter(Expenses.date <= end_dt)
            uniq_orders_q = uniq_orders_q.filter(Sales.date <= end_dt)
            no_order_id_q = no_order_id_q.filter(Sales.date <= end_dt)
            units_q = units_q.filter(Sales.date <= end_dt)

        revenue = rev_q.scalar() or 0.0
        expenses = exp_q.scalar() or 0.0
        net_profit = revenue - expenses
        
        unique_orders = uniq_orders_q.scalar() or 0
        rows_without_order_id = no_order_id_q.scalar() or 0
        total_orders = unique_orders + rows_without_order_id
        aov = (revenue / total_orders) if total_orders > 0 else 0.0
        total_units = float(units_q.scalar() or 0.0)

        # ── 2. Load Sales Data for Breakdown and Products ──────────────────
        sales_q = db.query(
            Sales.date,
            Sales.product,
            Sales.category,
            Sales.quantity,
            Sales.revenue,
            Sales.order_id,
        ).filter(Sales.tenant_id == tenant_id)

        if start_dt:
            sales_q = sales_q.filter(Sales.date >= start_dt)
        if end_dt:
            sales_q = sales_q.filter(Sales.date <= end_dt)

        sales_df = pd.read_sql(sales_q.statement, db.bind)

        # ── 3. Load Expense Data for Categories and Trends ────────────────
        exp_q_full = db.query(
            Expenses.date,
            Expenses.category,
            Expenses.description,
            Expenses.amount,
        ).filter(Expenses.tenant_id == tenant_id)

        if start_dt:
            exp_q_full = exp_q_full.filter(Expenses.date >= start_dt)
        if end_dt:
            exp_q_full = exp_q_full.filter(Expenses.date <= end_dt)

        exp_df = pd.read_sql(exp_q_full.statement, db.bind)

    # ── 4. Process Sales Metrics ─────────────────────────────────────────
    if not sales_df.empty:
        # Revenue trend (daily aggregation)
        revenue_trend = sales_df.groupby("date")["revenue"].sum().reset_index()
        revenue_trend = revenue_trend.sort_values("date").reset_index(drop=True)

        # Top 5 products by revenue
        top_products = (
            sales_df.groupby("product")["revenue"]
            .sum()
            .reset_index()
            .sort_values("revenue", ascending=False)
            .head(5)
            .reset_index(drop=True)
        )

        # Top and bottom products by quantity
        sales_df["quantity_clean"] = pd.to_numeric(sales_df["quantity"], errors="coerce").fillna(0.0)
        prod_qty_agg = (
            sales_df.groupby("product")
            .agg(quantity=("quantity_clean", "sum"), revenue=("revenue", "sum"))
            .reset_index()
        )
        top_products_by_qty = (
            prod_qty_agg.sort_values(by=["quantity", "revenue"], ascending=[False, False])
            .head(5)
            .reset_index(drop=True)
        )
        bottom_products_by_qty = (
            prod_qty_agg[prod_qty_agg["quantity"] >= 0]
            .sort_values(by=["quantity", "revenue"], ascending=[True, True])
            .head(5)
            .reset_index(drop=True)
        )

        # Category performance
        sales_df["category_clean"] = sales_df["category"].fillna("").astype(str).str.strip()
        sales_df["category_clean"] = sales_df["category_clean"].replace("", "Uncategorized")
        
        category_perf = (
            sales_df.groupby("category_clean")
            .agg(
                revenue=("revenue", "sum"),
                units_sold=("quantity_clean", "sum"),
                order_count=("revenue", "count"),
            )
            .reset_index()
            .rename(columns={"category_clean": "category"})
            .sort_values("revenue", ascending=False)
            .reset_index(drop=True)
        )
        if revenue > 0:
            category_perf["share_pct"] = (category_perf["revenue"] / revenue * 100.0).round(1)
        else:
            category_perf["share_pct"] = 0.0
    else:
        revenue_trend = pd.DataFrame(columns=["date", "revenue"])
        top_products = pd.DataFrame(columns=["product", "revenue"])
        top_products_by_qty = pd.DataFrame(columns=["product", "quantity", "revenue"])
        bottom_products_by_qty = pd.DataFrame(columns=["product", "quantity", "revenue"])
        category_perf = pd.DataFrame(columns=["category", "revenue", "units_sold", "order_count", "share_pct"])

    # ── 5. Process Expense Metrics ───────────────────────────────────────
    if not exp_df.empty:
        expense_breakdown = (
            exp_df.groupby("category")["amount"]
            .sum()
            .reset_index()
            .sort_values("amount", ascending=False)
            .reset_index(drop=True)
        )
        expense_trend = (
            exp_df.groupby("date")["amount"]
            .sum()
            .reset_index()
            .sort_values("date")
            .reset_index(drop=True)
        )
    else:
        expense_breakdown = pd.DataFrame(columns=["category", "amount"])
        expense_trend = pd.DataFrame(columns=["date", "amount"])

    # ── 6. Build Plain-Language Takeaways strictly in Code (Principle 1 & 2) ──
    takeaways: dict[str, str] = {}

    # Revenue takeaway
    if not revenue_trend.empty and revenue > 0:
        peak_row = revenue_trend.sort_values("revenue", ascending=False).iloc[0]
        peak_dt = pd.to_datetime(peak_row["date"]).strftime("%d %b %Y")
        takeaways["revenue_trend"] = (
            f"Revenue peaked at ₹{peak_row['revenue']:,.2f} on {peak_dt} across {total_orders} total transactions."
        )
    else:
        takeaways["revenue_trend"] = "Import sales files to track your revenue trend over time."

    # Category takeaway
    if not category_perf.empty and revenue > 0:
        top_cat = category_perf.iloc[0]
        takeaways["category_performance"] = (
            f"'{top_cat['category']}' generated the highest sales: ₹{top_cat['revenue']:,.2f} "
            f"({top_cat['share_pct']}% of all revenue)."
        )
    else:
        takeaways["category_performance"] = "Categorize your sales items to see which departments lead performance."

    # Top product takeaway
    if not top_products.empty and revenue > 0:
        top_prod = top_products.iloc[0]
        prod_share = round((top_prod["revenue"] / revenue) * 100, 1)
        takeaways["top_products"] = (
            f"'{top_prod['product']}' is your #1 earner, bringing in ₹{top_prod['revenue']:,.2f} ({prod_share}% of total sales)."
        )
    else:
        takeaways["top_products"] = "Import sales data to identify your best-selling menu or catalog items."

    # Quantity / volume takeaway
    if not top_products_by_qty.empty and total_units > 0:
        top_qty = top_products_by_qty.iloc[0]
        qty_val = int(top_qty["quantity"]) if float(top_qty["quantity"]).is_integer() else top_qty["quantity"]
        takeaways["product_volume"] = (
            f"'{top_qty['product']}' had the highest sales volume with {qty_val} units sold."
        )
    else:
        takeaways["product_volume"] = "Include quantity numbers in your sales file to monitor unit velocities."

    # Expense takeaway
    if not expense_breakdown.empty and expenses > 0:
        top_exp = expense_breakdown.iloc[0]
        exp_share = round((top_exp["amount"] / expenses) * 100, 1)
        takeaways["expense_breakdown"] = (
            f"'{top_exp['category']}' is your largest cost center, accounting for ₹{top_exp['amount']:,.2f} ({exp_share}% of total costs)."
        )
    else:
        takeaways["expense_breakdown"] = "Import expense records to visualize where your operational funds are spent."

    attention_items = get_attention_items(tenant_id)
    dow_insight = get_day_of_week_insights(tenant_id, start_date=start_date, end_date=end_date)
    slow_movers = get_slow_movers(tenant_id, start_date=start_date, end_date=end_date)

    return DashboardData(
        total_revenue=float(revenue),
        total_expenses=float(expenses),
        net_profit=float(net_profit),
        average_order_value=float(aov),
        revenue_trend=revenue_trend,
        top_products=top_products,
        expense_breakdown=expense_breakdown,
        total_transactions=int(total_orders),
        total_units_sold=float(total_units),
        expense_trend=expense_trend,
        top_products_by_qty=top_products_by_qty,
        bottom_products_by_qty=bottom_products_by_qty,
        category_performance=category_perf,
        takeaways=takeaways,
        attention_items=attention_items,
        day_of_week_insight=dow_insight,
        slow_movers=slow_movers,
    )


def get_revenue_trend(
    tenant_id: str,
    granularity: str = "daily",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch both revenue and expense series grouped by daily, weekly (ISO week),
    or monthly intervals, optionally bounded by a start and end date.
    All calculations are done in Python/Pandas backend; frontend only displays the output.
    """
    norm_granularity = granularity.lower().strip()
    if norm_granularity not in ("daily", "weekly", "monthly"):
        raise ValueError(f"Unsupported granularity: {granularity}. Choose 'daily', 'weekly', or 'monthly'.")

    start_dt = _parse_filter_date(start_date)
    end_dt = _parse_filter_date(end_date)

    with get_db() as db:
        s_query = db.query(Sales.date, Sales.revenue).filter(Sales.tenant_id == tenant_id)
        e_query = db.query(Expenses.date, Expenses.amount).filter(Expenses.tenant_id == tenant_id)

        if start_dt:
            s_query = s_query.filter(Sales.date >= start_dt)
            e_query = e_query.filter(Expenses.date >= start_dt)
        if end_dt:
            s_query = s_query.filter(Sales.date <= end_dt)
            e_query = e_query.filter(Expenses.date <= end_dt)

        sales_df = pd.read_sql(s_query.statement, db.bind)
        exp_df = pd.read_sql(e_query.statement, db.bind)

    if sales_df.empty and exp_df.empty:
        return pd.DataFrame(columns=["date", "label", "revenue", "expenses"])

    # Prepare sales timestamps
    if not sales_df.empty:
        sales_df["dt"] = pd.to_datetime(sales_df["date"])
    else:
        sales_df = pd.DataFrame(columns=["date", "revenue", "dt"])

    # Prepare expense timestamps
    if not exp_df.empty:
        exp_df["dt"] = pd.to_datetime(exp_df["date"])
        exp_df = exp_df.rename(columns={"amount": "expenses"})
    else:
        exp_df = pd.DataFrame(columns=["date", "expenses", "dt"])

    if norm_granularity == "daily":
        s_agg = sales_df.groupby("date", as_index=False)["revenue"].sum() if not sales_df.empty else pd.DataFrame(columns=["date", "revenue"])
        e_agg = exp_df.groupby("date", as_index=False)["expenses"].sum() if not exp_df.empty else pd.DataFrame(columns=["date", "expenses"])

        merged = pd.merge(s_agg, e_agg, on="date", how="outer").fillna(0.0)
        merged["dt"] = pd.to_datetime(merged["date"])
        merged = merged.sort_values("dt").reset_index(drop=True)
        merged["label"] = merged["dt"].dt.strftime("%d %b %Y")
        merged["date"] = merged["dt"].dt.strftime("%Y-%m-%d")
        return merged[["date", "label", "revenue", "expenses"]]

    elif norm_granularity == "weekly":
        if not sales_df.empty:
            sales_df["iso_year"] = sales_df["dt"].dt.isocalendar().year
            sales_df["iso_week"] = sales_df["dt"].dt.isocalendar().week
            s_agg = (
                sales_df.groupby(["iso_year", "iso_week"], as_index=False)
                .agg(revenue=("revenue", "sum"), min_date=("dt", "min"))
            )
        else:
            s_agg = pd.DataFrame(columns=["iso_year", "iso_week", "revenue", "min_date"])

        if not exp_df.empty:
            exp_df["iso_year"] = exp_df["dt"].dt.isocalendar().year
            exp_df["iso_week"] = exp_df["dt"].dt.isocalendar().week
            e_agg = (
                exp_df.groupby(["iso_year", "iso_week"], as_index=False)
                .agg(expenses=("expenses", "sum"), min_date_e=("dt", "min"))
            )
        else:
            e_agg = pd.DataFrame(columns=["iso_year", "iso_week", "expenses", "min_date_e"])

        merged = pd.merge(s_agg, e_agg, on=["iso_year", "iso_week"], how="outer").fillna(0.0)
        # Choose earliest min date available
        merged["min_date"] = np.where(merged["min_date"] != 0.0, merged["min_date"], merged["min_date_e"])
        merged = merged.sort_values(["iso_year", "iso_week"]).reset_index(drop=True)
        merged["label"] = merged.apply(lambda r: f"W{int(r['iso_week']):02d} {int(r['iso_year'])}", axis=1)
        merged["date"] = pd.to_datetime(merged["min_date"]).dt.strftime("%Y-%m-%d")
        return merged[["date", "label", "revenue", "expenses"]]

    else:  # monthly
        if not sales_df.empty:
            sales_df["period"] = sales_df["dt"].dt.to_period("M")
            s_agg = (
                sales_df.groupby("period", as_index=False)
                .agg(revenue=("revenue", "sum"), min_date=("dt", "min"))
            )
        else:
            s_agg = pd.DataFrame(columns=["period", "revenue", "min_date"])

        if not exp_df.empty:
            exp_df["period"] = exp_df["dt"].dt.to_period("M")
            e_agg = (
                exp_df.groupby("period", as_index=False)
                .agg(expenses=("expenses", "sum"), min_date_e=("dt", "min"))
            )
        else:
            e_agg = pd.DataFrame(columns=["period", "expenses", "min_date_e"])

        merged = pd.merge(s_agg, e_agg, on="period", how="outer").fillna(0.0)
        merged["min_date"] = np.where(merged["min_date"] != 0.0, merged["min_date"], merged["min_date_e"])
        merged = merged.sort_values("period").reset_index(drop=True)
        merged["label"] = pd.to_datetime(merged["min_date"]).dt.strftime("%b %Y")
        merged["date"] = pd.to_datetime(merged["min_date"]).dt.strftime("%Y-%m-%d")
        return merged[["date", "label", "revenue", "expenses"]]


DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_day_of_week_insights(
    tenant_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """
    Calculate sales performance by day of the week (Monday through Sunday),
    providing average daily revenue, transaction counts, and code-built comparison headlines.
    """
    start_dt = _parse_filter_date(start_date)
    end_dt = _parse_filter_date(end_date)

    with get_db() as db:
        q = db.query(
            Sales.date,
            Sales.revenue,
            Sales.order_id,
        ).filter(Sales.tenant_id == tenant_id)

        if start_dt:
            q = q.filter(Sales.date >= start_dt)
        if end_dt:
            q = q.filter(Sales.date <= end_dt)

        sales_df = pd.read_sql(q.statement, db.bind)

    if sales_df.empty:
        return None

    sales_df["date"] = pd.to_datetime(sales_df["date"])
    sales_df["day_index"] = sales_df["date"].dt.dayofweek  # 0=Monday, 6=Sunday
    sales_df["day_name"] = sales_df["date"].dt.day_name()

    total_rev_all = float(sales_df["revenue"].sum())

    days_data = []
    distinct_dates_by_day = sales_df.groupby("day_index")["date"].nunique().to_dict()

    for idx, day_name in enumerate(DAY_NAMES):
        sub = sales_df[sales_df["day_index"] == idx]
        if sub.empty:
            days_data.append({
                "day_index": idx,
                "day_name": day_name,
                "total_revenue": 0.0,
                "avg_revenue": 0.0,
                "order_count": 0,
                "share_pct": 0.0,
            })
            continue

        tot_rev = float(sub["revenue"].sum())
        n_dates = distinct_dates_by_day.get(idx, 1)
        avg_rev = round(tot_rev / max(1, n_dates), 2)
        n_orders = int(sub["order_id"].dropna().nunique()) if "order_id" in sub.columns else len(sub)
        share = round((tot_rev / total_rev_all) * 100.0, 1) if total_rev_all > 0 else 0.0

        days_data.append({
            "day_index": idx,
            "day_name": day_name,
            "total_revenue": round(tot_rev, 2),
            "avg_revenue": avg_rev,
            "order_count": n_orders,
            "share_pct": share,
        })

    active_days = [d for d in days_data if d["avg_revenue"] > 0]
    if not active_days:
        return None

    best = max(active_days, key=lambda x: x["avg_revenue"])
    lowest = min(active_days, key=lambda x: x["avg_revenue"])

    if best["day_name"] != lowest["day_name"] and lowest["avg_revenue"] > 0:
        pct_diff = round(((best["avg_revenue"] - lowest["avg_revenue"]) / lowest["avg_revenue"]) * 100.0, 1)
        headline = (
            f"{best['day_name']}s earn {pct_diff:+.1f}% more than {lowest['day_name']}s "
            f"(avg ₹{best['avg_revenue']:,.2f} vs ₹{lowest['avg_revenue']:,.2f} per day)."
        )
    else:
        headline = f"Peak daily revenue occurs on {best['day_name']}s averaging ₹{best['avg_revenue']:,.2f}."

    weekdays = [d for d in days_data if d["day_index"] < 5 and d["avg_revenue"] > 0]
    weekends = [d for d in days_data if d["day_index"] >= 5 and d["avg_revenue"] > 0]

    weekday_avg = float(np.mean([d["avg_revenue"] for d in weekdays])) if weekdays else 0.0
    weekend_avg = float(np.mean([d["avg_revenue"] for d in weekends])) if weekends else 0.0

    if weekend_avg > 0 and weekday_avg > 0:
        we_diff_pct = round(((weekend_avg - weekday_avg) / weekday_avg) * 100.0, 1)
        we_dir = "higher" if we_diff_pct >= 0 else "lower"
        weekend_headline = (
            f"Weekend days average {abs(we_diff_pct):.1f}% {we_dir} daily revenue "
            f"(₹{weekend_avg:,.2f}) compared to weekdays (₹{weekday_avg:,.2f})."
        )
    else:
        weekend_headline = "Insufficient weekday and weekend coverage for comparison."

    return {
        "days": days_data,
        "best_day": best["day_name"],
        "lowest_day": lowest["day_name"],
        "best_avg_revenue": best["avg_revenue"],
        "lowest_avg_revenue": lowest["avg_revenue"],
        "headline": headline,
        "weekend_headline": weekend_headline,
    }


def get_slow_movers(
    tenant_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Identify slow-moving products by calculating unit sales velocity,
    days since last transaction (relative to tenant anchor date), and actionable recommendations.
    """
    start_dt = _parse_filter_date(start_date)
    end_dt = _parse_filter_date(end_date)

    with get_db() as db:
        max_d = db.query(func.max(Sales.date)).filter(Sales.tenant_id == tenant_id).scalar()
        if not max_d:
            return []

        q = db.query(
            Sales.product,
            func.sum(Sales.quantity).label("units_sold"),
            func.sum(Sales.revenue).label("revenue"),
            func.min(Sales.date).label("first_date"),
            func.max(Sales.date).label("last_date"),
            func.count(Sales.id).label("transactions"),
        ).filter(Sales.tenant_id == tenant_id)

        if start_dt:
            q = q.filter(Sales.date >= start_dt)
        if end_dt:
            q = q.filter(Sales.date <= end_dt)

        df = pd.read_sql(q.group_by(Sales.product).statement, db.bind)

    if df.empty:
        return []

    df["units_sold"] = df["units_sold"].fillna(1.0).astype(float)
    df["revenue"] = df["revenue"].fillna(0.0).astype(float).round(2)
    df["last_date"] = pd.to_datetime(df["last_date"]).dt.date
    df["first_date"] = pd.to_datetime(df["first_date"]).dt.date

    anchor = max_d
    results = []

    for _, row in df.iterrows():
        p_name = str(row["product"])
        units = float(row["units_sold"])
        rev = float(row["revenue"])
        last_d = row["last_date"]
        first_d = row["first_date"]

        days_since_sale = (anchor - last_d).days if last_d else 0
        active_span_days = max(1, (anchor - first_d).days)
        weekly_velocity = round((units / active_span_days) * 7.0, 1)

        if days_since_sale >= 30:
            status = "Stalled"
            recommendation = "No sales in 30+ days. Consider bundling with a best-seller or running a clearance discount."
        elif weekly_velocity < 1.0:
            status = "Sluggish"
            recommendation = "Selling less than 1 unit per week. Review menu placement or consider phasing out."
        elif units <= 3:
            status = "Low Volume"
            recommendation = "Low total volume. Test customer awareness with sample promotions."
        else:
            status = "Moderate"
            recommendation = "Maintain safe minimum stock levels to avoid tied-up working capital."

        results.append({
            "product": p_name,
            "units_sold": units,
            "revenue": rev,
            "last_sold_date": str(last_d),
            "days_since_last_sale": days_since_sale,
            "weekly_velocity": weekly_velocity,
            "status": status,
            "recommendation": recommendation,
        })

    results.sort(key=lambda x: (x["weekly_velocity"], -x["days_since_last_sale"]))
    return results[:limit]

