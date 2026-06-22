from fastapi import APIRouter
from pydantic import BaseModel

from app.ai.rules_understanding import understand_user_text_rules
from app.chatbot.chatbot_service import chatbot_response
from app.database.mongodb import database
from app.utils.response import error_response

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    AI chatbot endpoint. Rules-first parsing in chatbot_service; no extra Groq
    call on this route (text understanding is deterministic).
    """

    session_id = (request.session_id or "").strip()
    if not session_id:
        return error_response(
            message="session_id is required",
            error={"stage": "validation", "field": "session_id"},
        )

    message = (request.message or "").strip()
    if not message:
        return error_response(
            message="message is required",
            error={"stage": "validation", "field": "message"},
        )

    understanding_result = understand_user_text_rules(message)
    extracted_data = (
        understanding_result.get("data", {})
        if understanding_result.get("success")
        else {}
    )

    enhanced_query_parts = []
    if extracted_data.get("machine_type"):
        enhanced_query_parts.append(extracted_data["machine_type"])
    if extracted_data.get("city"):
        enhanced_query_parts.append(extracted_data["city"])
    if extracted_data.get("max_price"):
        enhanced_query_parts.append(f"under {extracted_data['max_price']}")
    if extracted_data.get("intent") == "cheaper_options":
        enhanced_query_parts.append("cheap budget low price")

    enhanced_query = " ".join(enhanced_query_parts) or message

    response = await chatbot_response(session_id, message, database)

    if isinstance(response, dict) and response.get("data") is not None:
        response["data"]["input"] = {
            "original_message": message,
            "enhanced_query": enhanced_query,
            "text_understanding": extracted_data,
        }

    return response
