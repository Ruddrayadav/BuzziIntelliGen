from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import SessionUser, require_session
from api.serializers import to_jsonable
from services.dashboard_service import get_dashboard_data, get_revenue_trend


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user: SessionUser = Depends(require_session),
):
    return to_jsonable(get_dashboard_data(user.tenant_id, start_date=start_date, end_date=end_date))


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


