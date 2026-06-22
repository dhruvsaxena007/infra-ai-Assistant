"""
Conversation history — in-memory cache + MongoDB persistence across restarts.
"""

from __future__ import annotations

from typing import Any

from app.database.persistent_store import load_session_doc, persist_session_fields

_session_histories: dict[str, list[dict[str, str]]] = {}


def _get_or_create_history(session_id: str) -> list[dict[str, str]]:
    session_id = (session_id or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    if session_id not in _session_histories:
        doc = load_session_doc(session_id)
        if doc and doc.get("history"):
            _session_histories[session_id] = list(doc["history"])
        else:
            _session_histories[session_id] = []
    return _session_histories[session_id]


def save_conversation(session_id: str, user_message: str, ai_reply: str) -> None:
    history = _get_or_create_history(session_id)

    user_message = (user_message or "").strip()
    ai_reply = (ai_reply or "").strip()

    if not user_message and not ai_reply:
        return

    if user_message:
        history.append({"role": "user", "content": user_message})
    if ai_reply:
        history.append({"role": "assistant", "content": ai_reply})

    persist_session_fields(session_id, history=history[-20:])


def get_conversation_history(session_id: str) -> list[dict[str, Any]]:
    history = _get_or_create_history(session_id)
    return [{"role": item["role"], "content": item["content"]} for item in history]


def get_conversation_history_as_text(session_id: str) -> str:
    history = _get_or_create_history(session_id)
    if not history:
        return ""

    lines: list[str] = []
    for item in history:
        prefix = "User" if item["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {item['content']}")
    return "\n".join(lines)


def clear_conversation(session_id: str) -> None:
    session_id = (session_id or "").strip()
    history = _get_or_create_history(session_id)
    history.clear()
    _session_histories.pop(session_id, None)
    persist_session_fields(
        session_id,
        history=[],
        filters={},
        pending_clarification={},
        recommendation_context={},
    )
    try:
        from app.chatbot.chatbot_service import invalidate_session_cache

        invalidate_session_cache(session_id)
    except ImportError:
        pass


def hydrate_history_cache(session_id: str, history: list) -> None:
    """Called on server startup warm-up."""
    session_id = (session_id or "").strip()
    if session_id and history:
        _session_histories[session_id] = list(history)
