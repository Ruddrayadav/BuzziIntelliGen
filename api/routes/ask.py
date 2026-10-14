"""Ask-AI route backed solely by the existing AI service."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import SessionUser, require_session
from api.schemas import AskRequest
from api.serializers import to_jsonable
from services.ai_service import ask_question


router = APIRouter(prefix="/api", tags=["ask ai"])


@router.post("/ask")
def ask(payload: AskRequest, user: SessionUser = Depends(require_session)):
    answer = ask_question(payload.question, user.tenant_id)
    if answer.intent == "ai_unavailable":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=answer.text,
        )
    return to_jsonable({
        "text": answer.text,
        "intent": answer.intent,
        "table": {
            "columns": [] if answer.data is None else answer.data.columns.tolist(),
            "rows": [] if answer.data is None else answer.data,
        },
    })
