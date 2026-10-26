"""Analytics routes backed solely by the existing analytics service."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import SessionUser, require_session
from api.serializers import to_jsonable
from services.analytics_service import compare_periods, detect_anomalies, diagnose_profit_drop, get_available_months


router = APIRouter(prefix="/api/analytics", tags=["analytics"])

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("/months")
def months(user: SessionUser = Depends(require_session)):
    return {"months": get_available_months(user.tenant_id)}


@router.get("/compare")
def compare(
    current_month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    prior_month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    user: SessionUser = Depends(require_session),
):
    try:
        return to_jsonable(compare_periods(user.tenant_id, current_month, prior_month))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/anomalies")
def anomalies(user: SessionUser = Depends(require_session)):
    return to_jsonable(detect_anomalies(user.tenant_id))


@router.get("/diagnosis")
def diagnosis(
    current_month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    prior_month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    user: SessionUser = Depends(require_session),
):
    try:
        return to_jsonable(diagnose_profit_drop(user.tenant_id, current_month, prior_month))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
