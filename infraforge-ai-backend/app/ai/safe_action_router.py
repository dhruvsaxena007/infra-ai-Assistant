"""
Safe Action Router — maps classified intent + entities to an allowed backend action.

Uses Tool Permission Matrix before any tool invocation.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.intent_signals import (
    is_acknowledgement_signal,
    is_brand_availability_signal,
    is_brand_inventory_signal,
    is_brand_only_inventory_signal,
    is_machine_brand_query_signal,
)
from app.ai.tool_permission_matrix import (
    TOOL_CLARIFICATION,
    TOOL_COMPARISON,
    TOOL_CONVERSATIONAL,
    TOOL_IMAGE_CONTEXT,
    TOOL_MONGODB_BRAND_INVENTORY,
    TOOL_MONGODB_SEARCH,
    TOOL_NONE,
    TOOL_RAG,
    TOOL_RECOMMENDATION,
    TOOL_SUPPORT,
    get_intent_permissions,
    is_tool_allowed,
)

_BRAND_AVAIL_RE = re.compile(
    r"\b(?:available|have|got|stock|carry|sell|rent)\b",
    re.IGNORECASE,
)


def _entity_category(entities: dict[str, Any]) -> str | None:
    return (
        entities.get("machine_type")
        or entities.get("category")
        or entities.get("machine_category")
    )


def _entity_brand(entities: dict[str, Any]) -> str | None:
    brands = entities.get("brands")
    if isinstance(brands, list) and brands:
        return str(brands[0])
    return entities.get("brand")


def _has_previous_filters(ctx: dict[str, Any]) -> bool:
    last = ctx.get("last_filters") or ctx.get("last_search_filters") or {}
    if last.get("category") or last.get("city") or last.get("brand"):
        return True
    collected = ctx.get("collected_fields") or {}
    state = ctx.get("conversation_state") or {}
    collected = collected or state.get("collected_fields") or {}
    return bool(collected.get("category") or collected.get("city") or collected.get("brand"))


def _has_machine_context(ctx: dict[str, Any]) -> bool:
    last = ctx.get("last_results") or ctx.get("last_machines") or []
    if last:
        return True
    last_filters = ctx.get("last_filters") or {}
    return bool(last_filters.get("category") or last_filters.get("brand"))


def _has_pending_flow(ctx: dict[str, Any]) -> bool:
    pending = ctx.get("pending")
    if not pending:
        return False
    return bool(pending.get("type") or pending.get("missing_field") or pending.get("missing"))


def _compute_missing_fields(intent: str, entities: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    perms = get_intent_permissions(intent)
    required = perms.get("required_entities") or []
    missing: list[str] = []
    cat = _entity_category(entities)
    city = entities.get("city")
    brand = _entity_brand(entities)
    purpose = entities.get("purpose")

    for req in required:
        if req == "category_or_purpose":
            if not cat and not purpose and not (ctx.get("last_filters") or {}).get("category"):
                missing.append("category_or_purpose")
        elif req == "purpose_or_category":
            if not cat and not purpose:
                missing.append("purpose_or_category")
            if not city and not (ctx.get("last_filters") or {}).get("city"):
                missing.append("city")
        elif req == "city":
            if not city and not (ctx.get("last_filters") or {}).get("city"):
                missing.append("city")
        elif req == "category_or_brand_or_context":
            has_ctx = bool(cat or brand or _has_previous_filters(ctx))
            if not has_ctx:
                missing.append("category_or_brand")
        elif req == "previous_filters_or_entities":
            if not _has_previous_filters(ctx) and not (cat or city):
                missing.append("previous_context")
        elif req == "comparison_items":
            brands = entities.get("brands") or []
            if len(brands) < 2 and not cat:
                missing.append("comparison_items")
        elif req == "document_context":
            if not entities.get("document_reference") and not ctx.get("has_document_context"):
                missing.append("document_context")
        elif req == "image_or_category_context":
            if not ctx.get("has_image_context") and not cat:
                missing.append("image_or_category")
        elif req == "machine_context":
            if not _has_machine_context(ctx):
                missing.append("machine_context")
    return missing


def _resolve_brand_query_action(
    entities: dict[str, Any],
    ctx: dict[str, Any],
    message: str,
) -> tuple[str, str, str]:
    """Return (selected_action, allowed_tool, reason)."""
    cat = _entity_category(entities) or (ctx.get("last_filters") or {}).get("category")
    brand = _entity_brand(entities)
    city = entities.get("city") or (ctx.get("last_filters") or {}).get("city")
    inv = ctx.get("last_brand_inventory") or {}
    if not cat:
        cat = inv.get("category")
    if not city:
        city = inv.get("city")
    msg = message or ""

    if cat and brand:
        if is_brand_availability_signal(msg) or _BRAND_AVAIL_RE.search(msg):
            return (
                "check_brand_availability",
                TOOL_MONGODB_SEARCH,
                "brand and category known; checking listing availability",
            )
        return (
            "check_brand_availability",
            TOOL_MONGODB_SEARCH,
            "brand and category known; search listings for brand in category",
        )

    if cat and (is_brand_inventory_signal(msg) or not brand):
        loc = f" in {city}" if city else ""
        return (
            "query_brands_by_category",
            TOOL_MONGODB_BRAND_INVENTORY,
            f"category known{loc}; list available brands",
        )

    if brand and not cat:
        from app.ai.catalog_entity_resolver import is_brand_marketplace_search
        from app.ai.query_parser import parse_query

        if is_brand_marketplace_search(msg, parse_query(msg)) or city:
            return (
                "machine_search",
                TOOL_MONGODB_SEARCH,
                "brand with city or search signals; filter listings by brand",
            )
        return (
            "list_categories_for_brand",
            TOOL_MONGODB_BRAND_INVENTORY,
            "brand known without category; list categories or ask category",
        )

    return (
        "ask_brand_category",
        TOOL_CLARIFICATION,
        "category and brand missing; ask machine category",
    )


def _effective_intent(
    intent: str,
    message: str,
    entities: dict[str, Any],
    ctx: dict[str, Any],
) -> str:
    """Action-layer intent refinement — does not rewrite classifier output."""
    from app.ai.catalog_entity_resolver import is_brand_marketplace_search
    from app.ai.intent_signals import is_brand_filter_refinement_signal
    from app.ai.query_parser import parse_query

    if is_acknowledgement_signal(message, ctx):
        return "acknowledgement"
    parsed = parse_query(message)
    if is_brand_filter_refinement_signal(message, ctx, parsed):
        return "machine_search"
    if is_brand_marketplace_search(message, parsed):
        return "machine_search"
    if is_machine_brand_query_signal(message) or is_brand_inventory_signal(message):
        return "machine_brand_query"
    if is_brand_only_inventory_signal(message, entities):
        return "machine_brand_query"
    return intent


def resolve_action_decision(
    classification: dict[str, Any],
    ctx: dict[str, Any] | None = None,
    *,
    message: str = "",
) -> dict[str, Any]:
    """
    Build normalized action decision from classification + session context.
    """
    ctx = ctx or {}
    raw_intent = str(classification.get("intent") or "unknown").lower()
    intent = _effective_intent(raw_intent, message or classification.get("message") or "", entities := dict(classification.get("entities") or {}), ctx)
    perms = get_intent_permissions(intent)
    missing_fields = _compute_missing_fields(intent, entities, ctx)

    selected_action = perms.get("fallback_action_if_missing") or "clarify_unknown"
    allowed_tool = TOOL_CLARIFICATION
    reason = "default fallback"
    should_search = False
    should_rag = False
    should_support = False

    if intent == "machine_brand_query":
        selected_action, allowed_tool, reason = _resolve_brand_query_action(
            entities, ctx, message or classification.get("message") or "",
        )
        should_search = allowed_tool in (TOOL_MONGODB_SEARCH, TOOL_MONGODB_BRAND_INVENTORY)
    elif intent in ("machine_search", "rent_machine", "buy_machine", "machine_availability", "price_query"):
        if missing_fields:
            selected_action = perms.get("fallback_action_if_missing") or "ask_missing_machine_fields"
            allowed_tool = TOOL_CLARIFICATION
            reason = f"missing required fields: {missing_fields}"
        else:
            cat = _entity_category(entities)
            city = entities.get("city")
            from app.ai.search_refinement_engine import detect_refinement_type
            from app.ai.query_parser import parse_query

            is_refinement = bool(detect_refinement_type(message or "", parse_query(message or "")))
            if city and not cat and not entities.get("purpose") and not is_refinement:
                selected_action = "ask_missing_machine_fields"
                allowed_tool = TOOL_CLARIFICATION
                reason = "city known without category; collect machine type first"
            else:
                selected_action = "machine_search"
                allowed_tool = TOOL_MONGODB_SEARCH
                should_search = True
                reason = "category or purpose present; machine search allowed"
    elif intent in ("cheaper_option_query", "higher_budget_query"):
        if missing_fields:
            selected_action = "ask_followup_context"
            allowed_tool = TOOL_CLARIFICATION
            reason = "follow-up without previous search context"
        else:
            selected_action = "refine_search_filters"
            allowed_tool = TOOL_MONGODB_SEARCH
            should_search = True
            reason = "previous filters available for budget follow-up"
    elif intent == "machine_comparison":
        if missing_fields:
            selected_action = "ask_comparison_context"
            allowed_tool = TOOL_CLARIFICATION
            reason = "comparison items incomplete"
        else:
            selected_action = "comparison_advisory"
            allowed_tool = TOOL_COMPARISON
            reason = "comparison context sufficient"
    elif intent == "machine_recommendation":
        if missing_fields:
            selected_action = "ask_recommendation_fields"
            allowed_tool = TOOL_CLARIFICATION
            reason = "recommendation needs purpose and city"
        elif entities.get("purpose") or entities.get("machine_type"):
            selected_action = "recommendation_advisory"
            allowed_tool = TOOL_RECOMMENDATION
            reason = "purpose known; advisory recommendation"
        else:
            selected_action = "ask_recommendation_fields"
            allowed_tool = TOOL_CLARIFICATION
    elif intent == "broad_machine_request":
        selected_action = "ask_missing_machine_fields"
        allowed_tool = TOOL_CLARIFICATION
        reason = "broad request requires clarification before search"
    elif intent == "document_question":
        if missing_fields:
            selected_action = "ask_document_upload"
            allowed_tool = TOOL_CLARIFICATION
            reason = "no document context"
        else:
            selected_action = "document_rag"
            allowed_tool = TOOL_RAG
            should_rag = True
            reason = "document context available"
    elif intent in (
        "payment_issue", "refund_return", "order_issue", "delivery_issue",
        "delivery_logistics", "invoice_issue", "security_deposit",
        "complaint", "support_request", "human_handover", "contact_owner",
        "platform_how_to", "general_marketplace_help", "general_help", "booking_help",
    ):
        selected_action = "support_flow"
        allowed_tool = TOOL_SUPPORT
        should_support = True
        reason = "support intent; no machine search"
    elif intent in ("greeting", "user_introduction", "gratitude", "polite_conversation"):
        selected_action = "conversational_response"
        allowed_tool = TOOL_CONVERSATIONAL
        reason = "conversational intent; no backend tool"
    elif intent == "acknowledgement":
        if _has_pending_flow(ctx):
            selected_action = "continue_pending_flow"
            allowed_tool = TOOL_CLARIFICATION
            reason = "acknowledgement with active pending flow"
        else:
            selected_action = "conversational_response"
            allowed_tool = TOOL_CONVERSATIONAL
            reason = "acknowledgement without pending flow"
    elif intent == "frustration":
        selected_action = "recovery_response"
        allowed_tool = TOOL_CONVERSATIONAL
        reason = "frustration recovery; block search and RAG"
    elif intent == "out_of_scope":
        selected_action = "boundary_response"
        allowed_tool = TOOL_CONVERSATIONAL
        reason = "out of scope boundary"
    elif intent in ("image_followup", "image_search_followup", "image_context_followup"):
        if ctx.get("has_image_context"):
            selected_action = "image_context_search"
            allowed_tool = TOOL_IMAGE_CONTEXT
            should_search = bool(_entity_category(entities))
            reason = "image context available"
        else:
            selected_action = "ask_image_clarification"
            allowed_tool = TOOL_CLARIFICATION
            reason = "image follow-up without image context"
    elif intent == "unknown":
        selected_action = "clarify_unknown"
        allowed_tool = TOOL_CLARIFICATION
        reason = "unknown intent; short clarification only"
    elif classification.get("should_search_machines") and not missing_fields:
        selected_action = "machine_search"
        allowed_tool = TOOL_MONGODB_SEARCH
        should_search = True
        reason = "classification flagged search with sufficient entities"

    permission_passed = is_tool_allowed(intent, allowed_tool)
    permission_block_reason = None
    if not permission_passed:
        permission_block_reason = f"tool {allowed_tool} not allowed for intent {intent}"
        allowed_tool = TOOL_CLARIFICATION
        selected_action = perms.get("fallback_action_if_missing") or "clarify_unknown"
        should_search = False
        should_rag = False
        should_support = False
        reason = permission_block_reason

    if allowed_tool in perms.get("blocked_tools") or []:
        permission_passed = False
        permission_block_reason = f"tool {allowed_tool} blocked for {intent}"
        allowed_tool = TOOL_CLARIFICATION
        selected_action = perms.get("fallback_action_if_missing") or "clarify_unknown"
        should_search = False
        should_rag = False
        should_support = False

    assistant_mode = perms.get("assistant_mode") or intent
    if intent == "machine_brand_query" and allowed_tool == TOOL_MONGODB_BRAND_INVENTORY:
        assistant_mode = "brand_inventory"

    return {
        "intent": intent,
        "raw_intent": raw_intent,
        "assistant_mode": assistant_mode,
        "selected_action": selected_action,
        "allowed_tool": allowed_tool,
        "blocked_tools": list(perms.get("blocked_tools") or []),
        "required_entities": list(perms.get("required_entities") or []),
        "missing_fields": missing_fields,
        "should_search_machines": should_search and permission_passed,
        "should_use_rag": should_rag and permission_passed,
        "should_use_support": should_support and permission_passed,
        "permission_passed": permission_passed,
        "permission_block_reason": permission_block_reason,
        "reason": reason,
    }


def validate_tool_call(intent: str, tool: str) -> tuple[bool, str | None]:
    """Return (ok, block_reason)."""
    if is_tool_allowed(intent, tool):
        return True, None
    return False, f"tool {tool} not allowed for intent {intent}"


def action_decision_to_router_action(
    decision: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    """
    Map Safe Action Router decision to intent_action_router action constants.
    Permission matrix remains authoritative — blocked tools never search.
    """
    from app.ai.intent_action_router import (
        ACTION_BROAD_CLARIFY,
        ACTION_CLARIFY,
        ACTION_COMPARISON,
        ACTION_CONVERSATIONAL,
        ACTION_DEFER,
        ACTION_DOCUMENT_RAG,
        ACTION_IMAGE_FOLLOWUP,
        ACTION_MACHINE_SEARCH,
        ACTION_OUT_OF_SCOPE,
        ACTION_RECOMMENDATION,
        ACTION_SUPPORT,
    )

    selected = str(decision.get("selected_action") or "")
    intent = str(decision.get("intent") or classification.get("intent") or "unknown")
    llm_intent = classification.get("llm_intent") or intent
    entities = classification.get("entities") or {}
    sf = classification.get("search_filters") or {}

    if not decision.get("permission_passed"):
        return {
            "action": ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": "permission_blocked",
            "reason": decision.get("permission_block_reason"),
        }

    if selected in ("conversational_response",):
        subtype = "greeting"
        if llm_intent in ("user_introduction",) or entities.get("name"):
            subtype = "name_intro"
        elif llm_intent == "gratitude":
            subtype = "thanks"
        elif llm_intent == "polite_conversation":
            subtype = "polite_social"
        return {
            "action": ACTION_CONVERSATIONAL,
            "tool": "conversational",
            "subtype": subtype,
            "save_user_name": entities.get("name"),
            "response_goal": classification.get("response_goal"),
        }

    if selected == "recovery_response" or intent == "frustration":
        return {
            "action": ACTION_SUPPORT,
            "tool": "support",
            "intent": "frustration",
            "response_goal": "frustration_recovery",
        }

    if selected == "boundary_response" or intent == "out_of_scope":
        return {"action": ACTION_OUT_OF_SCOPE, "tool": "support"}

    if selected in ("ask_missing_machine_fields", "ask_followup_context", "continue_pending_flow"):
        goal = classification.get("response_goal") or "collect_machine_requirements"
        if selected == "continue_pending_flow":
            goal = "continue_pending_flow"
        return {
            "action": ACTION_BROAD_CLARIFY if intent == "broad_machine_request" else ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": selected,
            "response_goal": goal,
            "missing_fields": decision.get("missing_fields") or [],
        }

    if selected in ("clarify_unknown", "ask_comparison_context", "ask_recommendation_fields", "ask_image_clarification"):
        return {
            "action": ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": selected,
            "response_goal": classification.get("response_goal") or "clarify_unknown",
            "missing_fields": decision.get("missing_fields") or [],
        }

    if selected == "document_rag":
        return {"action": ACTION_DOCUMENT_RAG, "tool": "rag"}

    if selected in ("image_context_search",):
        return {
            "action": ACTION_IMAGE_FOLLOWUP,
            "tool": "image_context",
            "category": entities.get("category") or entities.get("machine_category"),
            "city": entities.get("city"),
        }

    if selected in ("recommendation_advisory", "ask_recommendation_fields"):
        if selected == "ask_recommendation_fields":
            return {
                "action": ACTION_RECOMMENDATION,
                "tool": "recommendation",
                "purpose": entities.get("purpose"),
                "city": entities.get("city"),
                "response_goal": "recommendation_clarification",
            }
        return {
            "action": ACTION_RECOMMENDATION,
            "tool": "recommendation",
            "purpose": entities.get("purpose"),
            "city": entities.get("city"),
        }

    if selected in ("comparison_advisory", "ask_comparison_context"):
        brands = entities.get("brands") or []
        if entities.get("brand") and entities.get("brand") not in brands:
            brands = [entities["brand"], *brands]
        return {
            "action": ACTION_COMPARISON,
            "tool": "comparison",
            "brands": brands,
            "category": entities.get("category") or entities.get("machine_category"),
            "city": entities.get("city"),
            "response_goal": "show_comparison",
        }

    if selected in (
        "query_brands_by_category",
        "list_categories_for_brand",
        "check_brand_availability",
        "ask_brand_category",
    ):
        return {"action": ACTION_DEFER, "tool": "brand_inventory", "selected_action": selected}

    if selected in ("machine_search", "refine_search_filters") and decision.get("should_search_machines"):
        return {
            "action": ACTION_MACHINE_SEARCH,
            "tool": "mongodb_search",
            "response_goal": classification.get("response_goal") or "show_machine_results",
            "filters": {
                "category": sf.get("category") or entities.get("category") or entities.get("machine_category"),
                "city": sf.get("city") or entities.get("city"),
                "region": entities.get("region"),
                "brand": sf.get("brand") or entities.get("brand"),
                "model": sf.get("model") or entities.get("model"),
                "max_price": sf.get("max_price") or entities.get("max_price") or entities.get("budget"),
                "listing_type": sf.get("listing_type") or entities.get("listing_type"),
                "rent_type": entities.get("rent_type"),
                "purpose_key": entities.get("purpose"),
            },
        }

    if selected == "support_flow" or decision.get("should_use_support"):
        return {
            "action": ACTION_SUPPORT,
            "tool": "support",
            "intent": intent,
            "response_goal": classification.get("response_goal"),
        }

    return {"action": ACTION_DEFER, "tool": "legacy_pipeline"}
