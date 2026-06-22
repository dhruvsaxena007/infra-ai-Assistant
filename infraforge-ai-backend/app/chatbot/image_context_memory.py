"""
Session-scoped image search context — backend single authority (IMG-1).

In-memory cache + MongoDB persistence with expiry and full turn metadata.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.database.persistent_store import load_session_doc, persist_session_fields

_STRONG_REFERENCE_TRIGGERS = [
    "this type", "this machine", "this one", "is this", "this",
    "same machine", "same type", "same",
    "ye wali machine", "ye wali", "ye machine", "yeh machine", "ye", "yeh",
    "kya ye", "kya yeh",
    "similar", "isi type", "aisi machine", "jaisi",
    "exact same", "bilkul same",
]

_WEAK_REFERENCE_TRIGGERS = [
    "available", "milega", "milegi", "milti", "milta",
    "under", "rent", "operator",
]

_IMAGE_REFERENCE_PHRASES = [
    "is this type of machine", "this type of machine", "type of machine",
    "is this machine", "this machine", "is this", "this type", "this one", "this",
    "same machine", "same type", "same",
    "ye wali machine", "ye wali", "ye machine", "yeh machine",
    "kya ye", "kya yeh", "ye", "yeh",
    "similar machines", "similar machine", "exact same machine",
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

_SUPPORT_BLOCK_INTENTS = frozenset({
    "refund_return", "order_issue", "payment_issue", "booking_issue",
    "support", "help", "document_question", "document_qa", "greeting",
    "frustration", "abusive", "out_of_scope",
})

_last_image_context_by_session: dict[str, dict] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    if not text:
        return False
    ctx = get_image_context(session_id)
    if not ctx:
        return False
    if mentions_explicit_machine(text):
        return False
    if has_strong_image_reference(text):
        return True
    return has_weak_image_reference(text)


def should_apply_image_context(text: str, session_id: str, *, router_intent: str | None = None) -> bool:
    """Image context must not leak into support/off-topic/document turns."""
    if router_intent and router_intent in _SUPPORT_BLOCK_INTENTS:
        return False
    return is_image_follow_up(text, session_id)


def _is_expired(ctx: dict) -> bool:
    expires = ctx.get("expires_at")
    if not expires:
        return False
    try:
        exp = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return _utcnow() > exp
    except (TypeError, ValueError):
        return False


def _load_context(session_id: str) -> dict | None:
    session_id = (session_id or "").strip()
    if session_id in _last_image_context_by_session:
        ctx = _last_image_context_by_session[session_id]
        if _is_expired(ctx):
            clear_image_context(session_id)
            return None
        return ctx
    doc = load_session_doc(session_id)
    ctx = (doc or {}).get("image_context")
    if ctx:
        if _is_expired(ctx):
            clear_image_context(session_id)
            return None
        _last_image_context_by_session[session_id] = ctx
        return ctx
    return None


def save_image_context(
    session_id: str,
    *,
    detected_machine_type: str | None = None,
    suggested_categories: list | None = None,
    search_query: str | None = None,
    upload_id: str | None = None,
    detected_category: str | None = None,
    confidence: float | None = None,
    classifier_used: str | None = None,
    image_intent: str | None = None,
    search_mode: str | None = None,
    full_context: dict | None = None,
) -> None:
    session_id = (session_id or "").strip()
    if not session_id:
        return

    if full_context:
        ctx = dict(full_context)
    else:
        cat = detected_category or detected_machine_type
        if not cat:
            return
        lowered = str(cat).strip().lower()
        if lowered in ("unknown", "other", "misc", ""):
            return
        ctx = {
            "upload_id": upload_id or "",
            "detected_category": lowered,
            "detected_machine_type": lowered,
            "suggested_categories": suggested_categories or [lowered],
            "search_query": search_query or lowered,
            "confidence": float(confidence or 0),
            "classifier_used": classifier_used or "unknown",
            "image_intent": image_intent or "unclear",
            "search_mode": search_mode or "none",
        }

    now = _utcnow()
    ctx.setdefault("created_at", now.isoformat())
    ctx["expires_at"] = (
        now + timedelta(seconds=settings.IMAGE_CONTEXT_TTL_SECONDS)
    ).isoformat()

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


def resolve_message_with_image_context(
    session_id: str,
    message: str,
    *,
    router_intent: str | None = None,
) -> tuple[str, bool]:
    message = (message or "").strip()
    if not should_apply_image_context(message, session_id, router_intent=router_intent):
        return message, False

    ctx = get_image_context(session_id)
    if not ctx:
        return message, False

    machine_type = (
        ctx.get("detected_category")
        or ctx.get("detected_machine_type")
        or ctx.get("search_query")
        or ""
    )
    if not machine_type:
        return message, False

    return inject_image_context(message, machine_type), True


def hydrate_image_context_cache(session_id: str, ctx: dict) -> None:
    session_id = (session_id or "").strip()
    if session_id and ctx and not _is_expired(ctx):
        _last_image_context_by_session[session_id] = ctx
