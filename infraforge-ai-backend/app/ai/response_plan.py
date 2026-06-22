"""
Backend Response Plan — defines WHAT the assistant should say (never HOW).

Generated after action routing and tool execution; consumed by dynamic response generator.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.intent_schema import infer_response_goal

TONE_MAP = {
    "frustrated": "empathetic",
    "urgent": "concise",
    "confused": "guiding",
    "positive": "friendly_professional",
    "neutral": "friendly_professional",
}

GOAL_MUST_ASK: dict[str, list[str]] = {
    "collect_machine_requirements": ["work type or machine category", "city"],
    "ask_city": ["city"],
    "ask_purpose": ["work type or machine category"],
    "ask_purpose_or_category": ["work type or machine category"],
    "collect_transaction_id": ["booking ID or transaction ID"],
    "collect_booking_id": ["booking ID or order ID"],
    "ask_document_upload": ["document upload"],
    "ask_image_clarification": ["machine type or clear photo", "city if searching"],
    "continue_followup": ["what you need help with"],
    "continue_pending_flow": ["missing detail from pending flow"],
    "recommendation_clarification": ["project or work type"],
    "clarify_unknown": ["what you need help with"],
    "support_collect_details": ["booking ID or transaction ID"],
}

GOAL_SUGGESTIONS: dict[str, list[str]] = {
    "collect_machine_requirements": ["Digging", "Lifting", "Compaction", "Loading", "Transport", "Road work"],
    "ask_purpose": ["Digging", "Compaction", "Lifting", "Transport", "Loading"],
    "ask_city": ["Jaipur", "Delhi", "Mumbai", "Pune"],
    "show_machine_results": ["Show cheaper options", "Rent only", "Compare machines", "Contact owner"],
    "explain_no_result": ["Search nearby cities", "Try similar machines", "Increase budget", "Contact support"],
    "explain_no_result_with_recovery": [
        "Search nearby cities", "Show other brands", "Increase budget",
        "Try similar machines", "Contact support",
    ],
    "suggest_similar_machines": ["Compare machines", "Show cheaper options", "Rent only", "Contact owner"],
    "collect_transaction_id": ["Share booking ID", "Share transaction ID", "Talk to support", "Raise request"],
    "collect_booking_id": ["Share booking ID", "Talk to support", "Raise request"],
    "offer_handover": ["Call support", "WhatsApp", "Raise request"],
    "ask_document_upload": ["Upload PDF", "Ask another question"],
    "ask_image_clarification": ["Upload clearer image", "Search by text", "Select machine type"],
    "greet_user": ["Search Machine", "Ask recommendation", "Contact support"],
    "acknowledge_name": ["Search Machine", "Ask recommendation", "Contact support"],
    "out_of_scope_boundary": ["Search Machine", "Contact support"],
    "show_brand_inventory": ["Excavator", "Road Roller", "Crane", "Backhoe Loader"],
    "show_comparison": ["Compare machines", "Show cheaper options", "Contact owner"],
    "frustration_recovery": ["Talk to support", "Search Machine", "Share booking ID"],
    "continue_pending_flow": ["Excavator", "Road Roller", "Jaipur", "Delhi"],
    "recommendation_clarification": ["Road work", "Building", "Earthwork", "Compaction"],
    "clarify_unknown": ["Search Machine", "Contact support", "Ask recommendation"],
    "domain_knowledge_answer": ["Search this machine", "Compare brands", "Ask recommendation"],
    "assistant_identity": ["Search Machine", "Compare machines", "Contact support"],
    "unsupported_service_boundary": ["Search Machine", "Ask recommendation", "Contact support"],
    "unrelated_redirect_boundary": ["Search Machine", "Contact support", "Ask recommendation"],
}


def _sanitize_tool_result(tool_result: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Strip sensitive fields; keep facts safe for LLM prompt."""
    if not tool_result:
        return {}
    safe: dict[str, Any] = {}
    for key in (
        "message",
        "machines",
        "machine_count",
        "exact_match_found",
        "requested_category",
        "city",
        "filters",
        "sources",
        "answer",
        "assistant_mode",
        "handover",
        "preserve_machine_panel",
        "suggestions",
        "next_best_action",
        "brands",
        "categories",
    ):
        if key in tool_result and tool_result[key] is not None:
            val = tool_result[key]
            if key == "machines" and isinstance(val, list):
                safe[key] = [
                    {
                        k: m.get(k)
                        for k in (
                            "name",
                            "title",
                            "category",
                            "category_display",
                            "city",
                            "price_per_day",
                            "rental_price",
                            "selling_price",
                            "availability",
                            "brand",
                        )
                        if m.get(k) is not None
                    }
                    for m in val[:8]
                ]
            elif key == "sources" and isinstance(val, list):
                safe[key] = [
                    {k: s.get(k) for k in ("title", "page", "source") if s.get(k) is not None}
                    for s in val[:5]
                ]
            else:
                safe[key] = val
    return safe


def _must_include_from_tool(tool_result: dict[str, Any], response_goal: str) -> list[str]:
    includes: list[str] = []
    draft = (tool_result.get("message") or "").strip()
    if draft and response_goal in (
        "show_machine_results",
        "explain_no_result",
        "explain_no_result_with_recovery",
        "suggest_similar_machines",
        "answer_document_question",
        "show_brand_inventory",
        "show_comparison",
    ):
        includes.append("present_backend_draft_facts_accurately")
    machines = tool_result.get("machines") or []
    if machines:
        includes.append(f"machine_list_count:{len(machines)}")
    brands = tool_result.get("brands") or []
    if brands:
        includes.append(f"brand_list_count:{len(brands)}")
    if tool_result.get("exact_match_found") is False:
        includes.append("no_exact_match")
    if tool_result.get("sources"):
        includes.append("cite_only_provided_sources")
    return includes


def _purpose_known(collected: dict[str, Any], known: dict[str, Any]) -> bool:
    return bool(
        collected.get("purpose")
        or collected.get("category")
        or collected.get("purpose_key")
        or known.get("last_machine_category")
    )


def _city_known(collected: dict[str, Any], known: dict[str, Any]) -> bool:
    return bool(collected.get("city") or known.get("last_city"))


def _context_aware_must_ask(
    goal: str,
    missing_fields: list[str],
    collected_fields: dict[str, Any],
    known: dict[str, Any],
) -> tuple[str, list[str]]:
    """Adjust goal and must_ask so only missing fields are requested."""
    direct_answer_goals = frozenset({
        "domain_knowledge_answer",
        "assistant_identity",
        "answer_document_question",
        "show_comparison",
    })
    if goal in direct_answer_goals:
        return goal, []

    mf = set(missing_fields or [])
    purpose_known = _purpose_known(collected_fields, known)
    city_known = _city_known(collected_fields, known)

    clarification_goals = {
        "collect_machine_requirements",
        "continue_pending_flow",
        "ask_followup_context",
        "recommendation_clarification",
    }
    if goal in clarification_goals or mf & {"city", "purpose", "purpose_or_category", "category"}:
        if purpose_known and not city_known:
            return "ask_city", list(GOAL_MUST_ASK.get("ask_city", ["city"]))
        if city_known and not purpose_known:
            return "ask_purpose", list(GOAL_MUST_ASK.get("ask_purpose", ["work type or machine category"]))
        if purpose_known and city_known:
            return goal, []

    must_ask = list(GOAL_MUST_ASK.get(goal, []))
    if "city" in mf and "city" not in " ".join(must_ask):
        must_ask.append("city")
    if mf & {"purpose", "purpose_or_category", "category"}:
        if "work type or machine category" not in must_ask:
            must_ask.append("work type or machine category")
    if mf & {"booking_id", "transaction_id", "order_id"}:
        if goal == "collect_transaction_id" and "transaction ID" not in " ".join(must_ask):
            must_ask.append("transaction ID")
        if goal == "collect_booking_id" and "booking ID" not in " ".join(must_ask):
            must_ask.append("booking ID")
    return goal, must_ask


def _known_context_from_session(
    ctx: dict[str, Any],
    ents: dict[str, Any],
    mem: dict[str, Any],
    cls: dict[str, Any],
    missing: list[str],
) -> dict[str, Any]:
    conv = ctx.get("_conversation_state") or {}
    collected = dict(conv.get("collected_fields") or {})
    last_filters = dict(conv.get("last_search_filters") or ctx.get("last_filters") or {})
    if not collected and last_filters:
        for key in ("category", "city", "brand", "purpose_key"):
            if last_filters.get(key):
                collected[key] = last_filters[key]

    return {
        "user_name": ents.get("name") or ctx.get("user_name"),
        "active_flow": conv.get("active_flow"),
        "collected_fields": collected,
        "last_search_filters": last_filters,
        "last_search_results_summary": conv.get("last_search_results_summary") or {},
        "last_brand_inventory": conv.get("last_brand_inventory") or {},
        "last_support_context": conv.get("last_support_context") or mem.get("last_support_issue") or {},
        "user_profile_hints": ctx.get("user_profile_hints") or conv.get("user_profile_hints") or {},
        "selected_machine": ctx.get("selected_machine") or conv.get("selected_machine") or {},
        "session_id": ctx.get("session_id"),
        "last_intent": mem.get("recent_intents", [None])[-1] if mem.get("recent_intents") else cls.get("last_intent"),
        "last_city": last_filters.get("city") or ents.get("city") or ctx.get("last_city"),
        "last_machine_category": last_filters.get("category") or ents.get("machine_category") or ents.get("category"),
        "pending_fields": missing or conv.get("pending_fields") or mem.get("pending_fields") or [],
        "greeted": bool(ctx.get("greeted")),
    }


def _facts_from_tool(tool: dict[str, Any], known: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if tool.get("machines"):
        facts["machines"] = tool["machines"]
        facts["machine_count"] = len(tool["machines"])
    if tool.get("brands"):
        facts["brands"] = tool["brands"]
    if tool.get("categories"):
        facts["categories"] = tool["categories"]
    if tool.get("exact_match_found") is not None:
        facts["exact_match_found"] = tool["exact_match_found"]
    for key in (
        "not_found_reason", "recovery_type", "safe_alternatives",
        "auto_retry_results", "filters_used",
    ):
        if tool.get(key) is not None:
            facts[key] = tool[key]
    recovery = tool.get("recovery")
    if isinstance(recovery, dict):
        for key in (
            "recovery_type", "safe_alternatives", "auto_retry_results",
            "next_best_action", "suggestions",
        ):
            if recovery.get(key) is not None and key not in facts:
                facts[key] = recovery[key]
    if tool.get("filters"):
        facts["filters"] = tool["filters"]
    if tool.get("sources"):
        facts["sources"] = tool["sources"]
    if known.get("collected_fields"):
        facts["collected_fields"] = known["collected_fields"]
    return facts


def response_goal_for_intent(intent: str, *, assistant_mode: str = "") -> str:
    from app.ai.intent_schema import INTENT_DEFAULT_RESPONSE_GOAL

    return INTENT_DEFAULT_RESPONSE_GOAL.get(intent, "continue_followup")


def build_response_plan(
    *,
    response_goal: str,
    intent: str,
    assistant_mode: str,
    language: str = "english",
    user_sentiment: str = "neutral",
    user_message: str = "",
    classification: Optional[dict[str, Any]] = None,
    entities: Optional[dict[str, Any]] = None,
    tool_result: Optional[dict[str, Any]] = None,
    session_context: Optional[dict[str, Any]] = None,
    response_memory: Optional[dict[str, Any]] = None,
    missing_fields: Optional[list[str]] = None,
    draft_message: str = "",
    selected_action: str = "",
) -> dict[str, Any]:
    """Build Response Plan JSON for every assistant turn."""
    cls = classification or {}
    ctx = session_context or {}
    mem = response_memory or {}
    ents = entities or {}
    tool = _sanitize_tool_result(tool_result or {})
    if draft_message and not tool.get("message"):
        tool["message"] = draft_message

    goal = response_goal or cls.get("response_goal") or infer_response_goal(cls)
    missing = list(missing_fields or cls.get("missing_fields") or [])
    known = _known_context_from_session(ctx, ents, mem, cls, missing)
    collected = known.get("collected_fields") or {}

    goal, must_ask = _context_aware_must_ask(goal, missing, collected, known)
    if user_sentiment == "frustrated" and goal not in ("frustration_recovery", "explain_no_result"):
        tone = "recovery"
    else:
        tone = TONE_MAP.get(user_sentiment, "friendly_professional")

    suggestions = list(tool.get("suggestions") or GOAL_SUGGESTIONS.get(goal) or [])
    facts = _facts_from_tool(tool, known)
    action = selected_action or cls.get("selected_action") or ""

    from app.ai.context_routing_gate import get_current_gate
    from app.ai.response_safety_guard import build_fact_constraints, must_include_for_response_plan

    gate = get_current_gate() or {}
    fact_constraints = build_fact_constraints(
        intent=intent,
        response_goal=goal,
        known_context=known,
        tool_result=tool,
        intent_family=gate.get("family"),
    )
    extra_must_include = must_include_for_response_plan(fact_constraints)
    extra_must_not = list(fact_constraints.get("must_not_claim") or [])

    safety_rules = {
        "do_not_invent_data": True,
        "do_not_invent_machine": True,
        "do_not_invent_price": True,
        "do_not_invent_availability": True,
        "do_not_invent_owner": True,
        "do_not_claim_action_completed_unless_confirmed": True,
        "use_only_tool_result": True,
        "match_user_language": True,
        "keep_short": True,
    }

    return {
        "response_goal": goal,
        "intent": intent,
        "assistant_mode": assistant_mode,
        "selected_action": action,
        "language": language or cls.get("language") or "english",
        "tone": tone,
        "user_sentiment": user_sentiment,
        "must_include": _must_include_from_tool(tool, goal) + extra_must_include,
        "must_ask": must_ask,
        "must_not_claim": [
            "refund_processed",
            "delivery_date",
            "ticket_completed",
            "payment_confirmed",
            "invented_machines",
            "invented_prices",
            "invented_availability",
            "invented_owner_contact",
            "user_has_completed_rental",
            "user_has_active_booking",
            "return_or_refund_initiated",
            "owner_already_contacted",
        ] + extra_must_not,
        "fact_constraints": fact_constraints,
        "facts": facts,
        "known_context": known,
        "tool_result": tool,
        "missing_fields": missing,
        "suggestions": suggestions[:8],
        "avoid_repeating": list(mem.get("recent_response_signatures") or [])[-5:],
        "avoid_phrases": list(mem.get("recent_messages_summary") or [])[-3:],
        "safety_rules": safety_rules,
        "rules": safety_rules,
        "frontend_payload": {
            "machines": tool.get("machines") or [],
            "filters": tool.get("filters") or known.get("last_search_filters") or {},
            "handover": tool.get("handover"),
            "context": {
                "intent": intent,
                "assistant_mode": assistant_mode,
                "selected_action": action,
            },
            "advisor_message": None,
        },
        "user_message": user_message[:500],
    }
