"""Dashboard route backed solely by the dashboard service."""

from fastapi import APIRouter, Depends

from api.deps import SessionUser, require_session
from api.serializers import to_jsonable
from services.dashboard_service import get_dashboard_data


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: SessionUser = Depends(require_session)):
    return to_jsonable(get_dashboard_data(user.tenant_id))
