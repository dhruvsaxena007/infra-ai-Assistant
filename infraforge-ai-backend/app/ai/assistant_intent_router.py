"""
Central assistant intent router for InfraForge Marketplace Assistant.

Layered classification:
  1. Deterministic rules / keywords
  2. Fuzzy spelling correction (rapidfuzz)
  3. Optional Groq fallback when confidence is low and flag enabled
  4. Unknown fallback without machine search
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.intent_classifier import classify_intent as _classify_intent

# Intent → UI assistant_mode mapping
_ASSISTANT_MODE_MAP: dict[str, str] = {
    "greeting": "greeting",
    "user_introduction": "conversational",
    "gratitude": "conversational",
    "polite_conversation": "conversational",
    "broad_machine_request": "clarification",
    "machine_brand_query": "brand_query",
    "machine_comparison": "comparison",
    "compare_machine": "comparison",
    "higher_budget_query": "machine_search",
    "cheaper_option_query": "machine_search",
    "acknowledgement": "conversational",
    "frustration": "support",
    "machine_search": "machine_search",
    "machine_availability": "machine_search",
    "machine_recommendation": "project_recommendation",
    "rent_machine": "machine_search",
    "buy_machine": "machine_search",
    "comparison_request": "comparison",
    "image_search_followup": "machine_search",
    "image_followup": "machine_search",
    "image_context_followup": "machine_search",
    "voice_followup": "conversational",
    "recommendation_result_search": "machine_search",
    "document_question": "document_qa",
    "order_issue": "order_issue",
    "refund_return": "refund_return",
    "payment_issue": "payment_issue",
    "invoice_issue": "payment_issue",
    "delivery_logistics": "delivery_logistics",
    "delivery_issue": "delivery_logistics",
    "security_deposit": "payment_issue",
    "contact_owner": "support",
    "platform_how_to": "platform_how_to",
    "general_marketplace_help": "support",
    "general_help": "support",
    "booking_help": "platform_how_to",
    "complaint": "support",
    "support_request": "support",
    "human_handover": "support",
    "out_of_scope": "out_of_scope",
    "unknown": "clarification",
    "compare_machine": "clarification",
    "price_query": "machine_search",
}


def _normalize_entities(raw: dict[str, Any]) -> dict[str, Any]:
    """Map parser / LLM entities to stable API shape."""
    return {
        "name": raw.get("name"),
        "category": raw.get("machine_type") or raw.get("category"),
        "city": raw.get("city"),
        "region": raw.get("region"),
        "brand": raw.get("brand"),
        "model": raw.get("model"),
        "purpose": raw.get("purpose"),
        "max_price": raw.get("max_price") or raw.get("budget"),
        "listing_type": raw.get("listing_type"),
        "rent_type": raw.get("rent_type"),
        "order_id": raw.get("order_id"),
        "issue_type": raw.get("issue_type"),
        "document_reference": raw.get("document_reference"),
        "image_reference": raw.get("image_reference"),
    }


def _intent_aliases(intent: str) -> str:
    if intent == "general_marketplace_help":
        return "general_help"
    if intent == "support_request":
        return "human_handover"
    if intent == "image_search_followup":
        return "image_context_followup"
    return intent


async def classify_assistant_intent(
    message: str,
    context: dict | None = None,
) -> dict[str, Any]:
    """
    Classify user message into marketplace assistant intent.

    Returns dict with intent, confidence, should_search_machines,
    requires_clarification, requires_handover, assistant_mode, entities, reason.
    """
    result = await _classify_intent(message, context)
    intent = _intent_aliases(result.get("intent") or "unknown")
    llm_intent = result.get("llm_intent") or intent
    entities = _normalize_entities(result.get("entities") or {})

    assistant_mode = result.get("assistant_mode") or _ASSISTANT_MODE_MAP.get(llm_intent) or _ASSISTANT_MODE_MAP.get(intent, "unknown")
    if intent == "human_handover":
        result["requires_handover"] = True

    out = {
        "intent": intent,
        "llm_intent": llm_intent,
        "confidence": float(result.get("confidence") or 0),
        "should_search_machines": bool(result.get("should_search_machines")),
        "requires_clarification": bool(result.get("requires_clarification")),
        "requires_handover": bool(result.get("requires_handover")),
        "assistant_mode": assistant_mode,
        "entities": entities,
        "missing_fields": result.get("missing_fields") or [],
        "reason": result.get("reason") or "",
        "layer": result.get("layer") or "rules",
        "normalized_message": result.get("normalized_message"),
        "response_goal": result.get("response_goal"),
        "user_sentiment": result.get("user_sentiment"),
        "language": result.get("language"),
        "search_filters": result.get("search_filters"),
        "validation_notes": result.get("validation_notes") or [],
        "intent_source": result.get("intent_source"),
        "rich": result.get("rich"),
        "should_use_rag": bool((result.get("rich") or {}).get("should_use_rag")),
    }
    try:
        from app.ai.assistant_debug_trace import record_intent_result
        record_intent_result(out)
    except Exception:
        pass
    return out


# Backward-compatible alias
classify_intent = classify_assistant_intent
