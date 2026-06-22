"""
Assistant turn analytics — safe logging for future dashboard (E10).
Does not change user-facing behavior.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def extract_analytics_from_response(
    response: dict,
    *,
    user_message: str,
    session_id: str,
) -> dict[str, Any]:
    """Build analytics document from standard chat API response."""
    data = response.get("data") or {}
    ctx = data.get("context") or {}
    search_status = data.get("search_status") or {}
    machines = data.get("machines") or []

    result_count = len(machines)
    exact = search_status.get("exact_match_found")
    if exact is True:
        search_success = True
    elif exact is False and result_count > 0:
        search_success = True  # alternatives found
    elif exact is False:
        search_success = False
    else:
        search_success = result_count > 0

    return {
        "session_id": session_id,
        "user_message": (user_message or "")[:500],
        "intent": ctx.get("intent") or search_status.get("intent"),
        "assistant_mode": ctx.get("assistant_mode") or data.get("assistant_mode"),
        "used_previous_context": bool(ctx.get("used_previous_context")),
        "search_success": search_success,
        "search_result_count": result_count,
        "fallback_used": bool(
            search_status.get("fallback_used")
            or ctx.get("ai_fallback_used")
        ),
        "classifier_used": ctx.get("classifier_used") or data.get("classifier"),
        "rag_scope": ctx.get("rag_scope") or data.get("rag_scope"),
        "created_at": datetime.utcnow(),
    }


async def save_turn_analytics(database, payload: dict[str, Any]) -> bool:
    """Persist turn analytics; failures are non-fatal."""
    if database is None:
        return False
    try:
        coll = getattr(database, "assistant_turn_logs", None)
        if coll is None:
            return False
        await coll.insert_one(payload)
        return True
    except Exception as exc:
        print(f"[turn_analytics] log failed: {exc}")
        return False


async def log_turn_from_response(
    database,
    session_id: str,
    user_message: str,
    response: dict,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    payload = extract_analytics_from_response(
        response,
        user_message=user_message,
        session_id=session_id,
    )
    if extra:
        payload.update(extra)
    await save_turn_analytics(database, payload)
