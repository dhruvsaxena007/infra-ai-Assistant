"""
Single gateway for assistant response delivery.

Flow: Response Plan -> Dynamic Generator -> Response Memory -> compatible reply dict.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.dynamic_response_generator import generate_dynamic_response
from app.ai.response_memory import get_response_memory, record_response_memory
from app.ai.response_plan import build_response_plan
from app.core.config import settings


def _previous_responses_from_memory(memory: dict[str, Any]) -> list[dict[str, Any]]:
    sigs = memory.get("recent_response_signatures") or []
    summaries = memory.get("recent_messages_summary") or []
    out = []
    for i, sig in enumerate(sigs[-4:]):
        summary = summaries[i] if i < len(summaries) else ""
        out.append({"signature": sig, "summary": summary})
    return out


async def deliver_assistant_response(
    *,
    session_id: str,
    user_message: str,
    draft_message: str,
    response_goal: str,
    intent: str,
    assistant_mode: str,
    session_context: Optional[dict[str, Any]] = None,
    classification: Optional[dict[str, Any]] = None,
    entities: Optional[dict[str, Any]] = None,
    missing_fields: Optional[list[str]] = None,
    tool_result: Optional[dict[str, Any]] = None,
    language: str = "english",
    sentiment: str = "neutral",
) -> dict[str, Any]:
    """
    Central response delivery — used by all assistant flows.
    Returns message + suggestions + metadata; updates session_context in result.
    """
    ctx = dict(session_context or {})
    ctx["session_id"] = session_id
    ctx["last_user_message"] = user_message[:200]
    memory = get_response_memory(ctx)
    tool = {**(tool_result or {}), "message": draft_message or (tool_result or {}).get("message") or ""}

    try:
        from app.ai.conversation_state_manager import load_conversation_state

        conv_state = load_conversation_state(session_id)
        if conv_state:
            ctx["_conversation_state"] = conv_state
    except Exception:
        pass

    plan = build_response_plan(
        response_goal=response_goal,
        intent=intent,
        assistant_mode=assistant_mode,
        language=language,
        user_sentiment=sentiment,
        user_message=user_message,
        classification=classification,
        entities=entities,
        tool_result=tool,
        session_context=ctx,
        response_memory=memory,
        missing_fields=missing_fields,
        draft_message=draft_message,
    )

    previous = _previous_responses_from_memory(memory)
    generated = await generate_dynamic_response(
        plan,
        user_message,
        ctx,
        previous,
        session_id=session_id,
    )

    updated_ctx = record_response_memory(
        ctx,
        intent=intent,
        response_goal=response_goal,
        message=generated.get("message") or draft_message,
        response_signature=generated.get("response_signature") or "",
        pending_fields=missing_fields or plan.get("known_context", {}).get("pending_fields"),
        language=language,
        machine_search=(tool.get("filters") or {}) if tool.get("machines") is not None else None,
        support_issue={"intent": intent} if assistant_mode == "support" or "issue" in intent else None,
    )

    generated["updated_session_context"] = updated_ctx
    generated["response_plan"] = plan
    generated["gateway_used"] = True
    try:
        from app.ai.assistant_debug_trace import record_response_delivery
        record_response_delivery(generated)
    except Exception:
        pass
    return generated
