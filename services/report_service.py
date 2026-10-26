"""
services/report_service.py
--------------------------
Generates executive-ready monthly business intelligence PDF reports.

PRINCIPLE 1 & 2:
  The LLM never calculates numbers. All report metrics, tables, and headlines
  are computed strictly in Python/SQL by dashboard_service, analytics_service,
  attention_service, and target_service.

LIBRARY CHOICE: ReportLab
  ReportLab is a mature, pure-Python library with pre-compiled wheels for all
  major operating systems. Unlike WeasyPrint (which requires external C-libraries
  like Pango and Cairo) or pdfkit/wkhtmltopdf (which requires an external OS
  binary), ReportLab runs reliably in any Python 3.11 environment without system
  dependencies, making it ideal for robust deployment and academic review.
"""

from datetime import date, datetime
import calendar
import io
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import func

from db.database import get_db
from db.models import Expenses, Sales, User
from services.analytics_service import compare_periods
from services.attention_service import get_attention_items
from services.dashboard_service import get_dashboard_data
from services.target_service import get_target_pacing


# ─────────────────────────────────────────────────────────────────────────────
# 1. Number Formatting Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_curr(val: Optional[float]) -> str:
    if val is None or pd.isna(val):
        return "₹0.00"
    return f"₹{float(val):,.2f}"


def _fmt_pct(val: Optional[float], show_sign: bool = True) -> str:
    if val is None or pd.isna(val):
        return "new"
    sign = "+" if show_sign and val > 0 else ""
    return f"{sign}{float(val):.1f}%"


def _fmt_int(val: Optional[float]) -> str:
    if val is None or pd.isna(val):
        return "0"
    return f"{int(val):,}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tenant Context & Date Resolution
# ─────────────────────────────────────────────────────────────────────────────
def _get_tenant_business_name(tenant_id: str) -> str:
    """Fetch registered business name for the tenant."""
    with get_db() as db:
        user = db.query(User).filter(User.tenant_id == tenant_id).first()
        if user and user.business_name:
            return user.business_name.strip()
    return tenant_id.replace("_", " ").title()


def _resolve_report_month(
    tenant_id: str,
    requested_month: Optional[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[str, str, str, str]:
    """
    Validates or resolves the target month / date range.
    Returns: (month_str 'YYYY-MM', human_label 'Month YYYY', start_date 'YYYY-MM-DD', end_date 'YYYY-MM-DD').
    """
    from services.dashboard_service import validate_date_range

    if start_date is not None or end_date is not None:
        start_dt, end_dt = validate_date_range(start_date, end_date)
        s_str = start_dt.isoformat() if start_dt else ""
        e_str = end_dt.isoformat() if end_dt else ""
        period_id = f"{s_str}_{e_str}"
        human_label = f"{s_str or 'Earliest'} to {e_str or 'Latest'}"
        return period_id, human_label, s_str, e_str

    if requested_month:
        month_str = requested_month.strip()
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month_str):
            raise ValueError(f"Invalid month format '{requested_month}'. Expected YYYY-MM (e.g. 2024-01).")
    else:
        with get_db() as db:
            max_s = db.query(func.max(Sales.date)).filter(Sales.tenant_id == tenant_id).scalar()
            max_e = db.query(func.max(Expenses.date)).filter(Expenses.tenant_id == tenant_id).scalar()
        valid = [d for d in (max_s, max_e) if d is not None]
        if not valid:
            raise ValueError("No sales or expense records found for this business. Please upload data first.")
        latest_date = max(valid)
        month_str = f"{latest_date.year:04d}-{latest_date.month:02d}"

    y, m = int(month_str[:4]), int(month_str[5:7])
    last_day = calendar.monthrange(y, m)[1]
    start_date = f"{y:04d}-{m:02d}-01"
    end_date = f"{y:04d}-{m:02d}-{last_day:02d}"
    human_label = date(y, m, 1).strftime("%B %Y")

    return month_str, human_label, start_date, end_date


# ─────────────────────────────────────────────────────────────────────────────
# 3. Numbered Canvas for Professional PDF Page Footers
# ─────────────────────────────────────────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to calculate total page count and draw running footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Footer divider line
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(36, 32, letter[0] - 36, 32)

        # Footer text
        disclaimer = "Generated by BizIntel Decision Support System • Deterministic Python/SQL Engine • Confidential"
        self.drawString(36, 20, disclaimer)
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(letter[0] - 36, 20, page_str)
        self.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Main PDF Generation Engine
# ─────────────────────────────────────────────────────────────────────────────
def generate_monthly_pdf_report(
    tenant_id: str,
    month: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> bytes:
    """
    Generates a complete, multi-section monthly executive intelligence PDF report
    for the specified tenant and reporting month or date range.
    Returns raw PDF bytes.
    """
    # 1. Resolve month & tenant details
    month_str, month_label, start_date, end_date = _resolve_report_month(
        tenant_id, month, start_date=start_date, end_date=end_date
    )
    business_name = _get_tenant_business_name(tenant_id)
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # 2. Gather verified data strictly from Python/SQL services (Principle 1 & 2)
    dash = get_dashboard_data(tenant_id, start_date=start_date, end_date=end_date)

    # Check if there is any data at all for this month
    if dash.total_revenue == 0.0 and dash.total_expenses == 0.0 and dash.total_transactions == 0:
        raise ValueError(
            f"No financial transactions recorded for month '{month_str}'. "
            f"Please select a month with sales or expense data."
        )

    # Period comparison (if prior month exists)
    comparison_data = None
    try:
        comparison_data = compare_periods(tenant_id, current_month=month_str)
    except Exception:
        comparison_data = None

    # Decision support attention items
    attention_items = get_attention_items(tenant_id)

    # Monthly revenue target pacing
    target_info = None
    try:
        target_info = get_target_pacing(tenant_id, month=month_str)
    except Exception:
        target_info = None

    # 3. Setup ReportLab document
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#475569"),
    )
    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1E293B"),
    )
    bold_body_style = ParagraphStyle(
        "BoldBodyDark",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    callout_style = ParagraphStyle(
        "CalloutText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
    )

    elements: List[Any] = []

    # ── HEADER SECTION ─────────────────────────────────────────────────────────
    header_data = [
        [
            Paragraph(f"<b>{business_name.upper()}</b>", title_style),
            Paragraph(f"<b>REPORTING PERIOD</b><br/>{month_label}", ParagraphStyle("RightHeader", parent=subtitle_style, alignment=2)),
        ],
        [
            Paragraph("Monthly Executive Business Intelligence & Decision Report", subtitle_style),
            Paragraph(f"Generated: {generated_at}", ParagraphStyle("RightMeta", parent=subtitle_style, alignment=2, fontSize=8, textColor=colors.HexColor("#64748B"))),
        ],
    ]
    header_table = Table(header_data, colWidths=[340, 200])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1E3A8A"), spaceAfter=12))

    # ── EXECUTIVE SUMMARY CALLOUT ──────────────────────────────────────────────
    margin_pct = (dash.net_profit / dash.total_revenue * 100) if dash.total_revenue > 0 else 0.0
    profit_status = "profitable" if dash.net_profit >= 0 else "operating at a net loss"

    exec_sentences = [
        f"During <b>{month_label}</b>, {business_name} generated <b>{_fmt_curr(dash.total_revenue)}</b> in gross revenue "
        f"across <b>{_fmt_int(dash.total_transactions)}</b> recorded orders, with total operating expenses of <b>{_fmt_curr(dash.total_expenses)}</b>. "
        f"The business was <b>{profit_status}</b> with a net profit of <b>{_fmt_curr(dash.net_profit)}</b> "
        f"(net profit margin: <b>{margin_pct:.1f}%</b>; Average Order Value: <b>{_fmt_curr(dash.average_order_value)}</b>)."
    ]

    if comparison_data and comparison_data.prior.period_label != "None":
        rev_change = comparison_data.revenue_delta_pct
        prof_change = comparison_data.profit_delta_pct
        rev_trend = _fmt_pct(rev_change)
        prof_trend = _fmt_pct(prof_change)
        exec_sentences.append(
            f"Compared to {comparison_data.prior.period_label}, monthly revenue shifted by <b>{rev_trend}</b> "
            f"and net profit changed by <b>{prof_trend}</b>."
        )

    if target_info and target_info.get("has_target"):
        target_amt = target_info.get("target_amount", 0.0)
        pacing_status = target_info.get("pacing_status", "on_track").replace("_", " ").title()
        exec_sentences.append(
            f"Monthly revenue target is set at <b>{_fmt_curr(target_amt)}</b> "
            f"(Target status: <b>{pacing_status}</b> with <b>{target_info.get('achieved_pct', 0.0):.1f}%</b> achieved)."
        )

    summary_html = " ".join(exec_sentences)
    callout_table = Table([[Paragraph(summary_html, callout_style)]], colWidths=[540])
    callout_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    elements.append(callout_table)
    elements.append(Spacer(1, 10))

    # ── FINANCIAL KPI TABLE ────────────────────────────────────────────────────
    elements.append(Paragraph("1. Core Financial Performance", section_heading_style))

    kpi_headers = ["Key Financial Metric", f"{month_label} (Current)", "Prior Month", "MoM Delta"]
    has_prior = bool(comparison_data and comparison_data.prior.period_label != "None")
    prior_rev = _fmt_curr(comparison_data.prior.revenue) if has_prior else "—"
    prior_exp = _fmt_curr(comparison_data.prior.expenses) if has_prior else "—"
    prior_profit = _fmt_curr(comparison_data.prior.net_profit) if has_prior else "—"
    prior_margin = f"{comparison_data.prior.profit_margin_pct:.1f}%" if has_prior else "—"
    prior_orders = _fmt_int(comparison_data.prior.order_count) if has_prior else "—"
    prior_aov = _fmt_curr(comparison_data.prior.average_order_value) if has_prior else "—"

    rev_delta = _fmt_pct(comparison_data.revenue_delta_pct) if has_prior else "no earlier data"
    exp_delta = _fmt_pct(comparison_data.expense_delta_pct) if has_prior else "no earlier data"
    prof_delta = _fmt_pct(comparison_data.profit_delta_pct) if has_prior else "no earlier data"
    margin_delta = _fmt_pct(comparison_data.margin_delta_pct, show_sign=True) if has_prior else "no earlier data"
    aov_delta = _fmt_pct(comparison_data.aov_delta_pct) if has_prior else "no earlier data"

    kpi_rows = [
        kpi_headers,
        ["Total Revenue", _fmt_curr(dash.total_revenue), prior_rev, rev_delta],
        ["Total Operating Expenses", _fmt_curr(dash.total_expenses), prior_exp, exp_delta],
        ["Net Operating Profit", _fmt_curr(dash.net_profit), prior_profit, prof_delta],
        ["Net Profit Margin", f"{margin_pct:.1f}%", prior_margin, margin_delta],
        ["Total Transactions / Orders", _fmt_int(dash.total_transactions), prior_orders, "—"],
        ["Total Units Sold", _fmt_int(dash.total_units_sold), "—", "—"],
        ["Average Order Value (AOV)", _fmt_curr(dash.average_order_value), prior_aov, aov_delta],
    ]

    kpi_table = Table(kpi_rows, colWidths=[200, 120, 110, 110])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 10))

    # ── DECISION SUPPORT ATTENTION SIGNALS ─────────────────────────────────────
    elements.append(Paragraph("2. Decision Support & Operational Attention Items", section_heading_style))

    if attention_items:
        att_rows = [["Severity", "Area", "Strategic Finding & Plain-Language Takeaway"]]
        for item in attention_items[:4]:  # Show top 4 highest priority
            sev = item.get("severity", "info").upper()
            title = item.get("title", "")
            msg = item.get("message", "")
            att_rows.append([
                sev,
                title,
                Paragraph(msg, body_style),
            ])

        att_table = Table(att_rows, colWidths=[70, 120, 350])
        att_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (0, 0), (1, -1), "LEFT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        elements.append(att_table)
    else:
        all_clear = Paragraph("✓ <i>All operations healthy. No critical margin contractions, expense surges, or sales anomalies detected.</i>", body_style)
        elements.append(all_clear)

    elements.append(Spacer(1, 10))

    # ── TOP PRODUCTS TABLE ─────────────────────────────────────────────────────
    elements.append(Paragraph("3. Top 5 Revenue-Generating Catalog Items", section_heading_style))

    top_df = dash.top_products
    if isinstance(top_df, pd.DataFrame) and not top_df.empty:
        prod_rows = [["Rank", "Product Name", "Category", "Units Sold", "Revenue (₹)", "Share %"]]
        for i, row in enumerate(top_df.head(5).itertuples(), start=1):
            p_name = getattr(row, "product", "Unknown")
            cat = getattr(row, "category", "—")
            qty = getattr(row, "quantity", 0)
            rev = getattr(row, "revenue", 0.0)
            share = getattr(row, "share_pct", 0.0)
            prod_rows.append([
                str(i),
                Paragraph(str(p_name), body_style),
                str(cat) if cat and not pd.isna(cat) else "—",
                _fmt_int(qty),
                _fmt_curr(rev),
                f"{share:.1f}%",
            ])

        prod_table = Table(prod_rows, colWidths=[40, 180, 110, 70, 80, 60])
        prod_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (0, 0), (2, -1), "LEFT"),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        elements.append(prod_table)
    else:
        elements.append(Paragraph("<i>No product sales recorded for this period.</i>", body_style))

    elements.append(Spacer(1, 10))

    # ── EXPENSE CATEGORY BREAKDOWN ─────────────────────────────────────────────
    elements.append(Paragraph("4. Operating Expense Breakdown by Category", section_heading_style))

    exp_df = dash.expense_breakdown
    if isinstance(exp_df, pd.DataFrame) and not exp_df.empty:
        shift_map = {}
        if comparison_data and isinstance(comparison_data.expense_shifts, pd.DataFrame) and not comparison_data.expense_shifts.empty:
            for _, srow in comparison_data.expense_shifts.iterrows():
                shift_map[str(srow.get("category", "")).strip().lower()] = srow.get("delta_pct")

        has_shifts = bool(shift_map and comparison_data and comparison_data.prior.period_label != "None")
        if has_shifts:
            exp_rows = [["Expense Category", "Total Spend (₹)", "Share", "MoM Change"]]
            for row in exp_df.head(6).itertuples():
                c_name = getattr(row, "category", "General")
                amt = getattr(row, "amount", 0.0)
                pct = getattr(row, "percentage", 0.0)
                d_pct = shift_map.get(str(c_name).strip().lower())
                change_str = _fmt_pct(d_pct)
                exp_rows.append([
                    str(c_name),
                    _fmt_curr(amt),
                    f"{pct:.1f}%",
                    change_str,
                ])
            col_widths = [200, 120, 110, 110]
        else:
            exp_rows = [["Expense Category", "Total Spend (₹)", "Share of Operating Expenses"]]
            for row in exp_df.head(6).itertuples():
                c_name = getattr(row, "category", "General")
                amt = getattr(row, "amount", 0.0)
                pct = getattr(row, "percentage", 0.0)
                exp_rows.append([
                    str(c_name),
                    _fmt_curr(amt),
                    f"{pct:.1f}%",
                ])
            col_widths = [240, 150, 150]

        exp_table = Table(exp_rows, colWidths=col_widths)
        exp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        elements.append(exp_table)
    else:
        elements.append(Paragraph("<i>No expenses recorded for this period.</i>", body_style))

    # Build PDF with NumberedCanvas
    doc.build(elements, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
