"""
Central Tool Permission Matrix for rules-first assistant routing.

Defines allowed/blocked tools and fallback actions per intent.
"""

from __future__ import annotations

from typing import Any

# Canonical tool identifiers
TOOL_MONGODB_SEARCH = "mongodb_search"
TOOL_MONGODB_BRAND_INVENTORY = "mongodb_brand_inventory"
TOOL_RAG = "rag"
TOOL_SUPPORT = "support"
TOOL_IMAGE_CONTEXT = "image_context"
TOOL_CONVERSATIONAL = "conversational"
TOOL_CLARIFICATION = "clarification"
TOOL_COMPARISON = "comparison"
TOOL_RECOMMENDATION = "recommendation"
TOOL_NONE = "none"

_DEFAULT: dict[str, Any] = {
    "allowed_tools": [TOOL_CONVERSATIONAL, TOOL_CLARIFICATION],
    "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_SUPPORT],
    "required_entities": [],
    "fallback_action_if_missing": "clarify_unknown",
    "assistant_mode": "clarification",
    "can_search_machines": False,
    "can_use_rag": False,
    "can_use_support": False,
    "can_use_image_context": False,
    "can_answer_without_tool": True,
}


def _support_perm(mode: str) -> dict[str, Any]:
    return {
        **_DEFAULT,
        "allowed_tools": [TOOL_SUPPORT, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_MONGODB_BRAND_INVENTORY],
        "fallback_action_if_missing": "collect_support_details",
        "assistant_mode": mode,
        "can_use_support": True,
    }


def _image_perm() -> dict[str, Any]:
    return {
        **_DEFAULT,
        "allowed_tools": [TOOL_IMAGE_CONTEXT, TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["image_or_category_context"],
        "fallback_action_if_missing": "ask_image_clarification",
        "assistant_mode": "image_clarification",
        "can_use_image_context": True,
        "can_search_machines": True,
    }


INTENT_PERMISSIONS: dict[str, dict[str, Any]] = {
    "greeting": {
        **{k: v for k, v in _DEFAULT.items() if k != "assistant_mode"},
        "allowed_tools": [TOOL_CONVERSATIONAL, TOOL_NONE],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_SUPPORT, TOOL_MONGODB_BRAND_INVENTORY],
        "assistant_mode": "greeting",
        "fallback_action_if_missing": "conversational_response",
    },
    "user_introduction": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CONVERSATIONAL],
        "assistant_mode": "conversational",
        "fallback_action_if_missing": "conversational_response",
    },
    "gratitude": {**_DEFAULT, "assistant_mode": "conversational", "fallback_action_if_missing": "conversational_response"},
    "polite_conversation": {**_DEFAULT, "assistant_mode": "conversational", "fallback_action_if_missing": "conversational_response"},
    "broad_machine_request": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CLARIFICATION],
        "required_entities": ["purpose_or_category", "city"],
        "fallback_action_if_missing": "ask_missing_machine_fields",
        "assistant_mode": "clarification",
    },
    "machine_recommendation": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CLARIFICATION, TOOL_RECOMMENDATION, TOOL_MONGODB_SEARCH],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["purpose_or_category", "city"],
        "fallback_action_if_missing": "ask_recommendation_fields",
        "assistant_mode": "recommendation_clarification",
        "can_search_machines": False,
    },
    "machine_search": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["category_or_purpose"],
        "fallback_action_if_missing": "ask_missing_machine_fields",
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "rent_machine": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["category_or_purpose"],
        "fallback_action_if_missing": "ask_missing_machine_fields",
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "buy_machine": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["category_or_purpose"],
        "fallback_action_if_missing": "ask_missing_machine_fields",
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "machine_brand_query": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_BRAND_INVENTORY, TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["category_or_brand_or_context"],
        "fallback_action_if_missing": "ask_brand_category",
        "assistant_mode": "brand_inventory",
        "can_search_machines": True,
    },
    "machine_comparison": {
        **_DEFAULT,
        "allowed_tools": [TOOL_COMPARISON, TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["comparison_items"],
        "fallback_action_if_missing": "ask_comparison_context",
        "assistant_mode": "comparison",
        "can_answer_without_tool": True,
    },
    "compare_machine": {
        **_DEFAULT,
        "allowed_tools": [TOOL_COMPARISON, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT, TOOL_MONGODB_SEARCH],
        "assistant_mode": "comparison",
        "fallback_action_if_missing": "ask_comparison_context",
    },
    "cheaper_option_query": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["previous_filters_or_entities"],
        "fallback_action_if_missing": "ask_followup_context",
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "higher_budget_query": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "required_entities": ["previous_filters_or_entities"],
        "fallback_action_if_missing": "ask_followup_context",
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "price_query": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "machine_availability": {
        **_DEFAULT,
        "allowed_tools": [TOOL_MONGODB_SEARCH, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_RAG, TOOL_SUPPORT],
        "assistant_mode": "machine_search",
        "can_search_machines": True,
    },
    "contact_owner": {
        **_DEFAULT,
        "allowed_tools": [TOOL_SUPPORT, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG],
        "required_entities": ["machine_context"],
        "fallback_action_if_missing": "ask_listing_context",
        "assistant_mode": "support",
        "can_use_support": True,
    },
    "payment_issue": _support_perm("payment_issue"),
    "refund_return": _support_perm("refund_return"),
    "delivery_issue": _support_perm("delivery_logistics"),
    "delivery_logistics": _support_perm("delivery_logistics"),
    "invoice_issue": _support_perm("payment_issue"),
    "order_issue": _support_perm("order_issue"),
    "security_deposit": _support_perm("payment_issue"),
    "complaint": _support_perm("support"),
    "support_request": _support_perm("support"),
    "human_handover": _support_perm("support"),
    "platform_how_to": _support_perm("platform_how_to"),
    "general_marketplace_help": _support_perm("support"),
    "general_help": _support_perm("support"),
    "booking_help": _support_perm("platform_how_to"),
    "document_question": {
        **_DEFAULT,
        "allowed_tools": [TOOL_RAG, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_SUPPORT],
        "required_entities": ["document_context"],
        "fallback_action_if_missing": "ask_document_upload",
        "assistant_mode": "document_qa",
        "can_use_rag": True,
    },
    "image_search_followup": _image_perm(),
    "image_followup": _image_perm(),
    "image_context_followup": _image_perm(),
    "acknowledgement": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CONVERSATIONAL, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_SUPPORT],
        "fallback_action_if_missing": "continue_pending_flow",
        "assistant_mode": "conversational",
    },
    "frustration": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CONVERSATIONAL, TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_SUPPORT, TOOL_MONGODB_BRAND_INVENTORY],
        "fallback_action_if_missing": "recovery_response",
        "assistant_mode": "support",
        "can_use_support": False,
    },
    "out_of_scope": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CONVERSATIONAL],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_SUPPORT],
        "fallback_action_if_missing": "boundary_response",
        "assistant_mode": "out_of_scope",
    },
    "unknown": {
        **_DEFAULT,
        "allowed_tools": [TOOL_CLARIFICATION],
        "blocked_tools": [TOOL_MONGODB_SEARCH, TOOL_RAG, TOOL_SUPPORT, TOOL_MONGODB_BRAND_INVENTORY],
        "fallback_action_if_missing": "clarify_unknown",
        "assistant_mode": "clarification",
    },
}


def get_intent_permissions(intent: str) -> dict[str, Any]:
    key = (intent or "unknown").strip().lower()
    base = dict(_DEFAULT)
    base.update(INTENT_PERMISSIONS.get(key, INTENT_PERMISSIONS["unknown"]))
    return base


def is_tool_allowed(intent: str, tool: str) -> bool:
    perms = get_intent_permissions(intent)
    allowed = set(perms.get("allowed_tools") or [])
    blocked = set(perms.get("blocked_tools") or [])
    if tool in blocked:
        return False
    return tool in allowed or tool == TOOL_NONE
