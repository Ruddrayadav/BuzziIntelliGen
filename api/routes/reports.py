"""
api/routes/reports.py
---------------------
Routes for exporting verified business intelligence reports.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from api.deps import SessionUser, require_session
from services.report_service import generate_monthly_pdf_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly-pdf")
def export_monthly_pdf(
    month: Optional[str] = Query(
        None,
        description="Target reporting month in YYYY-MM format. If omitted, uses latest month in records.",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    user: SessionUser = Depends(require_session),
):
    """
    Generate and stream a deterministic executive intelligence PDF report
    for the authenticated tenant.
    """
    try:
        pdf_bytes = generate_monthly_pdf_report(user.tenant_id, month=month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    safe_month = month or "latest"
    filename = f"bizintel-executive-report-{safe_month}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
