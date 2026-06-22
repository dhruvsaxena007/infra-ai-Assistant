"""
Per-session usage limits for image search and voice messages.

In-memory cache + MongoDB persistence via usage_limits on assistant_sessions.
"""

from __future__ import annotations

from app.core.config import settings
from app.database.persistent_store import load_session_doc, persist_session_fields

_usage_by_session: dict[str, dict[str, int]] = {}

_EMPTY_USAGE = {"image_search_count": 0, "voice_message_count": 0}


def _normalize_usage(raw: dict | None) -> dict[str, int]:
    raw = raw or {}
    return {
        "image_search_count": int(raw.get("image_search_count") or 0),
        "voice_message_count": int(raw.get("voice_message_count") or 0),
    }


def get_session_usage(session_id: str) -> dict[str, int]:
    session_id = (session_id or "").strip()
    if not session_id:
        return dict(_EMPTY_USAGE)

    if session_id in _usage_by_session:
        return dict(_usage_by_session[session_id])

    doc = load_session_doc(session_id)
    usage = _normalize_usage((doc or {}).get("usage_limits"))
    _usage_by_session[session_id] = usage
    return dict(usage)


def build_session_usage_payload(session_id: str) -> dict[str, int]:
    usage = get_session_usage(session_id)
    return {
        "image_search_count": usage["image_search_count"],
        "image_search_limit": settings.IMAGE_SEARCH_LIMIT_PER_SESSION,
        "voice_message_count": usage["voice_message_count"],
        "voice_message_limit": settings.VOICE_MESSAGE_LIMIT_PER_SESSION,
    }


def check_image_search_allowed(session_id: str) -> tuple[bool, int, int]:
    usage = get_session_usage(session_id)
    current = usage["image_search_count"]
    limit = settings.IMAGE_SEARCH_LIMIT_PER_SESSION
    return current < limit, current, limit


def check_voice_allowed(session_id: str) -> tuple[bool, int, int]:
    usage = get_session_usage(session_id)
    current = usage["voice_message_count"]
    limit = settings.VOICE_MESSAGE_LIMIT_PER_SESSION
    return current < limit, current, limit


def consume_image_search(session_id: str) -> tuple[bool, int, int]:
    allowed, current, limit = check_image_search_allowed(session_id)
    if not allowed:
        return False, current, limit

    session_id = (session_id or "").strip()
    usage = get_session_usage(session_id)
    usage["image_search_count"] = usage["image_search_count"] + 1
    _usage_by_session[session_id] = usage
    persist_session_fields(session_id, usage_limits=usage)
    return True, usage["image_search_count"], limit


def consume_voice_message(session_id: str) -> tuple[bool, int, int]:
    allowed, current, limit = check_voice_allowed(session_id)
    if not allowed:
        return False, current, limit

    session_id = (session_id or "").strip()
    usage = get_session_usage(session_id)
    usage["voice_message_count"] = usage["voice_message_count"] + 1
    _usage_by_session[session_id] = usage
    persist_session_fields(session_id, usage_limits=usage)
    return True, usage["voice_message_count"], limit


def reset_session_usage(session_id: str) -> None:
    session_id = (session_id or "").strip()
    if not session_id:
        return
    usage = dict(_EMPTY_USAGE)
    _usage_by_session[session_id] = usage
    persist_session_fields(session_id, usage_limits=usage)


def hydrate_usage_limits_cache(session_id: str, usage_limits: dict) -> None:
    session_id = (session_id or "").strip()
    if session_id and usage_limits:
        _usage_by_session[session_id] = _normalize_usage(usage_limits)
