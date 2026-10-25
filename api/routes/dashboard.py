from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import SessionUser, require_session
from api.serializers import to_jsonable
from services.dashboard_service import get_dashboard_data, get_revenue_trend


class SetTargetRequest(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Target month in YYYY-MM format")
    target_amount: float = Field(..., gt=0, description="Monthly revenue target amount")


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user: SessionUser = Depends(require_session),
):
    try:
        return to_jsonable(get_dashboard_data(user.tenant_id, start_date=start_date, end_date=end_date))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/dashboard/trend")
def dashboard_trend(
    granularity: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user: SessionUser = Depends(require_session),
):
    try:
        trend_df = get_revenue_trend(
            user.tenant_id,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
        )
        return to_jsonable(trend_df)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/dashboard/attention")
def dashboard_attention(user: SessionUser = Depends(require_session)):
    from services.attention_service import get_attention_items
    return to_jsonable(get_attention_items(user.tenant_id))


@router.get("/dashboard/day-of-week")
def dashboard_day_of_week(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user: SessionUser = Depends(require_session),
):
    from services.dashboard_service import get_day_of_week_insights
    try:
        return to_jsonable(get_day_of_week_insights(user.tenant_id, start_date=start_date, end_date=end_date))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/dashboard/slow-movers")
def dashboard_slow_movers(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(10, ge=1, le=50),
    user: SessionUser = Depends(require_session),
):
    from services.dashboard_service import get_slow_movers
    try:
        return to_jsonable(get_slow_movers(user.tenant_id, start_date=start_date, end_date=end_date, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/dashboard/target")
def get_target(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    user: SessionUser = Depends(require_session),
):
    from services.target_service import get_target_pacing
    return to_jsonable(get_target_pacing(user.tenant_id, month=month))


@router.post("/dashboard/target")
def set_target(
    payload: SetTargetRequest,
    user: SessionUser = Depends(require_session),
):
    from services.target_service import set_monthly_target
    try:
        result = set_monthly_target(user.tenant_id, payload.month, payload.target_amount)
        return to_jsonable(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/dashboard/target")
def delete_target(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    user: SessionUser = Depends(require_session),
):
    from services.target_service import delete_monthly_target
    deleted = delete_monthly_target(user.tenant_id, month)
    return {"deleted": deleted, "month": month}
