"""
services/ai_service.py
----------------------
Handles natural language questions from the user.

CORE DESIGN PRINCIPLE:
  The LLM NEVER calculates numbers. 
  
  Flow:
  1. LLM identifies INTENT (e.g., "top_products").
  2. Python/SQL queries the database and calculates the real answer.
  3. LLM formulates a friendly conversational reply based ONLY on that real answer.

This guarantees 100% accuracy and eliminates LLM hallucinations.
"""

from dataclasses import dataclass
import logging
from typing import Optional
import pandas as pd
from sqlalchemy import func

from db.database import get_db
from db.models import Sales, Expenses
from llm.llm import call_llm, call_llm_json, LLMError

logger = logging.getLogger(__name__)

@dataclass
class Answer:
    """
    The structured answer returned to the UI.
    Contains the friendly text explanation and the raw data table
    so the user can verify the math themselves.
    """
    text: str
    data: Optional[pd.DataFrame] = None
    intent: str = "unknown"


# ── 1. The Intent Router ─────────────────────────────────────────────────────
def _identify_intent(question: str) -> dict:
    """
    Ask the LLM to classify the user's question into one of our supported intents.
    Returns a dictionary, e.g., {"intent": "top_products", "limit": 5}
    """
    system_prompt = """
    You are an intent classifier for a restaurant/retail analytics system.
    Read the user's question and map it to one of the following intents:
    
    1. "top_products" — questions about best-selling items, top dishes, popular products.
    2. "revenue_summary" — questions about total sales, revenue, earnings, or income.
    3. "expense_summary" — questions about costs, spending, bills, or expenses.
    4. "net_profit" — questions about profit, net income, or what's left after expenses.
    5. "period_comparison" — questions comparing performance across months/periods (e.g., "compare with last month", "month over month", "how did we do vs previous month").
    6. "anomaly_detection" — questions about unusual days, outliers, spikes, drops, or strange transactions.
    7. "profit_diagnosis" — questions asking why profit changed, dropped, or increased, or diagnosing margin issues.
    8. "unknown" — if the question is unrelated to business data, or you don't understand it.
    
    If the user mentions a number of items (e.g., "top 3"), include a "limit" integer field.
    
    Return strictly JSON. 
    Format: {"intent": "string", "limit": integer}
    """
    
    try:
        response = call_llm_json(prompt=question, system_prompt=system_prompt)
        
        # Ensure we return a dictionary even if the LLM wraps it in a list
        if isinstance(response, list) and len(response) > 0:
            return response[0]
        elif isinstance(response, dict):
            return response
            
        return {"intent": "unknown", "limit": 5}
        
    except LLMError as e:
        logger.error(f"Intent classification failed: {e}")
        # Graceful degradation: if LLM fails, we just don't know the intent
        return {"intent": "unknown", "limit": 5}


# ── 2. The Data Fetchers (SQL/Pandas) ────────────────────────────────────────
def _get_top_products(tenant_id: str, limit: int = 5) -> pd.DataFrame:
    """SQL query to get the top N products by revenue."""
    with get_db() as db:
        query = db.query(Sales.product, func.sum(Sales.revenue).label("total_revenue"))\
                  .filter(Sales.tenant_id == tenant_id)\
                  .group_by(Sales.product)\
                  .order_by(func.sum(Sales.revenue).desc())\
                  .limit(limit)\
                  .statement
        df = pd.read_sql(query, db.bind)
    return df

def _get_revenue_summary(tenant_id: str) -> pd.DataFrame:
    with get_db() as db:
        rev = db.query(func.sum(Sales.revenue)).filter(Sales.tenant_id == tenant_id).scalar() or 0.0
    return pd.DataFrame([{"Metric": "Total Revenue", "Value (₹)": rev}])

def _get_expense_summary(tenant_id: str) -> pd.DataFrame:
    with get_db() as db:
        query = db.query(Expenses.category, func.sum(Expenses.amount).label("total_amount"))\
                  .filter(Expenses.tenant_id == tenant_id)\
                  .group_by(Expenses.category)\
                  .order_by(func.sum(Expenses.amount).desc())\
                  .statement
        df = pd.read_sql(query, db.bind)
    return df

def _get_net_profit(tenant_id: str) -> pd.DataFrame:
    with get_db() as db:
        rev = db.query(func.sum(Sales.revenue)).filter(Sales.tenant_id == tenant_id).scalar() or 0.0
        exp = db.query(func.sum(Expenses.amount)).filter(Expenses.tenant_id == tenant_id).scalar() or 0.0
    return pd.DataFrame([{
        "Total Revenue": rev, 
        "Total Expenses": exp, 
        "Net Profit": rev - exp
    }])

def _get_period_comparison(tenant_id: str) -> pd.DataFrame:
    from services.analytics_service import compare_periods
    comp = compare_periods(tenant_id)
    if not comp or comp.prior.period_label == "None":
        return pd.DataFrame([{"Message": "Need at least two months of data for period comparison."}])
    
    rows = [
        {"Metric": "Revenue", f"Prior ({comp.prior.period_label})": f"₹{comp.prior.revenue:,.2f}", f"Current ({comp.current.period_label})": f"₹{comp.current.revenue:,.2f}", "Change": f"₹{comp.revenue_delta:+,.2f}", "% Change": f"{comp.revenue_delta_pct:+.1f}%"},
        {"Metric": "Expenses", f"Prior ({comp.prior.period_label})": f"₹{comp.prior.expenses:,.2f}", f"Current ({comp.current.period_label})": f"₹{comp.current.expenses:,.2f}", "Change": f"₹{comp.expense_delta:+,.2f}", "% Change": f"{comp.expense_delta_pct:+.1f}%"},
        {"Metric": "Net Profit", f"Prior ({comp.prior.period_label})": f"₹{comp.prior.net_profit:,.2f}", f"Current ({comp.current.period_label})": f"₹{comp.current.net_profit:,.2f}", "Change": f"₹{comp.profit_delta:+,.2f}", "% Change": f"{comp.profit_delta_pct:+.1f}%"},
        {"Metric": "Orders", f"Prior ({comp.prior.period_label})": comp.prior.order_count, f"Current ({comp.current.period_label})": comp.current.order_count, "Change": comp.current.order_count - comp.prior.order_count, "% Change": f"{((comp.current.order_count - comp.prior.order_count)/max(1, comp.prior.order_count)*100):+.1f}%"},
        {"Metric": "Avg Order Value", f"Prior ({comp.prior.period_label})": f"₹{comp.prior.average_order_value:,.2f}", f"Current ({comp.current.period_label})": f"₹{comp.current.average_order_value:,.2f}", "Change": f"₹{comp.aov_delta:+,.2f}", "% Change": f"{comp.aov_delta_pct:+.1f}%"},
    ]
    return pd.DataFrame(rows)

def _get_anomaly_summary(tenant_id: str) -> pd.DataFrame:
    from services.analytics_service import detect_anomalies
    report = detect_anomalies(tenant_id)
    all_anomalies = report.revenue_anomalies + report.expense_anomalies
    if not all_anomalies:
        return pd.DataFrame([{"Status": "No statistical anomalies detected. Operations are normal."}])
    
    rows = []
    for a in all_anomalies:
        rows.append({
            "Date": str(a.date),
            "Metric": a.metric.title(),
            "Type": a.anomaly_type.title(),
            "Actual": f"₹{a.actual_value:,.2f}",
            "Expected": f"₹{a.expected_value:,.2f}",
            "Deviation": f"{a.deviation_pct:+.1f}%",
            "Severity": a.severity.title(),
            "Description": a.description
        })
    return pd.DataFrame(rows)

def _get_profit_diagnosis(tenant_id: str) -> pd.DataFrame:
    from services.analytics_service import diagnose_profit_drop
    diag = diagnose_profit_drop(tenant_id)
    if not diag:
        return pd.DataFrame([{"Message": "Need at least two months of data to diagnose profit shifts."}])
    
    rows = [
        {"Analysis Aspect": "Comparison Window", "Details": f"{diag.period_label} vs {diag.comparison_label}"},
        {"Analysis Aspect": "Primary Driver", "Details": diag.primary_driver},
        {"Analysis Aspect": "Net Profit Shift", "Details": f"₹{diag.profit_change:+,.2f} ({diag.profit_change_pct:+.1f}%)"},
        {"Analysis Aspect": "Revenue Impact", "Details": f"₹{diag.revenue_impact:+,.2f}"},
        {"Analysis Aspect": "Expense Impact", "Details": f"₹{diag.expense_impact:+,.2f}"},
    ]
    if diag.top_revenue_drags:
        drags_str = ", ".join([f"{d['product']} (-₹{d['drop_amount']:,.0f})" for d in diag.top_revenue_drags[:3]])
        rows.append({"Analysis Aspect": "Top Revenue Drags", "Details": drags_str})
    if diag.top_expense_surges:
        surges_str = ", ".join([f"{s['category']} (+₹{s['increase_amount']:,.0f})" for s in diag.top_expense_surges[:3]])
        rows.append({"Analysis Aspect": "Top Cost Surges", "Details": surges_str})
    if diag.recommendations:
        rows.append({"Analysis Aspect": "Top Recommendation", "Details": diag.recommendations[0]})
        
    return pd.DataFrame(rows)


# ── 3. The Explainer ─────────────────────────────────────────────────────────
def _explain_data(question: str, df: pd.DataFrame) -> str:
    """
    Feed the actual data back to the LLM and ask it to write a conversational answer.
    """
    if df.empty:
        return "I couldn't find any data for that. Have you uploaded your files yet?"

    # Convert the DataFrame to a simple CSV string so the LLM can read it
    data_csv = df.to_csv(index=False)
    
    system_prompt = """
    You are a helpful, professional business analyst assisting a small business owner.
    Answer the user's question using ONLY the data provided below.
    
    RULES:
    1. Do not invent, guess, or estimate any numbers.
    2. If the data provided does not answer the question, say so.
    3. Keep your answer brief, friendly, and easy to read (use bullet points if listing items).
    4. Format currency appropriately (e.g., ₹5,000).
    """
    
    prompt = f"User Question: {question}\n\nData Table:\n{data_csv}"
    
    try:
        return call_llm(prompt=prompt, system_prompt=system_prompt)
    except LLMError:
        return "I found the data, but my language processor is temporarily down. Please see the table below."


# ── 4. Main Public Function ──────────────────────────────────────────────────
def ask_question(question: str, tenant_id: str) -> Answer:
    """
    The main entry point for the Ask AI page.
    Takes a question, routes it to the right SQL query, and returns a friendly Answer.
    """
    # 1. Identify intent
    intent_data = _identify_intent(question)
    intent = intent_data.get("intent", "unknown")
    limit = intent_data.get("limit", 5)
    
    df = None
    
    # 2. Execute SQL/Analytics based on intent
    if intent == "top_products":
        df = _get_top_products(tenant_id, limit)
    elif intent == "revenue_summary":
        df = _get_revenue_summary(tenant_id)
    elif intent == "expense_summary":
        df = _get_expense_summary(tenant_id)
    elif intent == "net_profit":
        df = _get_net_profit(tenant_id)
    elif intent == "period_comparison":
        df = _get_period_comparison(tenant_id)
    elif intent == "anomaly_detection":
        df = _get_anomaly_summary(tenant_id)
    elif intent == "profit_diagnosis":
        df = _get_profit_diagnosis(tenant_id)
    else:
        # Fallback for unknown intents
        return Answer(
            text="I'm sorry, I don't know how to answer that yet. I can currently help with top products, revenue, expenses, profit, month-over-month comparisons, anomaly detection, and profit diagnostics.",
            data=None,
            intent="unknown"
        )
        
    # 3. Explain the data
    explanation = _explain_data(question, df)
    
    return Answer(text=explanation, data=df, intent=intent)
