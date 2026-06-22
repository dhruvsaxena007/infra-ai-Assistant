"""
Session-scoped image search context — in-memory + MongoDB persistence.
"""

from __future__ import annotations

import re

from app.database.persistent_store import load_session_doc, persist_session_fields

_STRONG_REFERENCE_TRIGGERS = [
    "this type", "this machine", "this one", "is this", "this",
    "same machine", "same type", "same",
    "ye wali machine", "ye wali", "ye machine", "yeh machine", "ye", "yeh",
    "kya ye", "kya yeh",
]

_WEAK_REFERENCE_TRIGGERS = ["available"]

_IMAGE_REFERENCE_PHRASES = [
    "is this type of machine", "this type of machine", "type of machine",
    "is this machine", "this machine", "is this", "this type", "this one", "this",
    "same machine", "same type", "same",
    "ye wali machine", "ye wali", "ye machine", "yeh machine",
    "kya ye", "kya yeh", "ye", "yeh",
]

_EXPLICIT_MACHINE_WORDS = [
    "excavator", "digger", "poclain", "jcb", "3dx", "4dx", "backhoe",
    "hydra", "crane", "bulldozer", "dozer", "road roller", "roller",
    "crawler drill", "drill rig", "drill", "drilling", "epiroc", "air roc",
    "dump truck", "dumper", "tipper", "concrete mixer", "mixer",
    "grader", "wheel loader", "loader", "forklift", "telehandler",
    "boom lift", "scissor lift", "compactor", "paver", "trencher",
    "skidder", "harvester", "rock breaker", "pipe layer",
]

_last_image_context_by_session: dict[str, dict] = {}


def _matches_word(text: str, word: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){re.escape(word)}([^a-z0-9]|$)", text) is not None


def has_strong_image_reference(text: str) -> bool:
    lowered = (text or "").lower()
    return any(_matches_word(lowered, w) for w in _STRONG_REFERENCE_TRIGGERS)


def has_weak_image_reference(text: str) -> bool:
    lowered = (text or "").lower()
    return any(_matches_word(lowered, w) for w in _WEAK_REFERENCE_TRIGGERS)


def mentions_explicit_machine(text: str) -> bool:
    lowered = (text or "").lower()
    return any(_matches_word(lowered, w) for w in _EXPLICIT_MACHINE_WORDS)


def is_image_follow_up(text: str, session_id: str) -> bool:
    if not text or session_id not in _last_image_context_by_session:
        return False
    if mentions_explicit_machine(text):
        return False
    if has_strong_image_reference(text):
        return True
    return has_weak_image_reference(text)


def _load_context(session_id: str) -> dict | None:
    session_id = (session_id or "").strip()
    if session_id in _last_image_context_by_session:
        return _last_image_context_by_session[session_id]
    doc = load_session_doc(session_id)
    ctx = (doc or {}).get("image_context")
    if ctx:
        _last_image_context_by_session[session_id] = ctx
        return ctx
    return None


def save_image_context(
    session_id: str,
    *,
    detected_machine_type: str,
    suggested_categories: list | None = None,
    search_query: str | None = None,
) -> None:
    session_id = (session_id or "").strip()
    if not session_id or not detected_machine_type:
        return

    lowered = str(detected_machine_type).strip().lower()
    if lowered in ("unknown", "other", "misc", ""):
        return

    ctx = {
        "detected_machine_type": detected_machine_type,
        "suggested_categories": suggested_categories or [detected_machine_type],
        "search_query": search_query or detected_machine_type,
    }
    _last_image_context_by_session[session_id] = ctx
    persist_session_fields(session_id, image_context=ctx)


def get_image_context(session_id: str) -> dict | None:
    session_id = (session_id or "").strip()
    return _load_context(session_id)


def clear_image_context(session_id: str) -> None:
    session_id = (session_id or "").strip()
    _last_image_context_by_session.pop(session_id, None)
    persist_session_fields(session_id, image_context={})


def inject_image_context(text: str, machine_type: str) -> str:
    t = f" {(text or '').lower()} "
    for phrase in sorted(_IMAGE_REFERENCE_PHRASES, key=len, reverse=True):
        t = re.sub(
            rf"(^|[^a-z0-9]){re.escape(phrase)}([^a-z0-9]|$)",
            " ",
            t,
            flags=re.IGNORECASE,
        )
    t = re.sub(r"\s+", " ", t).strip()
    combined = f"{machine_type} {t}".strip()
    return combined or machine_type


def resolve_message_with_image_context(session_id: str, message: str) -> tuple[str, bool]:
    message = (message or "").strip()
    ctx = get_image_context(session_id)
    if not ctx or not is_image_follow_up(message, session_id):
        return message, False

    machine_type = ctx.get("detected_machine_type") or ctx.get("search_query") or ""
    if not machine_type:
        return message, False

    return inject_image_context(message, machine_type), True


def hydrate_image_context_cache(session_id: str, ctx: dict) -> None:
    session_id = (session_id or "").strip()
    if session_id and ctx:
        _last_image_context_by_session[session_id] = ctx
