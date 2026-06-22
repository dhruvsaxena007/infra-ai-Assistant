"""
User Memory Profile — safe long-term returning-user preferences.

Separate from Conversation State Manager (session-scoped).
Never stores sensitive support/payment/document/raw message data.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

from app.chatbot.language import detect_query_language, pick_lang

_PROFILE_CTX: ContextVar[Optional[dict[str, Any]]] = ContextVar("user_memory_profile", default=None)
_PROFILE_META_CTX: ContextVar[Optional[dict[str, Any]]] = ContextVar("user_profile_meta", default=None)

SENSITIVE_INTENTS = frozenset({
    "payment_issue", "refund_return", "order_issue", "delivery_issue",
    "delivery_logistics", "invoice_issue", "security_deposit",
    "complaint", "support_request", "human_handover", "contact_owner",
    "document_question", "frustration",
})

MACHINE_SEARCH_INTENTS = frozenset({
    "machine_search", "rent_machine", "buy_machine", "machine_availability",
    "price_query", "cheaper_option_query", "higher_budget_query",
    "followup_search_refinement", "machine_recommendation", "machine_brand_query",
})

SIGNAL_THRESHOLD = 2
MAX_CATEGORIES = 6
MAX_BRANDS = 6

_STYLE_SHORT_RE = re.compile(r"\b(short answer|brief|concise|short me)\b", re.I)
_STYLE_DETAILED_RE = re.compile(r"\b(detailed|detail me|explain fully)\b", re.I)
_STYLE_PROFESSIONAL_RE = re.compile(r"\b(professional manner|formal tone)\b", re.I)
_STYLE_HINGLISH_RE = re.compile(r"\b(hindi me|hinglish me|hindi mein|hinglish mein)\b", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_profile_identity(
    session_id: str,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Resolve profile key from authenticated user or anonymous session."""
    session_id = (session_id or "").strip()
    user_id = (user_id or "").strip() or None
    if user_id:
        return {
            "profile_id": f"user:{user_id}",
            "user_id": user_id,
            "anonymous_session_key": None,
            "profile_source": "authenticated",
        }
    if session_id:
        return {
            "profile_id": f"anon:{session_id}",
            "user_id": None,
            "anonymous_session_key": session_id,
            "profile_source": "anonymous_session",
        }
    return {
        "profile_id": None,
        "user_id": None,
        "anonymous_session_key": None,
        "profile_source": "none",
    }


def empty_user_profile(
    *,
    profile_id: str | None = None,
    user_id: str | None = None,
    anonymous_session_key: str | None = None,
    profile_source: str = "none",
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "profile_id": profile_id or f"profile-{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "anonymous_session_key": anonymous_session_key,
        "name": None,
        "preferred_language": None,
        "preferred_city": None,
        "preferred_state": None,
        "common_machine_categories": [],
        "common_brands": [],
        "common_listing_type": None,
        "common_budget_range": {"min": None, "max": None, "currency": "INR"},
        "response_preferences": {
            "style": None,
            "show_suggestions": True,
        },
        "usage_summary": {
            "total_sessions": 0,
            "last_machine_search_category": None,
            "last_machine_search_city": None,
            "last_listing_type": None,
        },
        "privacy": {
            "source": profile_source,
            "sensitive_fields_excluded": True,
        },
        "_signals": {
            "city_counts": {},
            "category_counts": {},
            "brand_counts": {},
            "language_counts": {},
            "listing_type_counts": {},
        },
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }


def load_user_profile(
    session_id: str,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Load profile from persistence or return empty profile."""
    identity = resolve_profile_identity(session_id, user_id=user_id)
    if not identity.get("profile_id"):
        return empty_user_profile(profile_source="none")

    from app.database.persistent_store import load_user_profile_doc

    doc = load_user_profile_doc(identity["profile_id"])
    if doc:
        doc.setdefault("privacy", {"source": identity["profile_source"], "sensitive_fields_excluded": True})
        doc["last_seen_at"] = _now_iso()
        return doc

    return empty_user_profile(
        profile_id=identity["profile_id"],
        user_id=identity.get("user_id"),
        anonymous_session_key=identity.get("anonymous_session_key"),
        profile_source=identity["profile_source"],
    )


def save_user_profile(profile: dict[str, Any]) -> bool:
    from app.database.persistent_store import persist_user_profile

    pid = profile.get("profile_id")
    if not pid:
        return False
    profile["updated_at"] = _now_iso()
    profile["last_seen_at"] = _now_iso()
    return persist_user_profile(pid, profile)


def reset_user_profile(session_id: str, *, user_id: str | None = None) -> bool:
    """Delete profile for identity — safe reset without sensitive data."""
    identity = resolve_profile_identity(session_id, user_id=user_id)
    pid = identity.get("profile_id")
    if not pid:
        return False
    from app.database.persistent_store import delete_user_profile_doc
    return delete_user_profile_doc(pid)


def set_current_profile(profile: dict[str, Any] | None) -> Any:
    return _PROFILE_CTX.set(profile)


def get_current_profile() -> dict[str, Any] | None:
    return _PROFILE_CTX.get()


def reset_current_profile(token: Any) -> None:
    _PROFILE_CTX.reset(token)


def get_profile_meta() -> dict[str, Any]:
    return _PROFILE_META_CTX.get() or {}


def _set_profile_meta(meta: dict[str, Any]) -> None:
    _PROFILE_META_CTX.set(meta)


def _bump_count(counts: dict[str, int], key: str | None) -> int:
    if not key:
        return 0
    k = str(key).strip().lower()
    if not k:
        return 0
    counts[k] = counts.get(k, 0) + 1
    return counts[k]


def _top_keys(counts: dict[str, int], limit: int = 3) -> list[str]:
    return [
        k for k, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ][:limit]


def _confidence_met(counts: dict[str, int], key: str | None, threshold: int = SIGNAL_THRESHOLD) -> bool:
    if not key:
        return False
    return counts.get(str(key).strip().lower(), 0) >= threshold


def build_profile_hints(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Safe hints for response/context — never auto-apply city/category to search."""
    if not profile:
        return {}
    signals = profile.get("_signals") or {}
    city_counts = signals.get("city_counts") or {}
    hints: dict[str, Any] = {}

    if profile.get("name"):
        hints["name"] = profile["name"]
    if profile.get("preferred_language"):
        hints["preferred_language"] = profile["preferred_language"]
    city = profile.get("preferred_city")
    if city and _confidence_met(city_counts, city):
        hints["preferred_city"] = city
        hints["city_hint_requires_confirmation"] = True
    cats = profile.get("common_machine_categories") or []
    if cats:
        hints["common_machine_categories"] = cats[:MAX_CATEGORIES]
    brands = profile.get("common_brands") or []
    if brands:
        hints["common_brands"] = brands[:MAX_BRANDS]
    if profile.get("common_listing_type"):
        hints["common_listing_type"] = profile["common_listing_type"]
    budget = profile.get("common_budget_range") or {}
    if budget.get("max") is not None:
        hints["common_budget_max"] = budget.get("max")
    style = (profile.get("response_preferences") or {}).get("style")
    if style:
        hints["response_style"] = style
    return hints


def profile_city_confirmation_message(
    *,
    category: str | None,
    preferred_city: str,
    lang: str = "english",
) -> str:
    """Ask user to confirm profile city — never silently search."""
    from app.ai.category_mapping import category_label

    label = category_label(category) if category else "machine"
    city_title = str(preferred_city).title()
    return pick_lang(
        lang,
        english=f"Do you want me to search for {label} in {city_title}, or another city?",
        hindi=f"Kya main {city_title} me {label} search karun, ya koi aur sheher?",
        hinglish=f"Kya {city_title} me {label} search karun, ya koi aur city?",
    )


def profile_aware_clarification_message(
    *,
    lang: str = "english",
    category: str | None = None,
    profile_hints: dict[str, Any] | None = None,
) -> str | None:
    """Optional profile-aware city confirmation when category known but city missing."""
    hints = profile_hints or {}
    city = hints.get("preferred_city")
    if not city or not hints.get("city_hint_requires_confirmation"):
        return None
    return profile_city_confirmation_message(
        category=category,
        preferred_city=city,
        lang=lang,
    )


def _detect_response_style(message: str) -> str | None:
    text = message or ""
    if _STYLE_HINGLISH_RE.search(text):
        return "hinglish"
    if _STYLE_PROFESSIONAL_RE.search(text):
        return "professional"
    if _STYLE_SHORT_RE.search(text):
        return "short"
    if _STYLE_DETAILED_RE.search(text):
        return "detailed"
    return None


def _sanitize_profile_for_storage(profile: dict[str, Any]) -> dict[str, Any]:
    """Ensure no sensitive fields leak into stored profile."""
    clean = dict(profile)
    for bad in (
        "transaction_id", "booking_id", "order_id", "payment_id",
        "raw_messages", "document_text", "support_details", "api_key",
    ):
        clean.pop(bad, None)
    return clean


def update_profile_from_turn(
    profile: dict[str, Any],
    *,
    user_message: str,
    intent: str | None = None,
    entities: dict[str, Any] | None = None,
    parsed: dict[str, Any] | None = None,
    conversation_state: dict[str, Any] | None = None,
    reply_lang: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Update profile from stable low-risk turn signals.
    Returns (updated_profile, meta for debug trace).
    """
    profile = dict(profile or empty_user_profile())
    entities = entities or {}
    parsed = parsed or {}
    state = conversation_state or {}
    intent = (intent or "").lower()
    updated_fields: list[str] = []
    sensitive_skipped = False

    meta = {
        "profile_updated": False,
        "updated_fields": [],
        "sensitive_fields_skipped": True,
        "profile_hints_used": [],
    }

    if intent in SENSITIVE_INTENTS:
        sensitive_skipped = True
        meta["sensitive_fields_skipped"] = True
        meta["skip_reason"] = f"intent:{intent}"
        _set_profile_meta(meta)
        return profile, meta

    if any(k in (user_message or "").lower() for k in ("booking id", "transaction", "order id", "invoice")):
        if intent in SENSITIVE_INTENTS or "support" in intent or "payment" in intent:
            sensitive_skipped = True
            meta["sensitive_fields_skipped"] = True
            _set_profile_meta(meta)
            return profile, meta

    signals = dict(profile.get("_signals") or {})
    city_counts = dict(signals.get("city_counts") or {})
    category_counts = dict(signals.get("category_counts") or {})
    brand_counts = dict(signals.get("brand_counts") or {})
    language_counts = dict(signals.get("language_counts") or {})
    listing_counts = dict(signals.get("listing_type_counts") or {})

    from app.ai.universal_turn_engine import extract_user_name

    name = entities.get("name") or extract_user_name(user_message)
    if name and (
        intent in (
            "user_introduction", "greeting", "acknowledgement", "acknowledgment",
            "greet_user", "conversational", "acknowledge_name",
        )
        or re.search(r"\bmy\s+name\s+is\b", user_message or "", re.I)
    ):
        if profile.get("name") != name:
            profile["name"] = name
            updated_fields.append("name")

    lang = reply_lang or detect_query_language(user_message)
    lang_count = _bump_count(language_counts, lang)
    if lang_count >= SIGNAL_THRESHOLD and profile.get("preferred_language") != lang:
        profile["preferred_language"] = lang
        updated_fields.append("preferred_language")

    style = _detect_response_style(user_message)
    if style:
        prefs = dict(profile.get("response_preferences") or {})
        if prefs.get("style") != style:
            prefs["style"] = style
            profile["response_preferences"] = prefs
            updated_fields.append("response_preferences.style")

    if intent not in SENSITIVE_INTENTS:
        city = (
            entities.get("city")
            or parsed.get("city")
            or (state.get("collected_fields") or {}).get("city")
            or (state.get("last_search_filters") or {}).get("city")
        )
        category = (
            entities.get("category")
            or entities.get("machine_category")
            or parsed.get("category")
            or (state.get("collected_fields") or {}).get("category")
            or (state.get("last_search_filters") or {}).get("category")
        )
        brand = entities.get("brand") or parsed.get("brand")
        listing_type = entities.get("listing_type") or parsed.get("listing_type")
        max_price = (
            entities.get("max_price")
            or entities.get("budget")
            or parsed.get("max_price")
            or (state.get("collected_fields") or {}).get("budget")
        )

        if intent in MACHINE_SEARCH_INTENTS or category or city:
            if city:
                count = _bump_count(city_counts, city)
                usage = dict(profile.get("usage_summary") or {})
                usage["last_machine_search_city"] = str(city).lower()
                profile["usage_summary"] = usage
                if count >= SIGNAL_THRESHOLD and profile.get("preferred_city") != str(city).lower():
                    profile["preferred_city"] = str(city).lower()
                    updated_fields.append("preferred_city")

            if category:
                count = _bump_count(category_counts, category)
                usage = dict(profile.get("usage_summary") or {})
                usage["last_machine_search_category"] = str(category).lower()
                profile["usage_summary"] = usage
                top_cats = _top_keys(category_counts, MAX_CATEGORIES)
                if count >= 1 and top_cats != profile.get("common_machine_categories"):
                    profile["common_machine_categories"] = top_cats
                    if count >= SIGNAL_THRESHOLD:
                        updated_fields.append("common_machine_categories")

            if brand:
                count = _bump_count(brand_counts, brand)
                top_brands = _top_keys(brand_counts, MAX_BRANDS)
                if top_brands != profile.get("common_brands"):
                    profile["common_brands"] = top_brands
                    if count >= SIGNAL_THRESHOLD:
                        updated_fields.append("common_brands")

            if listing_type:
                count = _bump_count(listing_counts, listing_type)
                usage = dict(profile.get("usage_summary") or {})
                usage["last_listing_type"] = listing_type
                profile["usage_summary"] = usage
                if count >= SIGNAL_THRESHOLD and profile.get("common_listing_type") != listing_type:
                    profile["common_listing_type"] = listing_type
                    updated_fields.append("common_listing_type")

            if max_price is not None and intent in MACHINE_SEARCH_INTENTS:
                try:
                    price_val = float(max_price)
                    if price_val > 0:
                        br = dict(profile.get("common_budget_range") or {})
                        cur_max = br.get("max")
                        if cur_max is None or price_val > float(cur_max):
                            br["max"] = int(price_val)
                        br["currency"] = "INR"
                        profile["common_budget_range"] = br
                        if "common_budget_range" not in updated_fields:
                            updated_fields.append("common_budget_range")
                except (TypeError, ValueError):
                    pass

    profile["_signals"] = {
        "city_counts": city_counts,
        "category_counts": category_counts,
        "brand_counts": brand_counts,
        "language_counts": language_counts,
        "listing_type_counts": listing_counts,
    }
    profile["usage_summary"]["total_sessions"] = int(
        (profile.get("usage_summary") or {}).get("total_sessions") or 0
    ) + 0  # session bump handled on load

    if updated_fields:
        profile = _sanitize_profile_for_storage(profile)
        meta["profile_updated"] = True
        meta["updated_fields"] = updated_fields

    meta["sensitive_fields_skipped"] = sensitive_skipped or True
    _set_profile_meta(meta)
    return profile, meta


def begin_profile_turn(
    session_id: str,
    *,
    user_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load profile, bump session count, return profile + hints."""
    profile = load_user_profile(session_id, user_id=user_id)
    usage = dict(profile.get("usage_summary") or {})
    usage["total_sessions"] = int(usage.get("total_sessions") or 0) + 1
    profile["usage_summary"] = usage
    hints = build_profile_hints(profile)
    token = set_current_profile(profile)
    meta = {
        "loaded": True,
        "profile_source": (profile.get("privacy") or {}).get("source", "none"),
        "profile_hints_used": list(hints.keys()),
        "profile_updated": False,
        "updated_fields": [],
        "sensitive_fields_skipped": True,
        "_token": token,
    }
    _set_profile_meta(meta)
    return profile, hints, token


def end_profile_turn(
    profile: dict[str, Any],
    *,
    user_message: str,
    response: dict[str, Any],
    conversation_state: dict[str, Any] | None = None,
    intent: str | None = None,
    reply_lang: str | None = None,
    profile_token: Any = None,
) -> dict[str, Any]:
    """Apply turn updates and persist profile."""
    from app.ai.query_parser import parse_query

    data = response.get("data") or {}
    ctx = data.get("context") or {}
    entities = dict(ctx.get("entities") or {})
    from app.ai.assistant_brain import sanitize_display_name

    if ctx.get("user_name"):
        ctx["user_name"] = sanitize_display_name(ctx["user_name"])
    if entities.get("name"):
        entities["name"] = sanitize_display_name(entities["name"])
    if ctx.get("user_name") and not entities.get("name"):
        entities["name"] = ctx["user_name"]
    intent = intent or ctx.get("intent")

    updated, turn_meta = update_profile_from_turn(
        profile,
        user_message=user_message,
        intent=intent,
        entities=entities,
        parsed=parse_query(user_message),
        conversation_state=conversation_state,
        reply_lang=reply_lang,
    )

    begin_meta = get_profile_meta()
    if turn_meta.get("profile_updated"):
        save_user_profile(updated)
    else:
        save_user_profile(updated)  # persist last_seen_at bump

    final_meta = {
        "loaded": begin_meta.get("loaded", True),
        "profile_source": begin_meta.get("profile_source") or (updated.get("privacy") or {}).get("source"),
        "profile_hints_used": begin_meta.get("profile_hints_used") or [],
        "profile_updated": turn_meta.get("profile_updated", False),
        "updated_fields": turn_meta.get("updated_fields") or [],
        "sensitive_fields_skipped": turn_meta.get("sensitive_fields_skipped", True),
    }
    _set_profile_meta(final_meta)

    if profile_token is not None:
        reset_current_profile(profile_token)

    try:
        from app.ai.assistant_debug_trace import record_user_profile
        record_user_profile(final_meta)
    except Exception:
        pass

    return final_meta


def apply_profile_hints_to_session_context(
    session_ctx: dict[str, Any],
    hints: dict[str, Any] | None,
) -> dict[str, Any]:
    """Inject safe profile hints into session context without overriding explicit data."""
    if not hints:
        return session_ctx
    ctx = dict(session_ctx or {})
    if hints.get("name") and not ctx.get("user_name"):
        ctx["user_name"] = hints["name"]
    ctx["user_profile_hints"] = hints
    return ctx
