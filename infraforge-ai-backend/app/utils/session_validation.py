"""Session id validation — prevent shared fallback ids from merging user state."""

from __future__ import annotations

_RESERVED_SESSION_IDS = frozenset({
    "default",
    "global",
    "anonymous",
    "shared",
    "none",
    "null",
    "undefined",
    "test",
})


def normalize_session_id(session_id: str | None) -> str:
    return (session_id or "").strip()


def is_valid_session_id(session_id: str | None) -> bool:
    sid = normalize_session_id(session_id)
    if len(sid) < 8:
        return False
    if sid.lower() in _RESERVED_SESSION_IDS:
        return False
    return True


def session_id_validation_error(session_id: str | None) -> dict | None:
    if is_valid_session_id(session_id):
        return None
    return {
        "stage": "validation",
        "field": "session_id",
        "reason": "invalid_or_shared_session_id",
    }
