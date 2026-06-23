from fastapi import APIRouter
from pydantic import BaseModel

from app.chatbot.chatbot_service import chatbot_response
from app.database.mongodb import database
from app.utils.response import error_response
from app.utils.session_validation import is_valid_session_id, normalize_session_id, session_id_validation_error

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    selected_machine_id: str | None = None


class SessionResetRequest(BaseModel):
    session_id: str


@router.post("/session/reset")
async def reset_session(request: SessionResetRequest):
    """Clear backend session memory (filters, pending clarification, context)."""
    from app.ai.conversation_state_manager import reset_conversation_session
    from app.utils.response import success_response

    session_id = normalize_session_id(request.session_id)
    err = session_id_validation_error(session_id)
    if err:
        return error_response(
            message="A valid session_id is required",
            error=err,
        )

    state = reset_conversation_session(session_id)
    return success_response(
        message="Session reset successfully",
        data={"session_id": session_id, "active_flow": state.get("active_flow")},
    )


@router.post("/chat")
async def chat(request: ChatRequest):
    """AI chatbot — thin route; all routing in assistant_router."""

    session_id = normalize_session_id(request.session_id)
    err = session_id_validation_error(session_id)
    if err:
        return error_response(
            message="A valid session_id is required",
            error=err,
        )

    message = (request.message or "").strip()
    if not message:
        return error_response(
            message="message is required",
            error={"stage": "validation", "field": "message"},
        )

    selected_machine_id = (request.selected_machine_id or "").strip() or None
    return await chatbot_response(
        session_id,
        message,
        database,
        selected_machine_id=selected_machine_id,
    )
