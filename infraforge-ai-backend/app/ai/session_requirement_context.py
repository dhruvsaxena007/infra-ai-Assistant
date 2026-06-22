"""
Session memory authority — single place to read/write requirement context across turns.

Prevents re-asking known fields and stale category bleed (e.g. transport → dump truck
when user later says digging).
"""

from __future__ import annotations

from typing import Any, Optional


def collected_from_state(conv_state: dict | None) -> dict[str, Any]:
    if not conv_state:
        return {}
    return dict(conv_state.get("collected_fields") or {})


def enrich_parsed_from_session(
    message: str,
    parsed: dict,
    *,
    last_filters: dict | None = None,
    session_collected: dict | None = None,
    allow_session_enrich: bool = True,
) -> dict:
    """
    Merge purpose, category, city, budget from message + session memory.
    Current message purpose/category revises stale filters.
    """
    from app.ai.purpose_taxonomy import category_compatible_with_purpose, primary_category_for_purpose
    from app.chatbot.assistant_intelligence import (
        detect_requested_category,
        resolve_purpose_key,
    )

    parsed = dict(parsed or {})
    if not allow_session_enrich:
        return parsed
    last = dict(last_filters or {})
    collected = dict(session_collected or {})

    purpose = resolve_purpose_key(message) or collected.get("purpose")
    explicit_cat = parsed.get("category") or detect_requested_category(message)

    if purpose:
        derived = primary_category_for_purpose(purpose)
        parsed["purpose_key"] = purpose
        if derived:
            prior_cat = explicit_cat or last.get("category") or collected.get("category")
            if not prior_cat:
                parsed["category"] = derived
            elif explicit_cat and category_compatible_with_purpose(explicit_cat, purpose):
                parsed["category"] = explicit_cat
            elif explicit_cat and not category_compatible_with_purpose(explicit_cat, purpose):
                # Explicit machine name conflicts with new purpose — purpose wins for work-type revision
                parsed["category"] = derived
            elif not category_compatible_with_purpose(prior_cat, purpose):
                parsed["category"] = derived
            elif not explicit_cat:
                parsed["category"] = derived
    elif explicit_cat:
        parsed["category"] = explicit_cat

    if not parsed.get("city"):
        parsed["city"] = collected.get("city") or last.get("city")
    if parsed.get("max_price") is None:
        budget = collected.get("budget")
        if budget is not None:
            parsed["max_price"] = budget
        elif last.get("max_price") is not None:
            parsed["max_price"] = last.get("max_price")
    if not parsed.get("listing_type"):
        parsed["listing_type"] = collected.get("listing_type") or last.get("listing_type")
    if not parsed.get("category") and collected.get("category") and not purpose:
        parsed["category"] = collected.get("category")
    if not purpose and collected.get("purpose"):
        parsed["purpose_key"] = collected.get("purpose")

    return parsed


def sync_turn_context_to_collected(
    conv_state: dict | None,
    *,
    last_user_goal: str | None = None,
    recommendation_context: dict | None = None,
    comparison_context: dict | None = None,
    search_filters: dict | None = None,
    pending_clarification: dict | None = None,
) -> None:
    """Single write path for turn context — prevents dual-store desync."""
    if not conv_state:
        return
    if last_user_goal:
        conv_state["last_user_goal"] = last_user_goal
    if recommendation_context is not None:
        conv_state["last_recommendation_context"] = dict(recommendation_context)
    if comparison_context is not None:
        conv_state["last_comparison_context"] = dict(comparison_context)
        brands = comparison_context.get("brands") or []
        if brands:
            collected = dict(conv_state.get("collected_fields") or {})
            collected["brands"] = brands
            conv_state["collected_fields"] = collected
    if search_filters is not None:
        conv_state["last_search_filters"] = {k: v for k, v in search_filters.items() if v is not None}
    if pending_clarification is not None:
        conv_state["pending_clarification"] = pending_clarification


def requirements_complete_in_state(conv_state: dict | None) -> bool:
    collected = collected_from_state(conv_state)
    has_loc = bool(collected.get("city"))
    has_machine = bool(
        collected.get("category")
        or collected.get("purpose")
        or (conv_state or {}).get("_derived_category", {}).get("category")
    )
    return has_loc and has_machine


def should_skip_broad_clarification(
    message: str,
    conv_state: dict | None,
    parsed: dict | None = None,
) -> bool:
    """
    Do not reset to broad machine template when session already has partial/full requirements
    or the current message adds concrete fields.
    """
    from app.chatbot.assistant_intelligence import (
        detect_requested_category,
        resolve_purpose_key,
    )
    from app.ai.query_parser import parse_query

    parsed = parsed or parse_query(message or "")
    collected = collected_from_state(conv_state)

    if requirements_complete_in_state(conv_state):
        return True

    if resolve_purpose_key(message) or detect_requested_category(message):
        return True
    if parsed.get("city") or parsed.get("category") or parsed.get("max_price") is not None:
        return True

    if collected.get("city") and (collected.get("category") or collected.get("purpose")):
        return True
    if collected.get("city") or collected.get("category") or collected.get("purpose"):
        # Partial session — only clarify if message is truly empty
        text = (message or "").strip().lower()
        if len(text.split()) <= 4 and not resolve_purpose_key(message):
            return True
    return False


def filters_from_collected(conv_state: dict | None) -> dict[str, Any]:
    """Build search filters from canonical collected state."""
    collected = collected_from_state(conv_state)
    if not collected:
        return {}
    from app.ai.requirement_state_engine import requirement_state_from_conversation, build_search_filters

    req = requirement_state_from_conversation(conv_state or {})
    return build_search_filters(req)
