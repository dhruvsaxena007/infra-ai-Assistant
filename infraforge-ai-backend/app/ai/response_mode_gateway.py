"""
Response Mode Gateway — enforces canonical response modes from semantic understanding.

Prevents false out-of-domain, fixes support/meta_help/memory routing.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.semantic_turn_gateway import SemanticTurnUnderstanding

MODE_TO_ASSISTANT_MODE = {
    "greeting": "greeting",
    "meta_help": "conversational",
    "memory_answer": "conversational",
    "domain_knowledge": "advisory",
    "recommendation": "recommendation",
    "comparison": "comparison",
    "machine_search": "machine_search",
    "search_refinement": "machine_search",
    "support": "support",
    "clarification": "clarification",
    "frustration_recovery": "conversational",
    "off_topic_redirect": "clarification",
    "safe_error_fallback": "clarification",
    "conversational": "conversational",
}

INTENT_TO_LEGACY = {
    "machine_search": "machine_search",
    "recommendation": "machine_recommendation",
    "comparison": "machine_comparison",
    "support": "support_request",
    "domain_knowledge": "machine_advisory",
    "meta_help": "general_marketplace_help",
    "memory_question": "user_introduction",
    "conversational": "polite_conversation",
    "off_topic": "out_of_scope",
    "clarification_answer": "machine_search",
    "frustration": "frustration",
    "greeting": "greeting",
    "search_refinement": "followup_search_refinement",
}


def resolve_response_mode(understanding: SemanticTurnUnderstanding) -> dict[str, Any]:
    """
    Map semantic understanding → assistant routing decision.
    Returns mode, intent, flags, and whether to block machine context reuse.
    """
    mode = understanding.response_mode or "conversational"
    intent = INTENT_TO_LEGACY.get(understanding.primary_intent, understanding.primary_intent)
    assistant_mode = MODE_TO_ASSISTANT_MODE.get(mode, "conversational")

    block_machine_context = understanding.primary_intent in (
        "support", "off_topic", "frustration", "meta_help", "memory_question", "greeting",
    )

    skip_domain_boundary = understanding.primary_intent in (
        "support", "comparison", "recommendation", "domain_knowledge",
        "meta_help", "memory_question", "machine_search", "clarification_answer",
        "search_refinement",
    )

    force_support = understanding.primary_intent == "support"
    force_knowledge = understanding.should_answer_knowledge or understanding.primary_intent in (
        "domain_knowledge", "meta_help", "memory_question",
    )

    return {
        "response_mode": mode,
        "legacy_intent": intent,
        "assistant_mode": assistant_mode,
        "block_machine_context": block_machine_context,
        "skip_domain_boundary": skip_domain_boundary,
        "force_support": force_support,
        "force_knowledge": force_knowledge,
        "should_search": understanding.should_search,
        "should_recommend": understanding.should_recommend,
        "should_compare": understanding.should_compare,
        "domain_status": understanding.domain_status,
        "confidence": understanding.confidence,
        "reason": understanding.reason,
        "is_fragment": understanding.is_fragment,
        "entities": understanding.entities,
        "context_reference": understanding.context_reference,
        "missing_fields": understanding.missing_fields,
    }


async def build_memory_answer_draft(
    understanding: SemanticTurnUnderstanding,
    *,
    session_ctx: dict | None = None,
    lang: str = "english",
) -> dict[str, Any]:
    """Safe memory answer for 'what is my name' — never crashes."""
    ctx = session_ctx or {}
    name = (
        understanding.context_reference.get("user_name")
        or ctx.get("user_name")
        or (ctx.get("collected_fields") or {}).get("name")
    )
    if name:
        if lang == "hindi":
            msg = f"Aapka naam **{name}** hai — main is session me yaad rakhta hoon."
        elif lang == "hinglish":
            msg = f"Aapka naam **{name}** hai — main is session me remember karta hoon."
        else:
            msg = f"Your name is **{name}** — I've noted it for this session."
    else:
        from app.ai.safe_error_fallback import fallback_message_for_stage
        msg = fallback_message_for_stage("memory_answer", lang=lang)

    return {
        "message": msg,
        "response_goal": "memory_answer",
        "assistant_mode": "conversational",
        "suggestions": ["Search Machine", "Ask recommendation"],
    }


async def build_meta_help_draft(*, lang: str = "english") -> dict[str, Any]:
    """Meta help for capability questions — not wellbeing."""
    if lang == "hindi":
        msg = (
            "Main InfraForge AI hoon — construction aur heavy equipment marketplace assistant. "
            "Main aapki madad kar sakta hoon: machine search (rent/buy), recommendations, "
            "brand comparison, price filters, aur platform support (booking, payment, refund)."
        )
    elif lang == "hinglish":
        msg = (
            "Main InfraForge AI hoon — construction equipment marketplace assistant. "
            "Help kar sakta hoon: machine search, recommendations, brand compare, "
            "budget/city filters, aur support (booking/payment/refund)."
        )
    else:
        msg = (
            "I'm InfraForge AI — your construction and heavy-equipment marketplace assistant. "
            "I can help you search machines (rent/buy), get recommendations for your project, "
            "compare brands, filter by city and budget, and resolve platform support issues."
        )
    return {
        "message": msg,
        "response_goal": "meta_help",
        "assistant_mode": "conversational",
        "suggestions": ["Search Machine", "Ask recommendation", "Contact support"],
    }
