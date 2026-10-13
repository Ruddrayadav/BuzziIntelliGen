"""
app/pages/02_dashboard.py
-------------------------
Executive Business Dashboard with Advanced Analytics (Phase 5).

Provides:
- Tab 1: 📊 Executive Overview (KPIs, Daily Trend, Top Products, Expense Donut)
- Tab 2: 🔄 Period Comparison (MoM / WoW, Metric Deltas, Top Gainers & Decliners)
- Tab 3: 🚨 Anomaly Radar (Daily Outliers, Spike/Drop Detection, Severity Scoring)
- Tab 4: 🔍 Profit & Margin Diagnostics (Waterfall Chart, Root Cause Analysis, Recommendations)

UI RULE (strictly enforced):
  This file ONLY fetches data from the service layer and renders it with Plotly/Streamlit.
  There are NO database or raw aggregation calculations performed in this UI layer.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from services.dashboard_service import get_dashboard_data
from services.analytics_service import (
    get_available_months,
    compare_periods,
    detect_anomalies,
    diagnose_profit_drop,
)

# Use the logged-in user's tenant ID
TENANT_ID = st.session_state.get("tenant_id", "demo_user")
BUSINESS_NAME = st.session_state.get("business_name", "Your Business")

# ─────────────────────────────────────────────────────────────────────────────
# Page Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("📊 Business Intelligence Dashboard")
st.caption(f"Real-time analytics, automated anomaly detection, and root-cause diagnostics for **{BUSINESS_NAME}**.")

st.divider()

# Fetch baseline dashboard data
with st.spinner("Crunching analytics..."):
    base_data = get_dashboard_data(TENANT_ID)
    available_months = get_available_months(TENANT_ID)

# If no data at all, guide the user to the upload page
if base_data.total_revenue == 0 and base_data.total_expenses == 0:
    st.info("👋 No business data found yet. Head over to the **Upload Data** page to upload your sales or expenses!")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Tab Navigation
# ─────────────────────────────────────────────────────────────────────────────
tab_overview, tab_comparison, tab_anomalies, tab_diagnostics = st.tabs([
    "📊 Executive Overview",
    "🔄 Period Comparison (MoM)",
    "🚨 Anomaly Radar",
    "🔍 Profit & Margin Diagnostics"
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: EXECUTIVE OVERVIEW
# ═════════════════════════════════════════════════════════════════════════════
with tab_overview:
    st.subheader("Key Performance Indicators")
    k1, k2, k3, k4 = st.columns(4)

    k1.metric("Total Revenue", f"₹{base_data.total_revenue:,.2f}")
    k2.metric("Total Expenses", f"₹{base_data.total_expenses:,.2f}")

    profit_delta_label = "Profitable" if base_data.net_profit >= 0 else "Net Loss"
    profit_delta_color = "normal" if base_data.net_profit >= 0 else "inverse"
    k3.metric("Net Profit", f"₹{base_data.net_profit:,.2f}", delta=profit_delta_label, delta_color=profit_delta_color)

    k4.metric("Avg Order Value (AOV)", f"₹{base_data.average_order_value:,.2f}")

    st.divider()

    col_chart_left, col_chart_right = st.columns(2)

    with col_chart_left:
        st.subheader("Revenue Trend")
        if not base_data.revenue_trend.empty:
            fig_trend = px.line(
                base_data.revenue_trend,
                x="date",
                y="revenue",
                title="Daily Sales Revenue",
                labels={"date": "Date", "revenue": "Revenue (₹)"},
                markers=True,
                color_discrete_sequence=["#2563EB"]
            )
            fig_trend.update_layout(hovermode="x unified", height=380)
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("No sales data available for trend chart.")

    with col_chart_right:
        st.subheader("Top 5 Products")
        if not base_data.top_products.empty:
            top_prod_reversed = base_data.top_products.iloc[::-1]
            fig_prod = px.bar(
                top_prod_reversed,
                x="revenue",
                y="product",
                orientation="h",
                title="Top Products by Revenue",
                labels={"revenue": "Revenue (₹)", "product": "Product"},
                color="revenue",
                color_continuous_scale="Blues"
            )
            fig_prod.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig_prod, use_container_width=True)
        else:
            st.info("No product sales data available.")

    st.divider()
    st.subheader("Expense Breakdown")
    if not base_data.expense_breakdown.empty:
        fig_exp = px.pie(
            base_data.expense_breakdown,
            values="amount",
            names="category",
            title="Expenses by Category",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_exp.update_layout(height=400)
        st.plotly_chart(fig_exp, use_container_width=True)
    else:
        st.info("No expense data available for category breakdown.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: PERIOD COMPARISON (MoM / Custom)
# ═════════════════════════════════════════════════════════════════════════════
with tab_comparison:
    st.subheader("Month-over-Month Performance Comparison")
    st.caption("Compare key metrics and product/expense shifts between any two reporting months.")

    if len(available_months) < 2:
        st.warning("⚠️ At least two months of data are required to run Period-over-Period comparison. Currently, data is only recorded for: " + ", ".join(available_months))
    else:
        # Selector for comparison months
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            curr_month_sel = st.selectbox(
                "Target Month (Current):",
                options=available_months,
                index=len(available_months) - 1,
                key="mom_target_month"
            )
        with col_m2:
            default_prior_idx = max(0, available_months.index(curr_month_sel) - 1)
            prior_month_sel = st.selectbox(
                "Benchmark Month (Prior):",
                options=available_months,
                index=default_prior_idx,
                key="mom_prior_month"
            )

        comp = compare_periods(TENANT_ID, current_month=curr_month_sel, prior_month=prior_month_sel)

        if comp and comp.prior.period_label != "None":
            # Metric Deltas Cards
            c1, c2, c3, c4 = st.columns(4)

            rev_delta_str = f"₹{comp.revenue_delta:+,.2f} ({comp.revenue_delta_pct:+.1f}%)"
            c1.metric(
                f"Revenue ({comp.current.period_label})",
                f"₹{comp.current.revenue:,.2f}",
                delta=rev_delta_str
            )

            exp_delta_str = f"₹{comp.expense_delta:+,.2f} ({comp.expense_delta_pct:+.1f}%)"
            # Invert delta color: expense increase is unfavorable (red)
            c2.metric(
                f"Expenses ({comp.current.period_label})",
                f"₹{comp.current.expenses:,.2f}",
                delta=exp_delta_str,
                delta_color="inverse"
            )

            prof_delta_str = f"₹{comp.profit_delta:+,.2f} ({comp.profit_delta_pct:+.1f}%)"
            c3.metric(
                f"Net Profit ({comp.current.period_label})",
                f"₹{comp.current.net_profit:,.2f}",
                delta=prof_delta_str
            )

            aov_delta_str = f"₹{comp.aov_delta:+,.2f} ({comp.aov_delta_pct:+.1f}%)"
            c4.metric(
                f"AOV ({comp.current.period_label})",
                f"₹{comp.current.average_order_value:,.2f}",
                delta=aov_delta_str
            )

            st.divider()

            # Product Gainers & Decliners
            st.subheader("Product Performance Shifts")
            col_gainers, col_decliners = st.columns(2)

            with col_gainers:
                st.markdown("##### 🚀 Top Growth Products (Gainers)")
                if comp.top_gainers:
                    gainers_df = pd.DataFrame(comp.top_gainers)
                    fig_gainers = px.bar(
                        gainers_df,
                        x="delta",
                        y="product",
                        orientation="h",
                        title="Top Revenue Growth Items (₹)",
                        labels={"delta": "Revenue Increase (₹)", "product": "Product"},
                        color_discrete_sequence=["#10B981"]
                    )
                    fig_gainers.update_layout(yaxis={'categoryorder': 'total ascending'}, height=300)
                    st.plotly_chart(fig_gainers, use_container_width=True)
                else:
                    st.info("No products experienced revenue growth in this period.")

            with col_decliners:
                st.markdown("##### 🔻 Top Revenue Decliners")
                if comp.top_decliners:
                    decliners_df = pd.DataFrame(comp.top_decliners)
                    fig_decliners = px.bar(
                        decliners_df,
                        x="delta",
                        y="product",
                        orientation="h",
                        title="Largest Revenue Declines (₹)",
                        labels={"delta": "Revenue Drop (₹)", "product": "Product"},
                        color_discrete_sequence=["#EF4444"]
                    )
                    fig_decliners.update_layout(yaxis={'categoryorder': 'total descending'}, height=300)
                    st.plotly_chart(fig_decliners, use_container_width=True)
                else:
                    st.info("No products experienced sales decline in this period.")

            # Expense shifts
            st.divider()
            st.subheader("Operating Cost Shifts by Category")
            if not comp.expense_shifts.empty:
                st.dataframe(
                    comp.expense_shifts.style.format({
                        "prior_amount": "₹{:,.2f}",
                        "current_amount": "₹{:,.2f}",
                        "delta": "₹{:,.2f}",
                        "delta_pct": "{:+.1f}%"
                    }),
                    use_container_width=True
                )
            else:
                st.info("No expense categories to compare.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: ANOMALY RADAR
# ═════════════════════════════════════════════════════════════════════════════
with tab_anomalies:
    st.subheader("🚨 Statistical Anomaly Radar")
    st.caption("Automated detection of daily sales spikes/drops and unusual operational cost surges.")

    # Sensitivity selector
    col_sens, _ = st.columns([2, 4])
    with col_sens:
        sensitivity = st.slider("Detection Sensitivity (Z-score threshold):", min_value=1.5, max_value=3.5, value=2.0, step=0.25)

    report = detect_anomalies(TENANT_ID, sensitivity=sensitivity)

    a_c1, a_c2, a_c3 = st.columns(3)
    a_c1.metric("Total Anomalies Detected", report.total_anomalies)
    a_c2.metric("Revenue Anomalies", len(report.revenue_anomalies))
    a_c3.metric("Expense Anomalies", len(report.expense_anomalies))

    st.divider()

    # Timeline Chart
    if not report.timeline_df.empty:
        st.subheader("Daily Activity & Outliers Timeline")
        fig_ano = go.Figure()

        # Revenue line
        fig_ano.add_trace(go.Scatter(
            x=report.timeline_df["date"],
            y=report.timeline_df["revenue"],
            mode="lines",
            name="Daily Revenue",
            line={"color": "#3B82F6", "width": 2}
        ))

        # Expenses line
        fig_ano.add_trace(go.Scatter(
            x=report.timeline_df["date"],
            y=report.timeline_df["amount"],
            mode="lines",
            name="Daily Expenses",
            line={"color": "#F59E0B", "width": 1.5, "dash": "dot"}
        ))

        # Overlay Revenue Anomalies
        if report.revenue_anomalies:
            ano_rev_dates = [a.date for a in report.revenue_anomalies]
            ano_rev_vals = [a.actual_value for a in report.revenue_anomalies]
            ano_rev_text = [a.description for a in report.revenue_anomalies]
            fig_ano.add_trace(go.Scatter(
                x=ano_rev_dates,
                y=ano_rev_vals,
                mode="markers",
                name="Revenue Outlier",
                text=ano_rev_text,
                marker={"color": "#EF4444", "size": 11, "symbol": "circle"}
            ))

        # Overlay Expense Anomalies
        if report.expense_anomalies:
            ano_exp_dates = [a.date for a in report.expense_anomalies]
            ano_exp_vals = [a.actual_value for a in report.expense_anomalies]
            ano_exp_text = [a.description for a in report.expense_anomalies]
            fig_ano.add_trace(go.Scatter(
                x=ano_exp_dates,
                y=ano_exp_vals,
                mode="markers",
                name="Expense Outlier",
                text=ano_exp_text,
                marker={"color": "#8B5CF6", "size": 11, "symbol": "diamond"}
            ))

        fig_ano.update_layout(
            hovermode="x unified",
            height=420,
            xaxis_title="Date",
            yaxis_title="Amount (₹)"
        )
        st.plotly_chart(fig_ano, use_container_width=True)

    # Detailed Anomaly List
    all_anomalies = report.revenue_anomalies + report.expense_anomalies
    if all_anomalies:
        st.subheader("Detected Anomalies Log")
        ano_table_data = []
        for a in all_anomalies:
            ano_table_data.append({
                "Date": str(a.date),
                "Metric": a.metric.title(),
                "Type": a.anomaly_type.title(),
                "Actual (₹)": f"₹{a.actual_value:,.2f}",
                "Expected (₹)": f"₹{a.expected_value:,.2f}",
                "Deviation": f"{a.deviation_pct:+.1f}%",
                "Z-Score": f"{a.z_score:+.2f}",
                "Severity": "🔴 Critical" if a.severity == "critical" else ("🟡 Warning" if a.severity == "warning" else "🔵 Info"),
                "Event Description": a.description
            })
        st.dataframe(pd.DataFrame(ano_table_data), use_container_width=True)
    else:
        st.success("✅ No operational anomalies detected. Daily sales and expenses are within normal statistical ranges.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: PROFIT & MARGIN DIAGNOSTICS
# ═════════════════════════════════════════════════════════════════════════════
with tab_diagnostics:
    st.subheader("🔍 Root Cause Profit & Margin Diagnostics")
    st.caption("Decomposes changes in net profit into revenue contraction vs expense inflation, pinpointing causal drivers.")

    if len(available_months) < 2:
        st.warning("⚠️ At least two months of data are required to run Profit Diagnostics.")
    else:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            diag_curr_month = st.selectbox(
                "Target Month to Diagnose:",
                options=available_months,
                index=len(available_months) - 1,
                key="diag_target_month"
            )
        with col_d2:
            default_p_idx = max(0, available_months.index(diag_curr_month) - 1)
            diag_prior_month = st.selectbox(
                "Base Comparison Month:",
                options=available_months,
                index=default_p_idx,
                key="diag_prior_month"
            )

        diag = diagnose_profit_drop(TENANT_ID, current_month=diag_curr_month, prior_month=diag_prior_month)

        if diag:
            # Primary Driver Banner
            if diag.is_profit_down:
                st.error(f"⚠️ **Primary Diagnosis: {diag.primary_driver}**\n\nNet profit dropped by **₹{abs(diag.profit_change):,.2f}** ({diag.profit_change_pct:+.1f}%) in {diag.period_label} compared to {diag.comparison_label}.")
            else:
                st.success(f"📈 **Primary Diagnosis: {diag.primary_driver}**\n\nNet profit expanded by **₹{diag.profit_change:,.2f}** ({diag.profit_change_pct:+.1f}%) in {diag.period_label} compared to {diag.comparison_label}.")

            # Waterfall Chart
            st.divider()
            st.subheader("Net Profit Waterfall Attribution")
            if not diag.waterfall_df.empty:
                fig_waterfall = go.Figure(go.Waterfall(
                    name="Profit Attribution",
                    orientation="v",
                    measure=diag.waterfall_df["measure"].tolist(),
                    x=diag.waterfall_df["label"].tolist(),
                    textposition="outside",
                    text=[f"₹{val:+,.0f}" for val in diag.waterfall_df["value"]],
                    y=diag.waterfall_df["value"].tolist(),
                    connector={"line": {"color": "rgb(100, 116, 139)"}},
                    increasing={"marker": {"color": "#10B981"}},
                    decreasing={"marker": {"color": "#EF4444"}},
                    totals={"marker": {"color": "#3B82F6"}}
                ))
                fig_waterfall.update_layout(
                    title=f"Net Profit Bridge: {diag.comparison_label} → {diag.period_label}",
                    height=420,
                    showlegend=False
                )
                st.plotly_chart(fig_waterfall, use_container_width=True)

            # Key Insights & Actionable Recommendations
            col_ins, col_rec = st.columns(2)
            with col_ins:
                st.markdown("### 📋 Key Findings")
                for item in diag.key_insights:
                    st.markdown(f"- {item}")

            with col_rec:
                st.markdown("### 💡 Recommended Actions")
                for rec in diag.recommendations:
                    st.markdown(f"- **Action:** {rec}")

            # Drill down into top drags & cost surges
            st.divider()
            col_drag, col_surge = st.columns(2)

            with col_drag:
                st.markdown("#### 📉 Products Dragging Revenue Down")
                if diag.top_revenue_drags:
                    st.dataframe(pd.DataFrame(diag.top_revenue_drags).rename(columns={
                        "product": "Product",
                        "drop_amount": "Revenue Lost (₹)",
                        "pct_change": "Change (%)",
                        "contribution_pct": "Contribution to Drop (%)"
                    }), use_container_width=True)
                else:
                    st.info("No single product caused a significant revenue drop.")

            with col_surge:
                st.markdown("#### 💸 Surging Cost Categories")
                if diag.top_expense_surges:
                    st.dataframe(pd.DataFrame(diag.top_expense_surges).rename(columns={
                        "category": "Expense Category",
                        "increase_amount": "Increase (₹)",
                        "pct_change": "Inflation (%)",
                        "contribution_pct": "Share of Cost Hike (%)"
                    }), use_container_width=True)
                else:
                    st.info("Operating expenses did not experience significant category inflation.")
