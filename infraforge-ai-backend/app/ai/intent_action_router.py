"""
Action router — maps validated LLM classification to backend tool selection.

No machine data invention; only chooses which deterministic tool to invoke.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.intent_schema import (
    CONVERSATIONAL_INTENTS,
    build_search_filters_from_rich,
    infer_response_goal,
)

ACTION_CONVERSATIONAL = "conversational"
ACTION_BROAD_CLARIFY = "broad_clarify"
ACTION_MACHINE_SEARCH = "machine_search"
ACTION_RECOMMENDATION = "recommendation"
ACTION_SUPPORT = "support"
ACTION_DOCUMENT_RAG = "document_rag"
ACTION_IMAGE_FOLLOWUP = "image_followup"
ACTION_OUT_OF_SCOPE = "out_of_scope"
ACTION_CLARIFY = "clarify"
ACTION_DEFER = "defer"
ACTION_COMPARISON = "comparison"


def select_action(classification: dict[str, Any]) -> dict[str, Any]:
    """
    Return action dict: { action, tool, subtype, ... } for assistant_router.
    """
    intent = classification.get("llm_intent") or classification.get("intent") or "unknown"
    llm_intent = classification.get("llm_intent") or intent
    confidence = float(classification.get("confidence") or 0)
    entities = classification.get("entities") or {}
    requires_clarification = bool(classification.get("requires_clarification"))
    should_search = bool(classification.get("should_search_machines"))

    if confidence < 0.55 and intent not in CONVERSATIONAL_INTENTS:
        return {
            "action": ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": "low_confidence",
            "reason": "low_confidence_clarify",
        }

    if llm_intent in CONVERSATIONAL_INTENTS or intent in ("greeting",):
        subtype = llm_intent if llm_intent in CONVERSATIONAL_INTENTS else "greeting"
        if llm_intent == "user_introduction" or entities.get("name"):
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
            "response_goal": classification.get("response_goal") or (
                "acknowledge_name" if subtype == "name_intro" else "greet_user"
            ),
        }

    if llm_intent == "broad_machine_request" or (
        requires_clarification
        and not should_search
        and intent == "machine_search"
        and not entities.get("machine_category")
        and not entities.get("purpose")
    ):
        return {
            "action": ACTION_BROAD_CLARIFY,
            "tool": "clarification",
            "subtype": "broad_machine",
            "response_goal": "collect_machine_requirements",
        }

    if llm_intent == "document_question" or (
        entities.get("document_reference") and intent == "document_question"
    ):
        return {
            "action": ACTION_DOCUMENT_RAG,
            "tool": "rag",
        }

    if llm_intent == "image_followup" or intent == "image_search_followup":
        return {
            "action": ACTION_IMAGE_FOLLOWUP,
            "tool": "image_context",
            "category": entities.get("machine_category") or entities.get("category"),
            "city": entities.get("city"),
        }

    if llm_intent == "out_of_scope" or intent == "out_of_scope":
        return {
            "action": ACTION_OUT_OF_SCOPE,
            "tool": "support",
        }

    if llm_intent == "frustration" or intent == "frustration":
        return {
            "action": ACTION_SUPPORT,
            "tool": "support",
            "intent": "frustration",
            "response_goal": "frustration_recovery",
        }

    if llm_intent == "acknowledgement" or intent == "acknowledgement":
        return {
            "action": ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": "acknowledgement",
            "response_goal": "continue_pending_flow",
        }

    if llm_intent == "machine_brand_query" or intent == "machine_brand_query":
        return {
            "action": ACTION_DEFER,
            "tool": "brand_inventory",
        }

    if llm_intent == "machine_recommendation" or intent == "machine_recommendation":
        return {
            "action": ACTION_RECOMMENDATION,
            "tool": "recommendation",
            "purpose": entities.get("purpose"),
            "city": entities.get("city"),
        }

    if llm_intent in ("comparison_request", "machine_comparison", "compare_machine") or intent in (
        "comparison_request", "machine_comparison", "compare_machine",
    ):
        return {
            "action": ACTION_COMPARISON,
            "tool": "comparison",
            "brands": entities.get("brands") or ([entities["brand"]] if entities.get("brand") else []),
            "category": entities.get("category") or entities.get("machine_category"),
            "city": entities.get("city"),
            "response_goal": "show_comparison",
        }

    support_intents = {
        "payment_issue", "refund_return", "order_issue", "delivery_issue",
        "delivery_logistics", "security_deposit", "invoice_issue",
        "support_request", "human_handover", "complaint", "contact_owner",
        "platform_how_to", "general_marketplace_help", "general_help",
        "booking_help",
    }
    if intent in support_intents or llm_intent in {
        "payment_issue", "refund_return", "order_issue", "delivery_issue",
        "security_deposit", "invoice_issue", "support_request", "platform_how_to",
    }:
        support_goal = classification.get("response_goal") or infer_response_goal(
            classification.get("rich") or classification
        )
        return {
            "action": ACTION_SUPPORT,
            "tool": "support",
            "intent": intent,
            "response_goal": support_goal,
        }

    if should_search and not requires_clarification:
        rich = classification.get("rich") or {}
        sf = classification.get("search_filters") or build_search_filters_from_rich(rich) or {}
        return {
            "action": ACTION_MACHINE_SEARCH,
            "tool": "mongodb_search",
            "response_goal": classification.get("response_goal") or infer_response_goal(rich),
            "filters": {
                "category": sf.get("category") or entities.get("machine_category") or entities.get("category"),
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

    if requires_clarification:
        return {
            "action": ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": "missing_fields",
            "missing_fields": classification.get("missing_fields") or [],
        }

    if intent == "unknown":
        return {
            "action": ACTION_CLARIFY,
            "tool": "clarification",
            "subtype": "unknown",
        }

    return {
        "action": ACTION_DEFER,
        "tool": "legacy_pipeline",
    }
