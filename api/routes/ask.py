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
        "metric": answer.metric,
        "period": answer.period,
        "period_label": answer.period_label,
        "headline": answer.headline,
        "table": {
            "columns": [] if answer.data is None else answer.data.columns.tolist(),
            "rows": [] if answer.data is None else answer.data,
        },
    })


@router.get("/ask/history")
def ask_history(user: SessionUser = Depends(require_session)):
    """Fetch past Q&A conversations for the authenticated tenant."""
    from services.ai_service import get_chat_history
    history = get_chat_history(user.tenant_id)
    return to_jsonable(history)


@router.delete("/ask/history")
def clear_history(user: SessionUser = Depends(require_session)):
    """Clear all saved Q&A conversations for the authenticated tenant."""
    from services.ai_service import clear_chat_history
    count = clear_chat_history(user.tenant_id)
    return to_jsonable({"success": True, "deleted_count": count})

