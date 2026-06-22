"""
Central decision engine for the InfraForge marketplace assistant.

resolve_user_intent() is the single place that decides:
  - whether to reuse previous session memory
  - whether the current message starts a fresh search
  - how image context, pending clarification, and greetings interact

Priority (highest wins):
  1. Explicit category / brand / model in the CURRENT message
  2. Image-detected category when user references "this machine"
  3. Active pending clarification answer
  4. True follow-up phrases (same, what about, cheaper, under X, show all)
  5. Previous memory — only for genuine follow-ups, never for city-only pivots
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import (
    canonicalize_category,
    detect_brand,
    detect_cheaper,
    detect_free_request,
    detect_list_all,
    detect_max_price,
    detect_model,
    detect_negated_category,
    detect_override,
    detect_region,
    detect_requested_category,
)
from app.ai.query_parser import parse_query
from app.ai.spell_correction import (
    apply_confirmed_spelling,
    is_spell_confirmation_no,
    is_spell_confirmation_yes,
    resolve_spelling_async,
    should_apply_spelling,
)
from app.chatbot.assistant_intelligence import (
    apply_pending_answer,
    classify_non_service_message,
    detect_project_type,
    is_booking_guidance_query,
    is_clarification_answer,
    is_greeting,
    is_negative_pivot,
    is_recommendation_query,
    needs_clarification,
    parse_project_type_option,
    project_categories,
    project_type_pending_state,
)
from app.chatbot.image_context_memory import (
    get_image_context,
    resolve_message_with_image_context,
)
from app.chatbot.memory import get_conversation_history_as_text

# ---------------------------------------------------------------------------
# Follow-up detection — conservative: default is NEW search, not memory reuse.
# ---------------------------------------------------------------------------

FOLLOW_UP_PHRASES = (
    "cheaper", "lower", "same", "instead", "what about", "also", "more",
    "less", "budget", "options", "that", "those", "it", "them", "show",
    "better", "rated", "another", "rather", "switch", "change", "under",
    "upto", "up to", "kam", "sasta",
)

_SAME_PHRASES = ("same", "what about", "also in", "bhi", "wahi")

_DEFAULT_FILTERS = {
    "category": None,
    "city": None,
    "region": None,
    "max_price": None,
    "brand": None,
    "model": None,
    "condition": None,
    "pincode": None,
    "listing_type": None,
    "rent_type": None,
}


def _has_explicit_search_terms(parsed: dict) -> bool:
    return bool(
        parsed.get("category")
        or parsed.get("brand")
        or parsed.get("model")
    )


def _has_follow_up_phrase(message: str) -> bool:
    lower = (message or "").lower()
    return any(phrase in lower for phrase in FOLLOW_UP_PHRASES)


def _has_same_phrase(message: str) -> bool:
    lower = (message or "").lower()
    return any(phrase in lower for phrase in _SAME_PHRASES)


def _is_true_follow_up(
    message: str,
    parsed: dict,
    *,
    has_history: bool,
    pending: Optional[dict],
    last_filters: Optional[dict] = None,
) -> bool:
    """Return True only when previous context should be merged."""
    if pending:
        return True

    if not has_history:
        return False

    last = last_filters or {}

    if _has_explicit_search_terms(parsed):
        # Category switch while city is already known: "delhi" → "need a crane".
        # Fresh "jcb chahiye" with no prior city is handled by needs_clarification.
        if (
            parsed.get("category")
            and not parsed.get("city")
            and last.get("city")
        ):
            return True
        # New explicit machine terms override memory unless user says "same/what about".
        return _has_same_phrase(message) or (
            _has_follow_up_phrase(message) and not parsed.get("category")
        )

    # City-only: inherit only when the PREVIOUS query was incomplete (had category
    # but no city yet), e.g. "excavator under 10000" → "in jaipur".
    # A bare new city after a complete search (e.g. "delhi" after crane in jaipur)
    # must NOT silently reuse the old category.
    if parsed.get("city") and not parsed.get("category"):
        if _has_same_phrase(message):
            return True
        if last.get("category") and not last.get("city"):
            return True
        return False

    # Budget-only refinement ("under 5000", "cheaper options").
    if parsed.get("max_price") is not None and not parsed.get("city"):
        if last.get("category") or last.get("city"):
            return True
        return _has_follow_up_phrase(message) or len((message or "").split()) <= 4

    # Rent/buy preference only — keep machine + city from prior turn.
    if parsed.get("listing_type") and not parsed.get("category") and not parsed.get("city"):
        if last.get("category") or last.get("city"):
            return True

    # "list all machines" / "show all" after a prior search keeps category + city.
    if detect_list_all(message):
        return True

    return _has_follow_up_phrase(message)


def _start_fresh_filters(parsed: dict) -> dict:
    """Build filters from the current message only — no memory."""
    return {**_DEFAULT_FILTERS, **{k: v for k, v in parsed.items() if v is not None}}


def _merge_filters(
    old: dict,
    new: dict,
    *,
    is_follow_up: bool,
    override: bool,
    negated_category,
) -> dict:
    if not is_follow_up:
        merged = _start_fresh_filters(new)
    else:
        merged = {
            "category": new.get("category") or old.get("category"),
            "city": new.get("city") or old.get("city"),
            "region": new.get("region") or old.get("region"),
            "max_price": (
                new.get("max_price")
                if new.get("max_price") is not None
                else old.get("max_price")
            ),
            "brand": new.get("brand") or old.get("brand"),
            "model": new.get("model") or old.get("model"),
            "condition": new.get("condition") or old.get("condition"),
            "pincode": new.get("pincode") or old.get("pincode"),
            "listing_type": new.get("listing_type") or old.get("listing_type"),
            "rent_type": new.get("rent_type") or old.get("rent_type"),
        }

    # Explicit new values always win.
    for key in (
        "category", "city", "region", "brand", "model",
        "condition", "pincode", "listing_type", "rent_type",
    ):
        if new.get(key):
            merged[key] = new.get(key)

    if new.get("max_price") is not None:
        merged["max_price"] = new.get("max_price")

    if new.get("category"):
        merged["category"] = new.get("category")
    elif override or negated_category:
        if negated_category and negated_category == old.get("category"):
            merged["category"] = None
        elif override and not new.get("category"):
            merged["category"] = None

    # Region and city are mutually exclusive for search.
    if merged.get("region"):
        merged["city"] = None
    elif merged.get("city"):
        merged["region"] = None

    return merged


def _apply_cheaper_adjustment(filters: dict, message: str) -> dict:
    if not detect_cheaper(message):
        return filters
    explicit_price = any(char.isdigit() for char in message)
    if not explicit_price and filters.get("max_price"):
        filters = dict(filters)
        filters["max_price"] = int(filters["max_price"] * 0.75)
    return filters


def _confidence_level(parsed: dict, merged: dict, *, uses_previous: bool) -> str:
    if _has_explicit_search_terms(parsed) and (merged.get("city") or merged.get("region")):
        return "high"
    if _has_explicit_search_terms(parsed) or merged.get("city") or merged.get("region"):
        return "medium"
    if uses_previous:
        return "medium"
    return "low"


def _base_intent() -> dict[str, Any]:
    return {
        "intent": "search",
        "assistant_mode": "search",
        "category": None,
        "city": None,
        "region": None,
        "brand": None,
        "model": None,
        "max_price": None,
        "listing_type": None,
        "rent_type": None,
        "condition": None,
        "pincode": None,
        "is_follow_up": False,
        "uses_previous_context": False,
        "pending_clarification": None,
        "confidence": "low",
        "filters": dict(_DEFAULT_FILTERS),
        "project_type": None,
        "recommended_categories": [],
        "list_all": False,
        "free_request": False,
        "override": False,
        "greeting_first_time": False,
        "used_image_context": False,
        "clear_recommendation_context": False,
        "clear_pending_clarification": False,
        "save_pending_clarification": None,
        "save_recommendation_context": None,
        "save_filters": None,
        "mark_greeted": False,
    }


async def resolve_user_intent(
    session_id: str,
    message: str,
    *,
    last_filters: dict,
    pending: Optional[dict],
    recommendation_context: Optional[dict],
    greeted: bool = False,
    optional_image_context: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Resolve what the assistant should do for this user turn.

    Returns a dict with intent metadata plus merged ``filters`` ready for search.
    """
    result = _base_intent()
    message = (message or "").strip()
    history_text = get_conversation_history_as_text(session_id)
    has_history = bool(history_text)

    # --- Image context injection (explicit machine terms override image) ------
    resolved_message, used_image = resolve_message_with_image_context(
        session_id, message,
    )
    result["used_image_context"] = used_image

    # --- Greeting -------------------------------------------------------------
    if is_greeting(message):
        result["intent"] = "greeting"
        result["assistant_mode"] = "greeting"
        result["greeting_first_time"] = not greeted
        result["mark_greeted"] = True
        result["clear_pending_clarification"] = True
        result["clear_recommendation_context"] = True
        return result

    # --- Legacy spell-confirm pending: never trap the user in a loop ----------
    spell_context: Optional[dict] = None
    skip_spell = message.isdigit()

    if pending and pending.get("missing_field") == "spell_confirm":
        old_spell_pending = pending
        result["clear_pending_clarification"] = True
        pending = None
        if is_spell_confirmation_yes(message):
            resolved_message, spell_context = apply_confirmed_spelling(old_spell_pending)
            skip_spell = True
        elif is_spell_confirmation_no(message):
            # User rejected — use their message as-is, never re-suggest.
            skip_spell = True
        # Any other reply is treated as a fresh query.

    # --- Spelling tolerance: silent auto-fix only; never block conversation ---
    if not skip_spell and should_apply_spelling(resolved_message):
        spell = await resolve_spelling_async(resolved_message)
        if spell.action == "auto" and spell.corrections:
            resolved_message = spell.corrected_query
            spell_context = spell.to_context()

    result["spell_context"] = spell_context

    # --- Parse current message ------------------------------------------------
    parsed = parse_query(resolved_message)
    if optional_image_context and used_image:
        img_cat = canonicalize_category(
            optional_image_context.get("detected_machine_type")
        )
        if img_cat and not _has_explicit_search_terms(parsed):
            parsed["category"] = img_cat

    free_request = detect_free_request(message)
    list_all = detect_list_all(message)
    override = detect_override(message)
    negated = detect_negated_category(message)
    result["free_request"] = free_request
    result["list_all"] = list_all
    result["override"] = override

    # --- Rent / book / contact-owner guidance (no new search) -----------------
    if is_booking_guidance_query(message):
        result["intent"] = "booking_guidance"
        result["assistant_mode"] = "booking_guidance"
        result["uses_previous_context"] = bool(
            has_history
            and (
                last_filters.get("category")
                or last_filters.get("city")
                or last_filters.get("brand")
            )
        )
        result["confidence"] = "high"
        ctx_filters = dict(_DEFAULT_FILTERS)
        for key in ("category", "city", "brand", "listing_type"):
            if last_filters.get(key):
                ctx_filters[key] = last_filters.get(key)
        result["filters"] = ctx_filters
        _fill_result_from_filters(result, ctx_filters)
        return result

    # --- User rejected a clarification option ("no" / "nahi") -----------------
    if pending and is_negative_pivot(message):
        result["intent"] = "clarification"
        result["assistant_mode"] = "clarification"
        result["negative_pivot"] = True
        result["pending_clarification"] = pending
        result["save_pending_clarification"] = pending
        result["confidence"] = "low"
        return result

    # --- Irrelevant / abusive / off-topic (no search, no stale context) -------
    irrelevant_kind = classify_non_service_message(
        message, parsed, pending=pending,
    )
    if irrelevant_kind:
        result["intent"] = "off_topic"
        result["assistant_mode"] = irrelevant_kind
        result["confidence"] = "high"
        return result

    # --- Project recommendation -----------------------------------------------
    awaiting_project = bool(
        recommendation_context and recommendation_context.get("awaiting_project_type")
    )
    is_rec_query = is_recommendation_query(message)

    if is_rec_query or awaiting_project:
        project_key = parse_project_type_option(message)
        if not project_key and not is_rec_query:
            project_key = (recommendation_context or {}).get("project_type")
        if not project_key and is_rec_query and not awaiting_project:
            project_key = detect_project_type(message)
        if not project_key:
            result["intent"] = "project_recommendation"
            result["assistant_mode"] = "recommendation_clarification"
            result["save_recommendation_context"] = {"awaiting_project_type": True}
            result["save_pending_clarification"] = project_type_pending_state()
            result["pending_clarification"] = result["save_pending_clarification"]
            return result

        cats = project_categories(project_key)
        result["intent"] = "project_recommendation"
        result["assistant_mode"] = "project_recommendation"
        result["project_type"] = project_key
        result["recommended_categories"] = [
            {"category": c, "reason": f"Recommended for {project_key} projects"}
            for c in cats
        ]
        result["category"] = cats[0] if cats else None
        result["filters"] = _start_fresh_filters(parsed)
        if cats:
            result["filters"]["category"] = cats[0]
        result["list_all"] = True
        result["clear_recommendation_context"] = True
        result["clear_pending_clarification"] = True
        result["uses_previous_context"] = False
        result["confidence"] = "high"
        if cats:
            result["save_filters"] = {
                "category": cats[0],
                "city": None,
                "max_price": None,
            }
        return result

    # Drop stale pending when user pivots to a new search.
    if pending and not is_clarification_answer(message, pending, parsed=parsed):
        if (
            _has_explicit_search_terms(parsed)
            or parsed.get("city")
            or parsed.get("max_price") is not None
            or override
        ):
            pending = None
            result["clear_pending_clarification"] = True

    # --- Pending clarification answer -----------------------------------------
    if pending and is_clarification_answer(message, pending, parsed=parsed):
        merged = apply_pending_answer(pending, message, parsed)
        result["is_follow_up"] = True
        result["uses_previous_context"] = True
        result["clear_pending_clarification"] = True
        merged = _apply_cheaper_adjustment(merged, message)
        result["filters"] = merged
        _fill_result_from_filters(result, merged)
        result["confidence"] = _confidence_level(parsed, merged, uses_previous=True)
        result["save_filters"] = {
            k: merged.get(k)
            for k in (
                "category", "city", "region", "max_price", "brand", "model",
                "condition", "pincode", "listing_type", "rent_type",
            )
            if merged.get(k) is not None
        }
        return result

    # --- Standard search intent merge -----------------------------------------
    is_fup = _is_true_follow_up(
        message, parsed, has_history=has_history, pending=pending,
        last_filters=last_filters,
    )
    merged = _merge_filters(
        last_filters,
        parsed,
        is_follow_up=is_fup,
        override=override,
        negated_category=negated,
    )
    merged = _apply_cheaper_adjustment(merged, message)

    result["is_follow_up"] = is_fup
    result["uses_previous_context"] = is_fup and bool(
        last_filters.get("category")
        or last_filters.get("city")
        or last_filters.get("max_price")
    )
    result["filters"] = merged
    _fill_result_from_filters(result, merged)

    # --- Clarification needed before search? ----------------------------------
    clarify = needs_clarification(
        merged, list_all=list_all, message=message, pending=pending,
        last_filters=last_filters,
    )
    if clarify and not list_all and not free_request:
        result["intent"] = "clarification"
        result["assistant_mode"] = "clarification"
        result["pending_clarification"] = clarify
        result["save_pending_clarification"] = clarify
        result["confidence"] = "low"
        saved = {k: v for k, v in {
            "category": clarify.get("category") or merged.get("category"),
            "city": clarify.get("city") or merged.get("city"),
            "max_price": merged.get("max_price"),
            "listing_type": merged.get("listing_type"),
        }.items() if v is not None}
        if saved:
            result["save_filters"] = {**_DEFAULT_FILTERS, **saved}
        return result

    result["confidence"] = _confidence_level(
        parsed, merged, uses_previous=result["uses_previous_context"],
    )
    result["save_filters"] = {
        k: merged.get(k)
        for k in (
            "category", "city", "region", "max_price", "brand", "model",
            "condition", "pincode", "listing_type", "rent_type",
        )
        if merged.get(k) is not None
    }
    return result


def _fill_result_from_filters(result: dict, merged: dict) -> None:
    for key in (
        "category", "city", "region", "brand", "model", "max_price",
        "listing_type", "rent_type", "condition", "pincode",
    ):
        result[key] = merged.get(key)
