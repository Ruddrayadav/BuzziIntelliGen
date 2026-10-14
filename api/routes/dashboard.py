from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import SessionUser, require_session
from api.serializers import to_jsonable
from services.dashboard_service import get_dashboard_data, get_revenue_trend


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: SessionUser = Depends(require_session)):
    return to_jsonable(get_dashboard_data(user.tenant_id))


@router.get("/dashboard/trend")
def dashboard_trend(
    granularity: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    user: SessionUser = Depends(require_session),
):
    try:
        trend_df = get_revenue_trend(user.tenant_id, granularity)
        return to_jsonable(trend_df)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

