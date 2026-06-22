"""
Rich LLM intent JSON schema v1.0 — single source of truth for structure and validation constants.
"""

from __future__ import annotations

from typing import Any, Optional

SCHEMA_VERSION = "1.0"

LLM_INTENTS = frozenset({
    "greeting",
    "user_introduction",
    "gratitude",
    "polite_conversation",
    "broad_machine_request",
    "machine_search",
    "machine_availability",
    "rent_machine",
    "buy_machine",
    "sell_machine",
    "machine_recommendation",
    "machine_brand_query",
    "machine_comparison",
    "comparison_request",
    "price_query",
    "cheaper_option_query",
    "higher_budget_query",
    "followup_search_refinement",
    "contact_owner",
    "order_issue",
    "refund_return",
    "payment_issue",
    "delivery_issue",
    "security_deposit",
    "invoice_issue",
    "platform_how_to",
    "support_request",
    "document_question",
    "image_followup",
    "voice_followup",
    "acknowledgement",
    "frustration",
    "out_of_scope",
    "unknown",
})

ASSISTANT_MODES = frozenset({
    "conversation",
    "machine_search",
    "recommendation",
    "support",
    "document_qa",
    "image_followup",
    "clarification",
    "out_of_scope",
})

LANGUAGES = frozenset({"english", "hindi", "hinglish"})
SENTIMENTS = frozenset({"neutral", "positive", "confused", "frustrated", "urgent"})
LISTING_TYPES = frozenset({"rent", "buy", "sell", "auction", "tender", "unknown"})

SEARCH_ALLOWED_INTENTS = frozenset({
    "machine_search",
    "rent_machine",
    "buy_machine",
    "machine_availability",
    "price_query",
    "comparison_request",
    "machine_comparison",
    "machine_recommendation",
    "cheaper_option_query",
    "higher_budget_query",
    "followup_search_refinement",
})

SEARCH_BLOCKED_INTENTS = LLM_INTENTS - SEARCH_ALLOWED_INTENTS

INTENT_LEGACY_MAP: dict[str, str] = {
    "comparison_request": "compare_machine",
    "machine_comparison": "machine_comparison",
    "delivery_issue": "delivery_logistics",
    "image_followup": "image_search_followup",
    "gratitude": "greeting",
    "polite_conversation": "greeting",
    "user_introduction": "greeting",
    "broad_machine_request": "machine_search",
    "sell_machine": "buy_machine",
    "followup_search_refinement": "machine_search",
    "machine_brand_query": "machine_brand_query",
    "cheaper_option_query": "cheaper_option_query",
    "higher_budget_query": "higher_budget_query",
    "acknowledgement": "acknowledgement",
    "frustration": "frustration",
}

CONVERSATIONAL_INTENTS = frozenset({
    "greeting",
    "user_introduction",
    "gratitude",
    "polite_conversation",
})

INTENT_DEFAULT_RESPONSE_GOAL: dict[str, str] = {
    "greeting": "greet_user",
    "user_introduction": "acknowledge_name",
    "gratitude": "greet_user",
    "polite_conversation": "greet_user",
    "broad_machine_request": "collect_machine_requirements",
    "machine_search": "show_machine_results",
    "machine_availability": "show_machine_results",
    "rent_machine": "show_machine_results",
    "buy_machine": "show_machine_results",
    "sell_machine": "collect_machine_requirements",
    "machine_recommendation": "collect_machine_requirements",
    "comparison_request": "show_comparison",
    "compare_machine": "show_comparison",
    "machine_comparison": "show_comparison",
    "price_query": "show_machine_results",
    "contact_owner": "offer_handover",
    "order_issue": "collect_booking_id",
    "refund_return": "collect_booking_id",
    "payment_issue": "collect_transaction_id",
    "delivery_issue": "collect_booking_id",
    "security_deposit": "explain_security_deposit",
    "invoice_issue": "collect_booking_id",
    "platform_how_to": "explain_rental_process",
    "support_request": "offer_handover",
    "document_question": "answer_document_question",
    "image_followup": "ask_image_clarification",
    "voice_followup": "continue_followup",
    "out_of_scope": "out_of_scope_boundary",
    "frustration": "frustration_recovery",
    "acknowledgement": "continue_pending_flow",
    "machine_brand_query": "show_brand_inventory",
    "machine_advisory": "domain_knowledge_answer",
    "domain_knowledge": "domain_knowledge_answer",
    "assistant_identity": "assistant_identity",
    "unknown": "clarify_unknown",
}


def empty_rich_payload(*, reason: str = "", layer: str = "fallback") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "intent": "unknown",
        "sub_intent": None,
        "confidence": 0.0,
        "language": "english",
        "user_sentiment": "neutral",
        "assistant_mode": "clarification",
        "response_goal": "continue_followup",
        "requires_clarification": True,
        "requires_human_handover": False,
        "should_search_machines": False,
        "should_use_rag": False,
        "should_use_image_context": False,
        "next_best_action": "ask_clarification",
        "entities": empty_entities(),
        "missing_fields": ["intent"],
        "validation_notes": [],
        "search_filters": empty_search_filters(),
        "safety": {
            "can_answer_directly": False,
            "can_generate_final_response": True,
            "must_not_search": True,
            "must_not_invent_data": True,
        },
        "reason": reason,
        "layer": layer,
    }


def empty_entities() -> dict[str, Any]:
    return {
        "user": {"name": None},
        "machine": {
            "category": None,
            "brand": None,
            "brands": [],
            "model": None,
            "purpose": None,
            "listing_type": None,
            "rent_type": None,
            "condition": None,
        },
        "location": {"city": None, "state": None, "nearby_allowed": False},
        "commercial": {
            "budget": None,
            "budget_type": None,
            "currency": "INR",
            "price_max": None,
            "price_min": None,
        },
        "support": {
            "issue_category": None,
            "issue_subcategory": None,
            "order_id": None,
            "booking_id": None,
            "transaction_id": None,
            "payment_method": None,
            "amount": None,
        },
        "document": {
            "document_reference": False,
            "document_type": None,
            "question_about_document": False,
        },
        "image": {"image_reference": False, "detected_machine_hint": None},
    }


def empty_search_filters() -> dict[str, Any]:
    return {
        "category": None,
        "city": None,
        "max_price": None,
        "min_price": None,
        "brand": None,
        "model": None,
        "listing_type": None,
        "availability_required": True,
    }


def flatten_entities(entities: dict[str, Any]) -> dict[str, Any]:
    """Flat dict for legacy router / search merge."""
    user = entities.get("user") or {}
    machine = entities.get("machine") or {}
    location = entities.get("location") or {}
    commercial = entities.get("commercial") or {}
    support = entities.get("support") or {}
    document = entities.get("document") or {}
    image = entities.get("image") or {}
    return {
        "name": user.get("name"),
        "machine_category": machine.get("category"),
        "category": machine.get("category"),
        "brand": machine.get("brand"),
        "brands": list(machine.get("brands") or []),
        "model": machine.get("model"),
        "purpose": machine.get("purpose"),
        "listing_type": machine.get("listing_type"),
        "rent_type": machine.get("rent_type"),
        "condition": machine.get("condition"),
        "city": location.get("city"),
        "state": location.get("state"),
        "region": location.get("state"),
        "nearby_allowed": location.get("nearby_allowed"),
        "budget": commercial.get("budget") or commercial.get("price_max"),
        "max_price": commercial.get("price_max") or commercial.get("budget"),
        "min_price": commercial.get("price_min"),
        "order_id": support.get("order_id") or support.get("booking_id"),
        "booking_id": support.get("booking_id"),
        "transaction_id": support.get("transaction_id"),
        "issue_type": support.get("issue_category"),
        "issue_subcategory": support.get("issue_subcategory"),
        "document_reference": document.get("document_reference"),
        "image_reference": image.get("image_reference"),
    }


def build_search_filters_from_rich(payload: dict[str, Any]) -> dict[str, Any]:
    sf = dict(payload.get("search_filters") or empty_search_filters())
    flat = flatten_entities(payload.get("entities") or {})
    if not sf.get("category"):
        sf["category"] = flat.get("machine_category") or flat.get("category")
    if not sf.get("city"):
        sf["city"] = flat.get("city")
    if sf.get("max_price") is None:
        sf["max_price"] = flat.get("max_price")
    if not sf.get("brand"):
        sf["brand"] = flat.get("brand")
    if not sf.get("model"):
        sf["model"] = flat.get("model")
    if not sf.get("listing_type"):
        sf["listing_type"] = flat.get("listing_type")
    return {k: v for k, v in sf.items() if v is not None}


def merge_flat_into_rich(flat: dict[str, Any]) -> dict[str, Any]:
    """Upgrade flat/fast-path entities into rich nested shape."""
    entities = empty_entities()
    if flat.get("name"):
        entities["user"]["name"] = flat["name"]
    for key, rich_key in (
        ("machine_category", "category"),
        ("category", "category"),
        ("brand", "brand"),
        ("model", "model"),
        ("purpose", "purpose"),
        ("listing_type", "listing_type"),
        ("rent_type", "rent_type"),
        ("condition", "condition"),
    ):
        val = flat.get(key)
        if val:
            entities["machine"][rich_key] = val
    if flat.get("city"):
        entities["location"]["city"] = flat["city"]
    if flat.get("region") or flat.get("state"):
        entities["location"]["state"] = flat.get("state") or flat.get("region")
    if flat.get("budget") or flat.get("max_price"):
        entities["commercial"]["budget"] = flat.get("budget") or flat.get("max_price")
        entities["commercial"]["price_max"] = flat.get("max_price") or flat.get("budget")
    if flat.get("order_id"):
        entities["support"]["order_id"] = flat["order_id"]
        entities["support"]["booking_id"] = flat["order_id"]
    if flat.get("issue_type"):
        entities["support"]["issue_category"] = flat["issue_type"]
    if flat.get("document_reference"):
        entities["document"]["document_reference"] = True
    if flat.get("image_reference"):
        entities["image"]["image_reference"] = True
    return entities


def default_assistant_mode(intent: str) -> str:
    mapping = {
        "greeting": "conversation",
        "user_introduction": "conversation",
        "gratitude": "conversation",
        "polite_conversation": "conversation",
        "broad_machine_request": "clarification",
        "machine_search": "machine_search",
        "machine_recommendation": "recommendation",
        "document_question": "document_qa",
        "payment_issue": "support",
        "refund_return": "support",
        "order_issue": "support",
        "delivery_issue": "support",
        "out_of_scope": "out_of_scope",
        "unknown": "clarification",
        "comparison_request": "machine_search",
        "image_followup": "image_followup",
    }
    return mapping.get(intent, "support")


def infer_response_goal(payload: dict[str, Any]) -> str:
    explicit = payload.get("response_goal")
    if explicit:
        return str(explicit)
    intent = payload.get("intent") or "unknown"
    if payload.get("requires_clarification"):
        missing = payload.get("missing_fields") or []
        if "city" in missing:
            return "ask_city"
        if "purpose_or_category" in missing or "machine.category" in missing:
            return "collect_machine_requirements" if intent == "broad_machine_request" else "ask_purpose"
        if any("transaction" in m or "booking" in m for m in missing):
            return "collect_transaction_id"
    return INTENT_DEFAULT_RESPONSE_GOAL.get(intent, "continue_followup")


def to_legacy_classification(rich: dict[str, Any]) -> dict[str, Any]:
    intent = rich.get("intent") or "unknown"
    legacy_intent = INTENT_LEGACY_MAP.get(intent, intent)
    flat = flatten_entities(rich.get("entities") or {})
    return {
        "intent": legacy_intent,
        "llm_intent": intent,
        "confidence": rich.get("confidence"),
        "should_search_machines": rich.get("should_search_machines"),
        "requires_clarification": rich.get("requires_clarification"),
        "requires_handover": rich.get("requires_human_handover") or rich.get("requires_handover"),
        "assistant_mode": rich.get("assistant_mode"),
        "entities": flat,
        "missing_fields": rich.get("missing_fields") or [],
        "response_goal": rich.get("response_goal"),
        "user_sentiment": rich.get("user_sentiment"),
        "language": rich.get("language"),
        "search_filters": rich.get("search_filters") or build_search_filters_from_rich(rich),
        "validation_notes": rich.get("validation_notes") or [],
        "reason": rich.get("reason"),
        "layer": rich.get("layer"),
        "normalized_message": rich.get("normalized_message"),
        "rich": rich,
    }
