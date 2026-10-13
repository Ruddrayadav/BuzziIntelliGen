"""
services/dashboard_service.py
-----------------------------
Calculates KPIs and chart data for the business dashboard.

UI RULE:
  This service only queries the database and returns raw data dictionaries
  or DataFrames. It does NOT create Plotly charts or use Streamlit functions.
  The UI layer is responsible for rendering.
"""

from dataclasses import dataclass
from typing import Any
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import get_db, engine
from db.models import Sales, Expenses

@dataclass
class DashboardData:
    """
    All the data needed to render the dashboard.
    """
    # KPIs
    total_revenue: float
    total_expenses: float
    net_profit: float
    average_order_value: float
    
    # Chart Data (returned as plain dicts/lists or lightweight pandas DataFrames)
    # We use Pandas here just as a convenient transport format for the UI to plot.
    revenue_trend: pd.DataFrame
    top_products: pd.DataFrame
    expense_breakdown: pd.DataFrame


def get_dashboard_data(tenant_id: str) -> DashboardData:
    """
    Fetch and calculate all dashboard metrics for a specific tenant.
    
    This function uses SQLAlchemy's func.sum, func.count, etc. to do the heavy
    lifting in the database, rather than loading millions of rows into Python memory.
    """
    with get_db() as db:
        # ── 1. Calculate KPIs ────────────────────────────────────────────────
        
        # Total Revenue: sum of all sales revenue
        revenue = db.query(func.sum(Sales.revenue)).filter(Sales.tenant_id == tenant_id).scalar() or 0.0
        
        # Total Expenses: sum of all expense amounts
        expenses = db.query(func.sum(Expenses.amount)).filter(Expenses.tenant_id == tenant_id).scalar() or 0.0
        
        net_profit = revenue - expenses
        
        # Average Order Value (AOV)
        # We count unique order_ids. If order_id is missing, we count the row as its own order.
        unique_orders = db.query(func.count(func.distinct(Sales.order_id))).filter(Sales.tenant_id == tenant_id).scalar() or 0
        rows_without_order_id = db.query(func.count(Sales.id)).filter(
            Sales.tenant_id == tenant_id, 
            Sales.order_id == None
        ).scalar() or 0
        
        total_orders = unique_orders + rows_without_order_id
        aov = (revenue / total_orders) if total_orders > 0 else 0.0

        # ── 2. Calculate Chart Data ──────────────────────────────────────────
        
        # Revenue Trend by Date
        # Using Pandas read_sql for easier grouping and charting later
        sales_query = db.query(Sales.date, Sales.revenue).filter(Sales.tenant_id == tenant_id).statement
        sales_df = pd.read_sql(sales_query, db.bind)
        
        if not sales_df.empty:
            # Group by date and sum revenue
            revenue_trend = sales_df.groupby("date")["revenue"].sum().reset_index()
            revenue_trend = revenue_trend.sort_values("date")
        else:
            revenue_trend = pd.DataFrame(columns=["date", "revenue"])

        # Top 5 Products by Revenue
        prod_query = db.query(Sales.product, Sales.revenue).filter(Sales.tenant_id == tenant_id).statement
        prod_df = pd.read_sql(prod_query, db.bind)
        
        if not prod_df.empty:
            top_products = prod_df.groupby("product")["revenue"].sum().reset_index()
            top_products = top_products.sort_values("revenue", ascending=False).head(5)
        else:
            top_products = pd.DataFrame(columns=["product", "revenue"])

        # Expense Breakdown by Category
        exp_query = db.query(Expenses.category, Expenses.amount).filter(Expenses.tenant_id == tenant_id).statement
        exp_df = pd.read_sql(exp_query, db.bind)
        
        if not exp_df.empty:
            expense_breakdown = exp_df.groupby("category")["amount"].sum().reset_index()
        else:
            expense_breakdown = pd.DataFrame(columns=["category", "amount"])

    return DashboardData(
        total_revenue=float(revenue),
        total_expenses=float(expenses),
        net_profit=float(net_profit),
        average_order_value=float(aov),
        revenue_trend=revenue_trend,
        top_products=top_products,
        expense_breakdown=expense_breakdown,
    )
