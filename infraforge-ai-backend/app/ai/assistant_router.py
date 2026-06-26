"""
Central orchestrator for InfraForge Marketplace Assistant.

ONLY this module decides routing:
  universal turn shape → marketplace intent → support | search | recommendation

Downstream modules:
  universal_turn_engine   — turn shape only (conversational/compare/attribute/refine/defer)
  intent_classifier       — marketplace intent + should_search_machines
  intent_resolver         — search filter merge + follow-ups (no support intents)
  support_response_service — support copy
  chatbot_service.execute_machine_search_turn — machine search execution only
"""

from __future__ import annotations

import sys
import re
from typing import Any, Optional

from app.ai.assistant_brain import (
    build_comparison_response,
    build_contextual_refine_response,
    build_conversational_response,
    build_machine_detail_response,
    classify_universal_turn_async,
)
from app.ai.message_normalizer import normalize_user_message_async
from app.ai.contextual_assistant import (
    build_advisory_clarification,
    build_multi_purpose_advisory,
    build_suitability_response,
)
from app.ai.conversation_context import analyze_contextual_turn, get_result_context
from app.ai.assistant_intent_router import classify_assistant_intent
from app.ai.intent_classifier import is_blocked_search_intent, is_machine_search_intent
from app.ai.rag_service import ask_rag_question, rag_has_documents
from app.ai.rules_understanding import build_chat_input_metadata
from app.ai.support_response_service import build_response
from app.ai.assistant_response_style import (
    PROJECT_TYPE_CHIPS,
    build_recommended_categories,
    recommendation_clarification_warm,
)
from app.chatbot.assistant_intelligence import (
    greeting_message,
    _GREETING_CHIPS,
    detect_project_type,
    is_broad_vague_query,
    parse_project_type_option,
    project_categories,
    project_type_pending_state,
    resolve_purpose_key,
)
from app.chatbot.language import detect_query_language
from app.chatbot.memory import save_conversation
from app.core.config import settings
from app.utils.response import success_response


def _log_classification(message: str, classification: dict[str, Any]) -> None:
    try:
        print(
            "[assistant_router]",
            f"message={message[:120]!r}",
            f"intent={classification.get('intent')}",
            f"confidence={classification.get('confidence')}",
            f"should_search={classification.get('should_search_machines')}",
            f"entities={classification.get('entities')}",
            f"layer={classification.get('layer')}",
            f"reason={classification.get('reason')}",
        )
    except UnicodeEncodeError:
        print(
            "[assistant_router]",
            f"intent={classification.get('intent')}",
            f"confidence={classification.get('confidence')}",
            f"should_search={classification.get('should_search_machines')}",
            f"layer={classification.get('layer')}",
        )


def _assistant_payload(
    *,
    message: str,
    machines: list | None = None,
    assistant_mode: str,
    suggestions: list | None = None,
    handover: dict | None = None,
    reply_language: str | None = None,
    input_meta: dict | None = None,
    **extra,
) -> dict:
    from app.chatbot.assistant_intelligence import build_response_context

    context_extra = dict(extra.pop("context_extra", None) or {})
    if reply_language:
        context_extra["reply_language"] = reply_language
    context_extra["assistant_mode"] = assistant_mode
    context_extra["intent"] = extra.pop("intent", assistant_mode)

    payload = {
        "advisor_message": extra.pop("advisor_message", None),
        "machines": machines or [],
        "exact_results": extra.pop("exact_results", []),
        "alternatives": extra.pop("alternatives", []),
        "filters": extra.pop("filters", {}),
        "search_status": extra.pop("search_status", {}),
        "context": build_response_context(
            assistant_mode=assistant_mode,
            pending_clarification=extra.pop("pending_clarification", None),
            extra=context_extra or None,
        ),
        "suggestions": suggestions or [],
        "handover": handover,
        **extra,
    }
    if input_meta:
        payload["input"] = input_meta
    return payload


def _comparison_payload_extras(resp: dict) -> dict:
    """Flatten comparison tool output for chat clients."""
    cmp = resp.get("comparison") or {}
    return {
        k: v
        for k, v in {
            "comparison": cmp or None,
            "comparison_rows": resp.get("comparison_rows") or cmp.get("comparison_rows"),
            "llm_summary": resp.get("llm_summary") or cmp.get("llm_summary"),
            "better_for_budget": resp.get("better_for_budget") or cmp.get("better_for_budget"),
            "better_rating": resp.get("better_rating") or cmp.get("better_rating"),
            "overall_recommendation": resp.get("overall_recommendation") or cmp.get("overall_recommendation"),
            "value_for_money": resp.get("value_for_money") or cmp.get("value_for_money"),
            "machine_1": cmp.get("machine_1") or ((resp.get("machines") or [None, None])[0]),
            "machine_2": cmp.get("machine_2") or ((resp.get("machines") or [None, None])[1]),
        }.items()
        if v is not None
    }


async def _respond_comparison_turn(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    turn: dict,
    last_filters: dict,
    reply_lang: str,
    input_meta: dict | None = None,
    classification: dict | None = None,
) -> dict:
    from app.chatbot.chatbot_service import _persist_last_results
    from app.chatbot.memory import save_conversation

    resp = await build_comparison_response(
        database,
        turn,
        city=turn.get("city") or last_filters.get("city"),
        lang=reply_lang,
    )
    cmp_extras = _comparison_payload_extras(resp)
    final = await _apply_dynamic_response(
        session_id=session_id,
        user_message=user_message,
        draft=resp["message"],
        response_goal="show_comparison",
        intent="comparison",
        assistant_mode=resp.get("assistant_mode", "comparison"),
        reply_lang=reply_lang,
        classification=classification,
        tool_result={
            "message": resp["message"],
            "machines": resp.get("machines") or [],
            "suggestions": resp.get("suggestions") or [],
            "preserve_machine_panel": bool(resp.get("machines")),
            **cmp_extras,
        },
    )
    reply = final["message"]
    save_conversation(session_id, user_message, reply)
    machines = resp.get("machines") or []
    if machines:
        _persist_last_results(session_id, machines, last_filters)
    return success_response(
        message=reply,
        data=_assistant_payload(
            message=reply,
            machines=machines,
            assistant_mode=resp.get("assistant_mode", "comparison"),
            suggestions=final.get("suggestions") or resp.get("suggestions") or [],
            reply_language=reply_lang,
            advisor_message=resp.get("llm_summary") or (cmp_extras.get("comparison") or {}).get("llm_summary"),
            context_extra={
                "intent": "comparison",
                "response_goal": "show_comparison",
                "response_signature": final.get("response_signature"),
                "gateway_used": True,
                "universal": turn,
            },
            input_meta=input_meta,
            **cmp_extras,
        ),
    )


async def _apply_dynamic_response(
    *,
    session_id: str,
    user_message: str,
    draft: str,
    response_goal: str,
    intent: str,
    assistant_mode: str,
    reply_lang: str,
    session_ctx: dict | None = None,
    classification: dict | None = None,
    entities: dict | None = None,
    tool_result: dict | None = None,
    sentiment: str = "neutral",
) -> dict[str, Any]:
    """Response Plan -> dynamic generator -> memory. Used by all legacy reply paths."""
    from app.chatbot.chatbot_service import _get_session_context, _save_session_context
    from app.ai.conversation_aware_response import finalize_assistant_reply

    ctx = dict(session_ctx or _get_session_context(session_id))
    ctx["session_id"] = session_id
    out = await finalize_assistant_reply(
        draft_message=draft,
        intent=intent,
        assistant_mode=assistant_mode,
        response_goal=response_goal,
        entities=entities,
        missing_fields=(classification or {}).get("missing_fields"),
        tool_result={**(tool_result or {}), "message": draft},
        session_context=ctx,
        language=reply_lang,
        sentiment=sentiment or (classification or {}).get("user_sentiment") or "neutral",
        session_id=session_id,
        user_query=user_message,
        classification=classification,
    )
    if out.get("updated_session_context"):
        _save_session_context(session_id, out["updated_session_context"])
    return out


async def _document_qa_response(
    *,
    session_id: str,
    user_message: str,
    reply_lang: str,
    rag_result: dict | None = None,
    no_document: bool = False,
    classification: dict | None = None,
    input_meta: dict | None = None,
) -> dict:
    if no_document or not rag_result:
        draft = "Please upload a PDF or document first, then ask your question."
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=draft,
            response_goal="ask_document_upload",
            intent="document_question",
            assistant_mode="document_qa",
            reply_lang=reply_lang,
            classification=classification,
            tool_result={"suggestions": ["Upload PDF", "Upload text document"]},
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="document_qa",
                suggestions=final.get("suggestions") or ["Upload PDF", "Upload text document"],
                reply_language=reply_lang,
                input_meta=input_meta,
                context_extra={
                    "intent": "document_question",
                    "classification": classification,
                    "should_search_machines": False,
                    "rag_scope": "none",
                    "response_signature": final.get("response_signature"),
                },
            ),
        )

    answer = rag_result.get("answer") or rag_result.get("message") or ""
    final = await _apply_dynamic_response(
        session_id=session_id,
        user_message=user_message,
        draft=answer,
        response_goal="answer_document_question",
        intent="document_question",
        assistant_mode="document_qa",
        reply_lang=reply_lang,
        classification=classification,
        tool_result={
            "message": answer,
            "sources": rag_result.get("sources") or [],
            "suggestions": ["Ask another question", "Show source"],
        },
    )
    reply = final["message"]
    save_conversation(session_id, user_message, reply)
    return success_response(
        message=reply,
        data=_assistant_payload(
            message=reply,
            machines=[],
            assistant_mode="document_qa",
            answer=reply,
            sources=rag_result.get("sources") or [],
            suggestions=final.get("suggestions") or [],
            reply_language=reply_lang,
            input_meta=input_meta,
            context_extra={
                "intent": "document_question",
                "classification": classification,
                "should_search_machines": False,
                "rag_score": rag_result.get("similarity_score"),
                "answer_mode": rag_result.get("answer_mode"),
                "rag_scope": rag_result.get("rag_scope"),
                "response_signature": final.get("response_signature"),
            },
        ),
    )


def _is_document_content_question(message: str) -> bool:
    """Questions about uploaded document content (not general marketplace advice)."""
    text = (message or "").strip()
    if not text:
        return False
    if _references_uploaded_document(text):
        return True
    return bool(re.search(
        r"(?:"
        r"what\s+(?:machines?|equipment)\s+(?:are|is)\s+(?:needed|required|listed|mentioned|recommended)"
        r"|what\s+(?:does|do)\s+(?:the\s+)?(?:document|pdf|upload|file)"
        r"|(?:document|pdf|upload).{0,40}(?:say|mention|about|list)"
        r"|according\s+to\s+(?:the\s+)?(?:document|pdf|upload)"
        r")",
        text,
        re.I,
    ))


def _references_uploaded_document(message: str) -> bool:
    """True only when the user explicitly refers to an uploaded document."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(re.search(
        r"(?:"
        r"uploaded\s+(?:pdf|document|file|doc)"
        r"|(?:the|my|this)\s+(?:document|pdf|file|attachment)"
        r"|document\s+(?:says|mentions|about|content)"
        r"|pdf\s+(?:says|mentions|about)"
        r"|what\s+(?:does|do)\s+(?:the\s+)?(?:document|pdf|file|attachment)"
        r"|according\s+to\s+(?:the\s+)?(?:document|pdf|upload)"
        r")",
        text,
        re.I,
    ))


async def _try_session_document_rag(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    reply_lang: str,
    classification: dict | None,
    input_meta: dict | None,
) -> Optional[dict]:
    """When session has uploaded docs and question is about document content — RAG first."""
    if not rag_has_documents(session_id):
        return None
    if not _is_document_content_question(working_message):
        return None
    rag = ask_rag_question(working_message, session_id=session_id)
    if rag.get("success"):
        print("[assistant_router] session_document_rag")
        return await _document_qa_response(
            session_id=session_id,
            user_message=user_message,
            reply_lang=reply_lang,
            rag_result=rag,
            classification=classification,
            input_meta=input_meta,
        )
    return None


async def _try_canonical_requirement_routing(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    conv_state: dict,
    database,
    reply_lang: str,
    input_meta: dict | None,
) -> dict | None:
    """
    Execute search or clarification from canonical requirement transition decision.
    Router must not independently reconstruct requirement state.
    """
    from app.ai.conversation_state_manager import FLOW_MACHINE_REQUIREMENT
    from app.ai.requirement_state_engine import (
        FIELD_CITY,
        FIELD_PURPOSE_OR_CATEGORY,
        clarification_message_for_field,
        pending_clarification_from_requirement,
        requirement_state_from_conversation,
        suggestions_for_missing_field,
    )
    from app.chatbot.chatbot_service import _get_pending_clarification, _save_pending_clarification
    from app.chatbot.memory import save_conversation
    from app.ai.intent_signals import is_acknowledgement_signal

    if conv_state.get("_is_social_turn"):
        return None

    from app.ai.social_turn_detector import detect_social_turn

    social_ctx = {
        "last_filters": conv_state.get("last_search_filters") or {},
        "collected_fields": conv_state.get("collected_fields") or {},
        "conversation_state": conv_state,
        "greeted": bool(conv_state.get("greeted")),
        "pending": _get_pending_clarification(session_id),
    }
    if detect_social_turn(user_message, social_ctx):
        return None

    decision = conv_state.get("_requirement_decision")
    if decision is None:
        return None

    pending = _get_pending_clarification(session_id)
    if pending and is_acknowledgement_signal(working_message, {"pending": pending}):
        return None

    flow = conv_state.get("active_flow")
    if flow not in (FLOW_MACHINE_REQUIREMENT, "machine_search", "machine_recommendation", None):
        if not getattr(decision, "search_triggered", False):
            return None

    search_triggered = getattr(decision, "search_triggered", False)
    selected = getattr(decision, "selected_action", "")
    next_field = getattr(decision, "next_missing_field", None)

    if search_triggered or selected == "search_machines":
        filters = getattr(decision, "search_filters", None) or {}
        if filters.get("category") or filters.get("city"):
            print(
                f"[assistant_router] canonical_requirement_search "
                f"reason={getattr(decision, 'reason', '')} filters={filters}"
            )
            return await _guarded_machine_search(
                session_id=session_id,
                message=working_message,
                database=database,
                classification={
                    "intent": "machine_search",
                    "should_search_machines": True,
                    "confidence": 0.9,
                    "layer": "rules",
                    "reason": getattr(decision, "reason", "requirement_complete"),
                },
                forced_filters=filters,
            )

    if selected != "ask_missing_field" or not next_field:
        return None

    req = requirement_state_from_conversation(conv_state)
    pending_state = pending_clarification_from_requirement(req, next_field=next_field)
    if pending_state:
        _save_pending_clarification(session_id, pending_state)

    draft = clarification_message_for_field(next_field, req, lang=reply_lang)
    suggestions = suggestions_for_missing_field(next_field, req, database=database)
    goal = "ask_city" if next_field == FIELD_CITY else "collect_machine_requirements"
    collected = conv_state.get("collected_fields") or {}
    filters = {k: v for k, v in {
        "city": collected.get("city"),
        "category": collected.get("category"),
    }.items() if v}

    final = await _apply_dynamic_response(
        session_id=session_id,
        user_message=user_message,
        draft=draft,
        response_goal=goal,
        intent="machine_requirement_collection",
        assistant_mode="clarification",
        reply_lang=reply_lang,
        tool_result={"suggestions": suggestions, "message": draft},
    )
    reply = final["message"]
    save_conversation(session_id, user_message, reply)
    return success_response(
        message=reply,
        data=_assistant_payload(
            message=reply,
            machines=[],
            assistant_mode="clarification",
            suggestions=final.get("suggestions") or suggestions,
            reply_language=reply_lang,
            filters=filters,
            context_extra={
                "intent": "machine_requirement_collection",
                "pending_clarification": pending_state,
                "response_goal": goal,
                "requirement_decision": decision.to_dict() if hasattr(decision, "to_dict") else {},
            },
            input_meta=input_meta,
        ),
    )


async def _try_early_requirement_clarification(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    conv_state: dict,
    reply_lang: str,
    input_meta: dict | None,
    database=None,
) -> dict | None:
    """Delegate to canonical requirement routing — no independent state writes."""
    return await _try_canonical_requirement_routing(
        session_id=session_id,
        user_message=user_message,
        working_message=working_message,
        conv_state=conv_state,
        database=database,
        reply_lang=reply_lang,
        input_meta=input_meta,
    )


async def _try_search_refinement_route(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    gate: dict,
    last_filters: dict,
    reply_lang: str,
    input_meta: dict | None,
    classification: dict | None = None,
    action_decision: dict | None = None,
) -> dict | None:
    """Unified refinement path — cheaper, budget, city switch, brand filter."""
    from app.ai.context_routing_gate import FAMILY_SEARCH_REFINEMENT
    from app.ai.search_refinement_engine import apply_search_refinement, detect_refinement_type
    from app.ai.query_parser import parse_query

    if gate.get("family") != FAMILY_SEARCH_REFINEMENT and not detect_refinement_type(working_message):
        return None

    parsed = parse_query(working_message)
    result = apply_search_refinement(
        working_message,
        last_filters=last_filters,
        parsed=parsed,
        intent_family=gate.get("family"),
    )
    merged = result.get("filters") or {}
    if not merged.get("category") and not merged.get("city"):
        return None

    cls = dict(classification or {})
    cls["should_search_machines"] = True
    cls["intent"] = cls.get("intent") or "machine_search"
    return await _guarded_machine_search(
        session_id=session_id,
        message=working_message,
        database=database,
        classification=cls,
        action_decision={
            **(action_decision or {}),
            "should_search_machines": True,
            "selected_action": "refine_search_filters",
        },
        forced_filters=merged,
    )


async def _route_city_inventory(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    parsed: dict,
    reply_lang: str,
    input_meta: dict,
    classification: dict | None = None,
) -> dict:
    """City-wide inventory — categories available in city from DB."""
    from app.utils.machine_repository import available_categories_in_city
    from app.chatbot.assistant_intelligence import chips_from_categories, city_category_clarification_message

    city = (parsed.get("city") or "").strip().lower()
    if not city:
        reply = (
            "Which city should I check for available machines?"
            if reply_lang == "english"
            else "Kaunsi city me available machines check karun?"
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=reply,
            intent="machine_availability",
            assistant_mode="clarification",
            reply_lang=reply_lang,
            suggestions=["Jaipur", "Delhi", "Mumbai"],
            classification=classification or {},
            input_meta=input_meta,
            response_goal="ask_city",
        )

    available = await available_categories_in_city(database, city)
    if not available:
        reply = (
            f"I could not find machine listings in {city.title()} right now. Try another nearby city."
            if reply_lang == "english"
            else f"{city.title()} me abhi listings nahi mili. Koi aur city try karein."
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=reply,
            intent="machine_availability",
            assistant_mode="no_result",
            reply_lang=reply_lang,
            suggestions=["Search machine", "Contact support"],
            classification=classification or {},
            input_meta=input_meta,
        )

    reply = city_category_clarification_message(
        city, available, lang=reply_lang, max_show=10,
    )
    suggestions = chips_from_categories(available[:6])
    final = await _apply_dynamic_response(
        session_id=session_id,
        user_message=user_message,
        draft=reply,
        response_goal="collect_machine_requirements",
        intent="machine_availability",
        assistant_mode="clarification",
        reply_lang=reply_lang,
        tool_result={"suggestions": suggestions, "message": reply, "categories": available},
    )
    reply = final["message"]
    save_conversation(session_id, user_message, reply)
    return success_response(
        message=reply,
        data=_assistant_payload(
            message=reply,
            machines=[],
            assistant_mode="clarification",
            suggestions=final.get("suggestions") or suggestions,
            reply_language=reply_lang,
            context_extra={
                "intent": "machine_availability",
                "city": city,
                "available_categories": available,
                "response_goal": "collect_machine_requirements",
                "preserve_machine_panel": True,
            },
            input_meta=input_meta,
        ),
    )


async def _route_protected_family(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    gate: dict,
    reply_lang: str,
    input_meta: dict,
) -> dict | None:
    """Short-circuit protected families before enrichment or machine search."""
    from app.ai.context_routing_gate import FAMILY_CITY_INVENTORY, family_to_intent_hint
    from app.ai.query_parser import parse_query

    family = gate.get("family") or ""
    if family == FAMILY_CITY_INVENTORY:
        return await _route_city_inventory(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            database=database,
            parsed=gate.get("features", {}).get("parsed") or parse_query(working_message),
            reply_lang=reply_lang,
            input_meta=input_meta,
        )

    intent_hint = family_to_intent_hint(family)
    if not intent_hint or gate.get("confidence", 0) < 0.82:
        return None

    if intent_hint == "frustration":
        resp = build_response("frustration", lang=reply_lang, message=working_message)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent="frustration",
            assistant_mode="support",
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            input_meta=input_meta,
            response_goal="frustration_recovery",
        )

    resp = build_response(intent_hint, lang=reply_lang, message=working_message)
    return await _support_response(
        session_id=session_id,
        user_message=user_message,
        reply=resp["message"],
        intent=intent_hint,
        assistant_mode=resp.get("assistant_mode", "support"),
        reply_lang=reply_lang,
        suggestions=resp.get("suggestions") or [],
        handover=resp.get("handover"),
        input_meta=input_meta,
    )


async def _route_project_recommendation(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    project_key: str,
    classification: dict,
    input_meta: dict,
    reply_lang: str,
):
    """Continue project recommendation with purpose mapped to categories — no catalog dump."""
    from app.chatbot.chatbot_service import (
        execute_machine_search_turn,
        _save_pending_clarification,
        _save_recommendation_context,
    )

    cats = project_categories(project_key)
    _save_recommendation_context(session_id, None)
    _save_pending_clarification(session_id, None)
    rec_cats = build_recommended_categories(project_key)
    return await _guarded_machine_search(
        session_id=session_id,
        message=working_message,
        database=database,
        classification={
            **classification,
            "intent": "machine_recommendation",
            "should_search_machines": True,
        },
        forced_filters={"category": cats[0]} if cats else None,
        search_flags={
            "list_all": False,
            "project_type": project_key,
            "recommended_categories": rec_cats,
        },
    )


async def _try_continue_pending_clarification(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    reply_lang: str,
    input_meta: dict,
) -> Optional[dict]:
    """Resume recommendation / purpose clarification — never fall through to RAG or generic."""
    from app.chatbot.chatbot_service import (
        _get_pending_clarification,
        _get_recommendation_context,
        execute_machine_search_turn,
        _save_pending_clarification,
        _save_recommendation_context,
    )
    from app.chatbot.assistant_intelligence import (
        is_clarification_answer,
        parse_project_type_option,
        detect_project_type,
        resolve_purpose_key,
        primary_category_for_purpose,
    )

    pending = _get_pending_clarification(session_id)
    rec_ctx = _get_recommendation_context(session_id)

    from app.ai.intent_signals import is_acknowledgement_signal
    from app.chatbot.assistant_intelligence import (
        broad_machine_clarification_message,
        build_broad_machine_request_response,
    )

    if pending and is_acknowledgement_signal(working_message, {"pending": pending}):
        print("[assistant_router] acknowledgement_continue_pending")
        field = pending.get("missing_field") or pending.get("type")
        if field in ("machine_purpose", "purpose"):
            resp = build_broad_machine_request_response(lang=reply_lang)
            draft = (
                "Got it. " + resp["message"]
                if reply_lang == "english"
                else "Theek hai. " + resp["message"]
            )
            goal = "continue_pending_flow"
            suggestions = resp.get("suggestions") or []
        elif field == "project_type":
            draft = recommendation_clarification_warm(lang=reply_lang)
            goal = "recommendation_clarification"
            suggestions = list(PROJECT_TYPE_CHIPS)[:6]
        else:
            draft = broad_machine_clarification_message(lang=reply_lang)
            goal = "continue_pending_flow"
            suggestions = (
                build_broad_machine_request_response(lang=reply_lang).get("suggestions")
                or list(PROJECT_TYPE_CHIPS)[:6]
            )
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=draft,
            response_goal=goal,
            intent="acknowledgement",
            assistant_mode="clarification",
            reply_lang=reply_lang,
            tool_result={"suggestions": suggestions, "message": draft},
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=final.get("suggestions") or suggestions,
                reply_language=reply_lang,
                context_extra={
                    "intent": "acknowledgement",
                    "pending_clarification": pending,
                    "response_goal": goal,
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    classification = {
        "intent": "machine_recommendation",
        "should_search_machines": True,
        "confidence": 0.85,
        "layer": "rules",
        "reason": "pending_clarification_resume",
    }

    awaiting_project = (
        (pending and pending.get("missing_field") == "project_type")
        or (rec_ctx and rec_ctx.get("awaiting_project_type"))
    )
    if awaiting_project:
        project_key = (
            parse_project_type_option(working_message)
            or detect_project_type(working_message)
        )
        if not project_key:
            pk = resolve_purpose_key(working_message)
            if pk in ("digging", "compaction", "lifting", "transport", "drilling", "loading", "concrete"):
                project_key = {
                    "digging": "earthwork",
                    "compaction": "compaction",
                    "lifting": "lifting",
                    "transport": "transport",
                    "drilling": "earthwork",
                    "loading": "earthwork",
                    "concrete": "concrete",
                }.get(pk, pk)
        if project_key:
            print(f"[assistant_router] pending_project_type_resume key={project_key}")
            return await _route_project_recommendation(
                session_id=session_id,
                user_message=user_message,
                working_message=working_message,
                database=database,
                project_key=project_key,
                classification=classification,
                input_meta=input_meta,
                reply_lang=reply_lang,
            )

    if pending and pending.get("missing_field") == "purpose":
        if is_clarification_answer(working_message, pending):
            print("[assistant_router] pending_purpose_resume")
            return await _guarded_machine_search(
                session_id=session_id,
                message=working_message,
                database=database,
                classification={
                    "intent": "machine_search",
                    "should_search_machines": True,
                    "confidence": 0.85,
                    "layer": "rules",
                    "reason": "purpose_clarification_resume",
                },
            )

    if pending and pending.get("missing_field") == "machine_purpose":
        # Canonical requirement engine handles machine_purpose via merge + early_req
        return None

    return None


async def _try_llm_first_route(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    session_ctx: dict,
    last_filters: dict,
    reply_lang: str,
    input_meta: dict,
) -> Optional[dict]:
    """
    LLM-first brain: classify intent → select action → invoke backend tool.
    Returns None to fall through to legacy pipeline when action is defer.
    """
    if not settings.llm_intent_first:
        return None

    from app.chatbot.chatbot_service import (
        _get_pending_clarification,
        _save_pending_clarification,
        _save_session_context,
        execute_machine_search_turn,
    )
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
    from app.ai.llm_intent_classifier import log_intent_debug
    from app.chatbot.assistant_intelligence import build_broad_machine_request_response
    from app.ai.conversation_aware_response import (
        finalize_assistant_reply,
        log_response_debug,
    )

    pending = _get_pending_clarification(session_id)
    router_ctx = {
        "greeted": bool(session_ctx.get("greeted")),
        "user_name": session_ctx.get("user_name"),
        "pending": pending,
        "has_session_documents": rag_has_documents(session_id),
        "has_image_context": bool(session_ctx.get("last_image_context")),
        "last_filters": last_filters,
    }

    classification = await classify_assistant_intent(working_message, router_ctx)

    from app.ai.safe_action_router import resolve_action_decision, action_decision_to_router_action
    action_decision = resolve_action_decision(classification, router_ctx, message=working_message)
    classification = {
        **classification,
        "intent": action_decision.get("intent") or classification.get("intent"),
        "should_search_machines": bool(action_decision.get("should_search_machines")),
        "missing_fields": action_decision.get("missing_fields") or classification.get("missing_fields"),
    }
    action = action_decision_to_router_action(action_decision, classification)
    act = action.get("action")
    tool = action.get("tool") or action_decision.get("allowed_tool") or ""

    try:
        from app.ai.assistant_debug_trace import record_action_decision, record_routing
        record_action_decision(action_decision)
        record_routing(
            selected_action=action_decision.get("selected_action") or act or "",
            tool_used=tool or "none",
            should_search_machines=bool(action_decision.get("should_search_machines")),
        )
    except Exception:
        pass

    log_intent_debug(
        normalized_message=working_message,
        classification=classification,
        action=act,
        tool=tool,
        rag_used=(act == ACTION_DOCUMENT_RAG),
        search_used=(act == ACTION_MACHINE_SEARCH),
    )

    entities = classification.get("entities") or {}
    llm_intent = classification.get("llm_intent") or classification.get("intent")

    async def _finalize(
        draft: str,
        *,
        response_goal: str,
        assistant_mode: str,
        tool_result: dict | None = None,
    ) -> dict:
        out = await finalize_assistant_reply(
            draft_message=draft,
            intent=llm_intent or classification.get("intent") or "unknown",
            assistant_mode=assistant_mode,
            response_goal=response_goal,
            entities=entities,
            missing_fields=classification.get("missing_fields"),
            tool_result=tool_result,
            session_context={
                **session_ctx,
                "session_id": session_id,
                "turn_count": int(session_ctx.get("turn_count") or 0) + 1,
            },
            language=classification.get("language") or reply_lang,
            sentiment=classification.get("user_sentiment") or "neutral",
            session_id=session_id,
            user_query=working_message,
            classification=classification,
        )
        if out.get("updated_session_context"):
            _save_session_context(session_id, out["updated_session_context"])
        log_response_debug(
            normalized_message=working_message,
            classification=classification,
            response=out,
            action=act,
            tool=tool,
        )
        return out

    if act == ACTION_DEFER:
        return None

    if act == ACTION_COMPARISON:
        from app.ai.universal_turn_engine import _comparison_shape
        from app.chatbot.query_parser import parse_query

        parsed = parse_query(working_message)
        cmp_turn = _comparison_shape(working_message, parsed) or {
            "shape": "comparison",
            "brands": action.get("brands") or entities.get("brands") or [],
            "category": action.get("category") or entities.get("category") or entities.get("machine_category"),
            "city": action.get("city") or entities.get("city"),
            "needs_clarification": len(action.get("brands") or entities.get("brands") or []) < 2,
            "original_message": working_message,
        }
        if entities.get("brand") and entities["brand"] not in (cmp_turn.get("brands") or []):
            cmp_turn["brands"] = [entities["brand"], *(cmp_turn.get("brands") or [])]
        return await _respond_comparison_turn(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            database=database,
            turn=cmp_turn,
            last_filters=last_filters,
            reply_lang=reply_lang,
            input_meta=input_meta,
            classification=classification,
        )

    if act == ACTION_CONVERSATIONAL:
        subtype = action.get("subtype") or "greeting"
        if llm_intent == "greeting" and subtype == "greeting":
            first_time = not session_ctx.get("greeted")
            draft = greeting_message(first_time=first_time, lang=reply_lang)
            final = await _finalize(
                draft,
                response_goal="greet_user",
                assistant_mode="greeting",
                tool_result={"suggestions": list(_GREETING_CHIPS)},
            )
            reply = final["message"]
            new_ctx = final.get("updated_session_context") or session_ctx
            new_ctx = {**new_ctx, "greeted": True}
            _save_session_context(session_id, new_ctx)
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode="greeting",
                    suggestions=final.get("suggestions") or list(_GREETING_CHIPS),
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "greeting",
                        "llm_intent": llm_intent,
                        "classification": classification,
                        "response_goal": final.get("response_goal"),
                        "response_variant_id": final.get("response_variant_id"),
                        "layer": classification.get("layer"),
                    },
                    input_meta=input_meta,
                ),
            )

        turn = {
            "subtype": subtype,
            "user_name": entities.get("name") or session_ctx.get("user_name"),
            "original_message": working_message,
            "save_user_name": action.get("save_user_name") or entities.get("name"),
        }
        resp = build_conversational_response(turn, lang=reply_lang)
        goal = action.get("response_goal") or "acknowledge_name"
        final = await _finalize(resp["message"], response_goal=goal, assistant_mode="conversational", tool_result=resp)
        reply = final["message"]
        new_ctx = final.get("updated_session_context") or {**session_ctx, "greeted": True}
        if resp.get("save_user_name"):
            new_ctx["user_name"] = resp["save_user_name"]
        new_ctx["greeted"] = True
        _save_session_context(session_id, new_ctx)
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="conversational",
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": llm_intent,
                    "classification": classification,
                    "user_name": new_ctx.get("user_name"),
                    "response_goal": final.get("response_goal"),
                    "response_variant_id": final.get("response_variant_id"),
                    "layer": classification.get("layer"),
                },
                input_meta=input_meta,
            ),
        )

    if act in (ACTION_BROAD_CLARIFY, ACTION_CLARIFY):
        resp = build_broad_machine_request_response(lang=reply_lang)
        goal = action.get("response_goal") or "collect_machine_requirements"
        if act == ACTION_CLARIFY and action.get("subtype") == "unknown":
            resp["message"] = (
                "I'm not fully sure which machine you need. "
                "Can you tell me the work type and city?"
            )
            goal = "continue_followup"
        final = await _finalize(resp["message"], response_goal=goal, assistant_mode="clarification", tool_result=resp)
        pending_state = resp["pending"]
        _save_pending_clarification(session_id, pending_state)
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": llm_intent or "broad_machine_request",
                    "classification": classification,
                    "pending_clarification": pending_state,
                    "response_goal": final.get("response_goal"),
                    "response_variant_id": final.get("response_variant_id"),
                    "layer": classification.get("layer"),
                },
                input_meta=input_meta,
            ),
        )

    if act == ACTION_DOCUMENT_RAG:
        if not rag_has_documents(session_id):
            draft = "Please upload a PDF or document first, then ask your question."
            final = await _finalize(
                draft,
                response_goal="ask_document_upload",
                assistant_mode="document_qa",
                tool_result={"suggestions": ["Upload PDF", "Upload text document"]},
            )
            return await _support_response(
                session_id=session_id,
                user_message=user_message,
                reply=final["message"],
                intent="document_question",
                assistant_mode="document_qa",
                reply_lang=reply_lang,
                suggestions=final.get("suggestions") or ["Upload PDF", "Upload text document"],
                classification=classification,
                input_meta=input_meta,
                extra={
                    "rag_scope": "none",
                    "response_variant_id": final.get("response_variant_id"),
                    "response_goal": final.get("response_goal"),
                },
            )
        rag = ask_rag_question(working_message, session_id=session_id)
        if rag.get("success"):
            answer = rag.get("answer") or rag.get("message") or ""
            final = await _finalize(
                answer,
                response_goal="answer_document_question",
                assistant_mode="document_qa",
                tool_result={
                    "message": answer,
                    "sources": rag.get("sources") or [],
                    "suggestions": ["Ask another question", "Show source"],
                },
            )
            save_conversation(session_id, user_message, final["message"])
            return success_response(
                message=final["message"],
                data=_assistant_payload(
                    message=final["message"],
                    machines=[],
                    assistant_mode="document_qa",
                    answer=final["message"],
                    sources=rag.get("sources") or [],
                    suggestions=final.get("suggestions") or [],
                    reply_language=reply_lang,
                    input_meta=input_meta,
                    context_extra={
                        "intent": "document_question",
                        "classification": classification,
                        "should_search_machines": False,
                        "rag_score": rag.get("similarity_score"),
                        "answer_mode": rag.get("answer_mode"),
                        "response_variant_id": final.get("response_variant_id"),
                        "response_goal": final.get("response_goal"),
                    },
                ),
            )
        draft = "Please upload a PDF or document first, then ask your question."
        final = await _finalize(
            draft,
            response_goal="ask_document_upload",
            assistant_mode="document_qa",
            tool_result={"suggestions": ["Upload PDF", "Upload text document"]},
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=final["message"],
            intent="document_question",
            assistant_mode="document_qa",
            reply_lang=reply_lang,
            suggestions=final.get("suggestions") or ["Upload PDF", "Upload text document"],
            classification=classification,
            input_meta=input_meta,
            extra={
                "rag_scope": "none",
                "response_variant_id": final.get("response_variant_id"),
                "response_goal": final.get("response_goal"),
            },
        )

    if act == ACTION_OUT_OF_SCOPE:
        resp = build_response("out_of_scope", lang=reply_lang, message=working_message)
        final = await _finalize(resp["message"], response_goal="out_of_scope_boundary", assistant_mode="out_of_scope", tool_result=resp)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=final["message"],
            intent="out_of_scope",
            assistant_mode="out_of_scope",
            reply_lang=reply_lang,
            suggestions=final.get("suggestions") or resp.get("suggestions") or [],
            classification=classification,
            entities=entities,
            input_meta=input_meta,
            extra={"response_variant_id": final.get("response_variant_id"), "response_goal": final.get("response_goal")},
        )

    if act == ACTION_SUPPORT:
        intent = action.get("intent") or classification.get("intent") or "support_request"
        resp = build_response(
            intent,
            entities=entities,
            lang=reply_lang,
            message=working_message,
        )
        goal = classification.get("response_goal") or (
            "collect_transaction_id" if intent == "payment_issue" else "collect_booking_id"
        )
        final = await _finalize(resp["message"], response_goal=goal, assistant_mode=resp.get("assistant_mode", "support"), tool_result=resp)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=final["message"],
            intent=intent,
            assistant_mode=resp.get("assistant_mode", "support"),
            reply_lang=reply_lang,
            suggestions=final.get("suggestions") or resp.get("suggestions") or [],
            handover=resp.get("handover"),
            classification=classification,
            entities=entities,
            input_meta=input_meta,
            extra={"response_variant_id": final.get("response_variant_id"), "response_goal": final.get("response_goal")},
        )

    if act == ACTION_IMAGE_FOLLOWUP:
        from app.chatbot.image_context_memory import get_image_context

        if not get_image_context(session_id):
            draft = (
                "I could not find a recent machine image in this session. "
                "Please upload a photo or tell me the machine type and city."
            )
            final = await _finalize(
                draft,
                response_goal="ask_image_clarification",
                assistant_mode="image_clarification",
            )
            return await _support_response(
                session_id=session_id,
                user_message=user_message,
                reply=final["message"],
                intent="image_clarification",
                assistant_mode="image_clarification",
                reply_lang=reply_lang,
                suggestions=final.get("suggestions") or [],
                classification=classification,
                input_meta=input_meta,
                extra={
                    "response_variant_id": final.get("response_variant_id"),
                    "response_goal": final.get("response_goal"),
                },
            )
        return None  # image context exists — legacy pipeline enriches search

    if act == ACTION_RECOMMENDATION:
        return None  # use existing project recommendation flow

    if act == ACTION_MACHINE_SEARCH:
        filters = action.get("filters") or {}
        forced = {k: v for k, v in filters.items() if v is not None}
        return await _guarded_machine_search(
            session_id=session_id,
            message=working_message,
            database=database,
            classification={
                **classification,
                "intent": "machine_search",
                "should_search_machines": True,
                "layer": classification.get("layer") or "llm",
                "reason": "llm_action_search",
            },
            forced_filters=forced if forced else None,
        )

    return None


def _document_query_allowed(intent: str, message: str) -> bool:
    """RAG only for explicit document Q&A — never for greeting/search/recommendation."""
    if intent == "document_question":
        return True
    return _references_uploaded_document(message)


async def _support_response(
    *,
    session_id: str,
    user_message: str,
    reply: str,
    intent: str,
    assistant_mode: str,
    reply_lang: str,
    suggestions: list | None = None,
    handover: dict | None = None,
    classification: dict | None = None,
    entities: dict | None = None,
    extra: dict | None = None,
    input_meta: dict | None = None,
    response_goal: str = "",
) -> dict:
    from app.chatbot.chatbot_service import _get_session_context, _save_session_context
    from app.ai.conversation_aware_response import finalize_assistant_reply
    from app.ai.response_plan import response_goal_for_intent

    session_ctx = _get_session_context(session_id)
    goal = response_goal or response_goal_for_intent(intent, assistant_mode=assistant_mode)
    final_extra = dict(extra or {})
    tool_payload: dict = {"message": reply, "suggestions": suggestions, "handover": handover}
    if extra:
        for key in ("brands", "categories", "machines"):
            if extra.get(key):
                tool_payload[key] = extra[key]
        if extra.get("selected_action"):
            tool_payload["selected_action"] = extra["selected_action"]

    try:
        final = await finalize_assistant_reply(
            draft_message=reply,
            intent=intent,
            assistant_mode=assistant_mode,
            response_goal=goal,
            entities=entities,
            missing_fields=(classification or {}).get("missing_fields"),
            tool_result=tool_payload,
            session_context={**session_ctx, "session_id": session_id},
            language=reply_lang,
            sentiment=(classification or {}).get("user_sentiment") or "neutral",
            session_id=session_id,
            user_query=user_message,
            classification=classification,
        )
    except Exception as exc:
        print(f"[support_response] finalize_failed -> draft: {exc}")
        final = {
            "message": reply,
            "suggestions": suggestions or [],
            "fallback_used": True,
            "llm_generated": False,
        }

    reply = final["message"]
    suggestions = final.get("suggestions") or suggestions
    final_extra.update({
        "response_goal": goal,
        "response_variant_id": final.get("response_variant_id"),
        "response_signature": final.get("response_signature"),
        "llm_generated": final.get("llm_generated"),
        "fallback_used": final.get("fallback_used"),
        "gateway_used": True,
    })
    if final.get("updated_session_context"):
        _save_session_context(session_id, final["updated_session_context"])

    save_conversation(session_id, user_message, reply)
    ctx = {
        "intent": intent,
        "classification": classification,
        "entities": entities or {},
        "should_search_machines": False,
        **final_extra,
    }
    if classification:
        ctx["confidence"] = classification.get("confidence")
    return success_response(
        message=reply,
        data=_assistant_payload(
            message=reply,
            machines=[],
            assistant_mode=assistant_mode,
            suggestions=suggestions or [],
            handover=handover,
            reply_language=reply_lang,
            context_extra=ctx,
            input_meta=input_meta,
        ),
    )


async def _route_brand_inventory_action(
    *,
    session_id: str,
    user_message: str,
    database,
    action_decision: dict,
    classification: dict,
    entities: dict,
    last_filters: dict,
    reply_lang: str,
    input_meta: dict | None,
) -> dict:
    """Execute allowed brand inventory action from permission matrix decision."""
    from app.ai.brand_inventory_service import build_brand_inventory_reply
    from app.chatbot.chatbot_service import execute_machine_search_turn

    selected = action_decision.get("selected_action") or "ask_brand_category"
    cat = (
        entities.get("machine_type")
        or entities.get("category")
        or last_filters.get("category")
    )
    brands = entities.get("brands") or []
    brand = entities.get("brand") or (brands[0] if brands else None)
    city = entities.get("city") or last_filters.get("city")

    if selected == "check_brand_availability" and cat and brand:
        forced = {"category": cat, "brand": brand}
        if city:
            forced["city"] = city
        return await _guarded_machine_search(
            session_id=session_id,
            message=user_message,
            database=database,
            classification={
                **classification,
                "should_search_machines": True,
                "intent": "machine_brand_query",
            },
            forced_filters=forced,
            search_flags={"list_all": True},
        )

    payload = await build_brand_inventory_reply(
        database,
        selected_action=selected,
        category=cat,
        brand=brand,
        city=city,
        lang=reply_lang,
    )
    goal_map = {
        "query_brands_by_category": "show_brand_inventory",
        "list_categories_for_brand": "show_brand_inventory",
        "check_brand_availability": "check_brand_availability",
        "ask_brand_category": "collect_machine_requirements",
    }
    return await _support_response(
        session_id=session_id,
        user_message=user_message,
        reply=payload["message"],
        intent="machine_brand_query",
        assistant_mode=payload.get("assistant_mode") or action_decision.get("assistant_mode") or "brand_inventory",
        reply_lang=reply_lang,
        suggestions=payload.get("suggestions") or [],
        classification=classification,
        entities=entities,
        input_meta=input_meta,
        response_goal=goal_map.get(selected, "show_brand_inventory"),
        extra={
            "brands": payload.get("brands"),
            "categories": payload.get("categories"),
            "action_decision": action_decision,
            "selected_action": selected,
        },
    )


async def _guarded_machine_search(
    *,
    session_id: str,
    message: str,
    database,
    classification: dict,
    action_decision: dict | None = None,
    forced_filters: dict | None = None,
    search_flags: dict | None = None,
) -> dict:
    """Run machine search only when permission matrix allows mongodb_search."""
    from app.ai.safe_action_router import validate_tool_call
    from app.ai.tool_permission_matrix import TOOL_MONGODB_SEARCH
    from app.chatbot.chatbot_service import execute_machine_search_turn

    intent = classification.get("intent") or "unknown"
    ok, block_reason = validate_tool_call(intent, TOOL_MONGODB_SEARCH)
    if action_decision and not action_decision.get("should_search_machines"):
        ok = False
        block_reason = action_decision.get("reason") or block_reason
    if not ok:
        reply = (
            "I need a bit more detail before I search listings. "
            "Which machine type and city should I use?"
        )
        return await _support_response(
            session_id=session_id,
            user_message=message,
            reply=reply,
            intent=intent,
            assistant_mode="clarification",
            reply_lang=detect_query_language(message),
            suggestions=["Excavator in Jaipur", "Road Roller", "Contact support"],
            classification=classification,
            extra={"permission_block_reason": block_reason, "action_decision": action_decision},
        )

    from app.ai.conversation_state_manager import get_current_state

    state = get_current_state()
    if state and state.get("_recovery_followup_filters"):
        follow = dict(state["_recovery_followup_filters"])
        follow.pop("action", None)
        recovery_base = (state.get("last_no_result_context") or {}).get("last_no_result_filters") or {}
        forced_filters = {**(forced_filters or {}), **recovery_base, **follow}

    enriched_cls = {**(classification or {}), "action_decision": action_decision or {}}
    return await execute_machine_search_turn(
        session_id,
        message,
        database,
        classification=enriched_cls,
        forced_filters=forced_filters,
        search_flags=search_flags,
    )


async def handle_assistant_message(
    session_id: str,
    user_message: str,
    database,
    context: Optional[dict] = None,
) -> dict:
    """
    Central entry: classify intent, route to support or machine search.
    """
    from app.chatbot.chatbot_service import (
        _get_last_filters,
        _get_pending_clarification,
        _get_session_context,
        _save_session_context,
    )

    session_id = (session_id or "").strip()
    user_message = (user_message or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    if not user_message:
        return success_response(
            message="Please type a message.",
            data=_assistant_payload(
                message="Please type a message.",
                machines=[],
                assistant_mode="clarification",
            ),
        )

    norm = await normalize_user_message_async(user_message)
    working_message = norm.corrected
    try:
        from app.ai.assistant_debug_trace import record_normalized_message
        record_normalized_message(working_message)
    except Exception:
        pass
    input_meta = build_chat_input_metadata(
        original_message=user_message,
        normalized_message=working_message,
    )
    if norm.corrections:
        input_meta["corrections"] = norm.corrections
    if norm.corrections:
        print(
            "[assistant_router]",
            f"normalized layer={norm.layer}",
            f"corrections={norm.corrections}",
        )

    last_filters = _get_last_filters(session_id)
    session_ctx = _get_session_context(session_id)
    greeted = bool(session_ctx.get("greeted"))
    result_ctx = get_result_context(session_ctx)
    reply_lang = detect_query_language(working_message)

    from app.ai.conversation_state_manager import (
        begin_turn,
        get_current_state,
        merge_incoming_turn,
        state_to_router_context,
    )
    from app.ai.query_parser import parse_query

    conv_state = get_current_state()
    if conv_state is None:
        conv_state = begin_turn(session_id)
    parsed_msg = parse_query(working_message)

    # --- Suggestion chip → executable message (context-aware) -----------------
    from app.ai.suggestion_action_resolver import is_suggestion_chip, resolve_suggestion_chip

    chip_route: dict[str, Any] | None = None
    if is_suggestion_chip(working_message):
        chip_ctx = {
            **session_ctx,
            "session_id": session_id,
            "conversation_state": conv_state,
            "last_search_filters": last_filters,
        }
        chip_route = resolve_suggestion_chip(working_message, session_ctx=chip_ctx)
        if chip_route.get("action") == "send_message" and chip_route.get("message"):
            working_message = chip_route["message"]
            input_meta["suggestion_chip"] = chip_route.get("chip")
            input_meta["from_suggestion_chip"] = True
            if chip_route.get("intent_hint"):
                input_meta["intent_hint"] = chip_route["intent_hint"]
            parsed_msg = parse_query(working_message)
            reply_lang = detect_query_language(working_message)

    # --- Image context follow-up (chips, city, availability) before domain gateway ---
    from app.ai.image_chat_followup import try_image_chat_followup

    img_followup = await try_image_chat_followup(
        session_id=session_id,
        user_message=user_message,
        working_message=working_message,
        database=database,
        reply_lang=reply_lang,
        session_ctx=session_ctx,
        conv_state=conv_state,
        input_meta=input_meta,
        assistant_router_module=sys.modules[__name__],
    )
    if img_followup is not None:
        from app.chatbot.memory import save_conversation
        from app.ai.conversation_state_manager import apply_turn_result, save_conversation_state

        save_conversation(session_id, user_message, img_followup.get("message") or "")
        if conv_state:
            apply_turn_result(
                conv_state,
                user_message=user_message,
                response=img_followup,
                intent=((img_followup.get("data") or {}).get("context") or {}).get("intent"),
            )
            save_conversation_state(conv_state)
        return img_followup

    active_flow = (conv_state or {}).get("active_flow")
    classification: dict = {}

    from app.ai.context_routing_gate import (
        evaluate_routing_gate,
        sanitize_router_context,
        family_blocks_universal_early_exit,
    )
    from app.ai.assistant_debug_trace import record_context_routing

    gate = evaluate_routing_gate(
        working_message,
        active_flow=active_flow,
        parsed=parsed_msg,
    )
    record_context_routing({
        "current_intent_family": gate.get("family"),
        "context_eligibility_decision": gate.get("reason"),
        "previous_context_used": not gate.get("block_previous_search_context"),
        "previous_context_blocked_reason": gate.get("reason") if gate.get("block_previous_search_context") else "",
        "active_flow_before": active_flow or "",
    })

    # Always merge session state BEFORE domain gateway — early domain exits must not skip memory
    from app.ai.semantic_turn_gateway import (
        is_short_context_fragment,
        resolve_fragment_context,
        understand_turn_semantically,
    )
    from app.ai.response_mode_gateway import resolve_response_mode

    semantic_ctx = {
        **session_ctx,
        "conversation_state": conv_state,
        "last_search_filters": last_filters,
        "greeted": greeted,
        "user_name": session_ctx.get("user_name"),
    }
    semantic = await understand_turn_semantically(
        working_message,
        parsed=parsed_msg,
        context=semantic_ctx,
    )
    if conv_state is not None:
        conv_state["_semantic_understanding"] = semantic.to_dict()
        conv_state["last_user_goal"] = semantic.primary_intent
        if semantic.should_recommend:
            from app.ai.domain_recommendation_engine import build_recommendation_context
            conv_state["last_recommendation_context"] = build_recommendation_context(
                working_message, parsed=semantic.entities, conv_state=conv_state,
            )
        if semantic.should_compare:
            cmp_brands = semantic.entities.get("brands") or []
            conv_state["last_comparison_context"] = {
                "brands": cmp_brands,
                "category": semantic.entities.get("category"),
                "city": semantic.entities.get("city"),
            }
        if semantic.should_search:
            conv_state["last_search_filters"] = {
                **(conv_state.get("last_search_filters") or {}),
                **{k: v for k, v in semantic.entities.items() if v is not None and k in (
                    "category", "city", "max_price", "brand", "listing_type", "purpose_key",
                )},
            }

    mode_decision = resolve_response_mode(semantic)
    if semantic.is_fragment or is_short_context_fragment(working_message, parsed=parsed_msg):
        frag = resolve_fragment_context(
            working_message,
            conv_state=conv_state,
            last_filters=last_filters,
            parsed=semantic.entities,
        )
        parsed_msg = frag["parsed"]
        working_message = semantic.normalized_message or working_message
        if conv_state and frag.get("merged_from_session"):
            conv_state["_fragment_merge"] = frag["context_reference"]

    if conv_state:
        merge_incoming_turn(
            conv_state,
            message=working_message,
            parsed=parsed_msg,
        )
        partial_ctx = state_to_router_context(conv_state)
        if partial_ctx.get("last_filters"):
            last_filters = {**last_filters, **partial_ctx["last_filters"]}

    # --- Semantic orchestrator (authoritative when confident) -------------------
    from app.ai.semantic_response_orchestrator import try_semantic_orchestrated_route

    semantic_route = await try_semantic_orchestrated_route(
        session_id=session_id,
        user_message=user_message,
        working_message=working_message,
        semantic=semantic,
        mode_decision=mode_decision,
        parsed=parsed_msg,
        reply_lang=reply_lang,
        input_meta=input_meta,
        database=database,
        conv_state=conv_state,
        assistant_router_module=sys.modules[__name__],
    )
    if semantic_route is not None:
        if conv_state:
            from app.ai.conversation_state_manager import apply_turn_result
            from app.ai.session_requirement_context import sync_turn_context_to_collected

            apply_turn_result(
                conv_state,
                user_message=user_message,
                response=semantic_route,
                intent=(semantic_route.get("data") or {}).get("context", {}).get("intent"),
            )
            sync_turn_context_to_collected(conv_state)
        return semantic_route

    # --- Phase 12: Domain Intelligence Gateway (shadow / hybrid) ----------------
    from app.ai.domain_intelligence_gateway import interpret_domain_message
    from app.ai.domain_response_orchestrator import (
        should_skip_broad_machine_route,
        try_domain_orchestrated_route,
    )
    from app.chatbot.chatbot_service import _get_pending_clarification

    domain_context = {
        **session_ctx,
        "conversation_state": conv_state,
        "collected_fields": (conv_state or {}).get("collected_fields"),
        "pending_fields": (conv_state or {}).get("pending_fields"),
        "active_flow": (conv_state or {}).get("active_flow"),
        "last_search_filters": last_filters,
        "pending": _get_pending_clarification(session_id),
        "greeted": greeted,
    }
    domain_interp = await interpret_domain_message(
        working_message,
        parsed=parsed_msg,
        context=domain_context,
        gate=gate,
    )
    if conv_state is not None:
        conv_state["_domain_interpretation"] = domain_interp.to_dict()

    from app.core.config import settings as _settings
    if _settings.domain_intelligence_hybrid:
        domain_route = await try_domain_orchestrated_route(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            interp=domain_interp,
            reply_lang=reply_lang,
            input_meta=input_meta,
            database=database,
            conv_state=conv_state,
            assistant_router_module=sys.modules[__name__],
        )
        if domain_route is not None:
            if conv_state:
                from app.ai.conversation_state_manager import apply_turn_result
                apply_turn_result(
                    conv_state,
                    user_message=user_message,
                    response=domain_route,
                    intent=(domain_route.get("data") or {}).get("context", {}).get("intent"),
                )
            return domain_route

    _skip_broad_machine = should_skip_broad_machine_route(domain_interp)

    protected = await _route_protected_family(
        session_id=session_id,
        user_message=user_message,
        working_message=working_message,
        database=database,
        gate=gate,
        reply_lang=reply_lang,
        input_meta=input_meta,
    )
    if protected is not None and gate.get("family") != "machine_comparison":
        if conv_state:
            from app.ai.conversation_state_manager import apply_turn_result
            apply_turn_result(
                conv_state,
                user_message=user_message,
                response=protected,
                intent=(protected.get("data") or {}).get("context", {}).get("intent"),
            )
        return protected

    if conv_state:
        early_req = await _try_early_requirement_clarification(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            conv_state=conv_state,
            reply_lang=reply_lang,
            input_meta=input_meta,
            database=database,
        )
        if early_req is not None:
            from app.ai.conversation_state_manager import apply_turn_result
            apply_turn_result(
                conv_state,
                user_message=user_message,
                response=early_req,
                intent="machine_requirement_collection",
            )
            return early_req

    if gate.get("block_previous_search_context"):
        last_filters = {}
        result_ctx = {}

    # --- Resume pending clarification before any RAG or re-classification ------
    if gate.get("allow_pending_machine_resume"):
        pending_route = await _try_continue_pending_clarification(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            database=database,
            reply_lang=reply_lang,
            input_meta=input_meta,
        )
        if pending_route is not None:
            return pending_route
    else:
        pending_route = None

    # --- LLM-first brain (primary when AI_INTENT_MODE=llm_first) ---------------
    llm_route = await _try_llm_first_route(
        session_id=session_id,
        user_message=user_message,
        working_message=working_message,
        database=database,
        session_ctx=session_ctx,
        last_filters=last_filters,
        reply_lang=reply_lang,
        input_meta=input_meta,
    )
    if llm_route is not None:
        return llm_route

    # --- Session document RAG (rules mode only — LLM routes document_question) -
    if not settings.llm_intent_first:
        doc_rag = await _try_session_document_rag(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            reply_lang=reply_lang,
            classification=None,
            input_meta=input_meta,
        )
        if doc_rag is not None:
            return doc_rag

    # --- Vague machine request → clarify first (rules mode only) -------------
    _collected = (conv_state or {}).get("collected_fields") if conv_state else {}
    if (
        not settings.llm_intent_first
        and is_broad_vague_query(working_message, session_collected=_collected)
        and not _skip_broad_machine
    ):
        from app.chatbot.chatbot_service import _save_pending_clarification
        from app.chatbot.assistant_intelligence import build_broad_machine_request_response

        print("[assistant_router] broad_machine_clarify")
        try:
            from app.ai.assistant_debug_trace import record_routing
            record_routing(
                selected_action="broad_clarify",
                tool_used="none",
                should_search_machines=False,
            )
        except Exception:
            pass
        resp = build_broad_machine_request_response(lang=reply_lang)
        pending_state = resp["pending"]
        _save_pending_clarification(session_id, pending_state)
        parsed_bm = parse_query(working_message)
        profile_hints = session_ctx.get("user_profile_hints") or {}
        from app.ai.user_memory_profile import profile_aware_clarification_message

        draft = (
            profile_aware_clarification_message(
                lang=reply_lang,
                category=parsed_bm.get("category"),
                profile_hints=profile_hints,
            )
            or resp["message"]
        )
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=draft,
            response_goal="collect_machine_requirements",
            intent="broad_machine_request",
            assistant_mode="clarification",
            reply_lang=reply_lang,
            session_ctx=session_ctx,
            tool_result=resp,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "machine_purpose_clarification",
                    "pending_clarification": pending_state,
                    "corrections": norm.corrections or None,
                    "response_signature": final.get("response_signature"),
                },
                input_meta=input_meta,
            ),
        )

    # --- Universal turn engine (ONE classifier — all shapes) ----------------
    universal = await classify_universal_turn_async(
        working_message,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
        last_filters=last_filters,
        greeted=greeted,
    )
    try:
        from app.ai.assistant_debug_trace import record_universal_classifier_called
        record_universal_classifier_called()
    except Exception:
        pass
    print(
        "[assistant_router]",
        f"universal_shape={universal.get('shape')}",
        f"layer={universal.get('layer', 'rules')}",
        f"subtype={universal.get('subtype')}",
        f"reason={universal.get('reason')}",
    )

    if universal.get("shape") == "knowledge_answer":
        from app.ai.knowledge_query_engine import build_knowledge_answer

        resp = await build_knowledge_answer(
            universal,
            user_message=working_message,
            lang=reply_lang,
        )
        goal = resp.get("response_goal") or "domain_knowledge_answer"
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal=goal,
            intent=universal.get("kind") or "domain_knowledge",
            assistant_mode=resp.get("assistant_mode", "advisory"),
            reply_lang=reply_lang,
            session_ctx=session_ctx,
            tool_result=resp,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        if conv_state is not None:
            from app.ai.suggestion_action_resolver import save_knowledge_context
            save_knowledge_context(conv_state, universal)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode=resp.get("assistant_mode", "advisory"),
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": universal.get("kind") or "domain_knowledge",
                    "preserve_machine_panel": True,
                    "universal": universal,
                    "response_goal": goal,
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
            ),
        )

    if universal.get("shape") == "conversational":
        resp = build_conversational_response(
            {**universal, "greeted": greeted},
            lang=reply_lang,
        )
        subtype = universal.get("subtype") or "conversational"
        goal_map = {
            "thanks": "respond_gratitude",
            "appreciation": "respond_appreciation",
            "satisfaction": "respond_satisfaction",
            "wellbeing": "respond_wellbeing",
            "wellbeing_reciprocal": "respond_wellbeing",
            "user_state": "respond_wellbeing",
            "polite_social": "respond_appreciation",
            "name_intro": "acknowledge_name",
            "assistant_identity": "assistant_identity",
            "greeting": "greet_user",
        }
        goal = goal_map.get(subtype, "respond_conversational")
        assistant_mode = "greeting" if subtype == "greeting" else "conversational"
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal=goal,
            intent=subtype,
            assistant_mode=assistant_mode,
            reply_lang=reply_lang,
            session_ctx=session_ctx,
            tool_result=resp,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        new_ctx = {**session_ctx, "greeted": True}
        if resp.get("save_user_name"):
            new_ctx["user_name"] = resp["save_user_name"]
        _save_session_context(session_id, new_ctx)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode=assistant_mode,
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": subtype,
                    "user_name": new_ctx.get("user_name"),
                    "universal": universal,
                    "corrections": norm.corrections or None,
                    "ai_fallback_used": universal.get("ai_fallback_used"),
                    "response_signature": final.get("response_signature"),
                },
            ),
        )

    if universal.get("shape") == "selected_machine":
        from app.ai.selected_machine_context import build_selected_machine_response

        action = universal.get("action") or "want_booking"
        machine = universal.get("machine") or session_ctx.get("selected_machine") or {}
        resp = build_selected_machine_response(
            machine=machine,
            action=action,
            lang=reply_lang,
        )
        goal = resp.get("response_goal") or "booking_guidance"
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal=goal,
            intent="contact_owner" if action == "contact_owner" else "booking_guidance",
            assistant_mode=resp.get("assistant_mode", "booking_guidance"),
            reply_lang=reply_lang,
            session_ctx=session_ctx,
            tool_result={
                "message": resp["message"],
                "machines": resp.get("machines") or [],
                "suggestions": resp.get("suggestions") or [],
                "preserve_machine_panel": True,
            },
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        panel_machines = resp.get("machines") or ([machine] if machine else [])
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=panel_machines,
                assistant_mode=resp.get("assistant_mode", "booking_guidance"),
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "selected_machine",
                    "preserve_machine_panel": True,
                    "referenced_machine": (machine or {}).get("name"),
                    "universal": universal,
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
            ),
        )

    if universal.get("shape") == "comparison":
        return await _respond_comparison_turn(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            database=database,
            turn=universal,
            last_filters=last_filters,
            reply_lang=reply_lang,
            input_meta=input_meta,
        )

    if universal.get("shape") == "machine_attribute":
        resp = build_machine_detail_response(universal, lang=reply_lang)
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal="ask_followup_context",
            intent="machine_detail",
            assistant_mode=resp.get("assistant_mode", "machine_detail"),
            reply_lang=reply_lang,
            tool_result={
                "message": resp["message"],
                "suggestions": resp.get("suggestions") or [],
                "preserve_machine_panel": resp.get("preserve_machines", True),
            },
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        panel_machines = (
            (result_ctx.get("last_machines") or [])
            if resp.get("preserve_machines")
            else []
        )
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=panel_machines,
                assistant_mode=resp.get("assistant_mode", "machine_detail"),
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "machine_detail",
                    "preserve_machine_panel": resp.get("preserve_machines", True),
                    "referenced_machine": (universal.get("machine") or {}).get("name"),
                    "universal": universal,
                    "normalization": norm.to_dict() if norm.corrections else None,
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
            ),
        )

    if universal.get("shape") == "contextual_refine":
        refine_filters = universal.get("filters") or last_filters
        resp = await build_contextual_refine_response(
            database,
            universal,
            result_ctx=result_ctx,
            lang=reply_lang,
        )
        goal = "show_machine_results" if resp.get("machines") else "ask_followup_context"
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal=goal,
            intent="contextual_refine",
            assistant_mode=resp.get("assistant_mode", "search"),
            reply_lang=reply_lang,
            tool_result={
                "message": resp["message"],
                "machines": resp.get("machines") or [],
                "suggestions": resp.get("suggestions") or [],
                "preserve_machine_panel": not resp.get("preserve_machines", True) or bool(resp.get("machines")),
            },
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        machines = resp.get("machines") or []
        if machines and not resp.get("preserve_machines"):
            from app.chatbot.chatbot_service import _persist_last_results
            _persist_last_results(session_id, machines, refine_filters)
        from app.ai.turn_models import build_turn_result_payload
        return success_response(
            message=reply,
            data=build_turn_result_payload(
                message=reply,
                machines=machines if not resp.get("preserve_machines") else (result_ctx.get("last_machines") or []),
                assistant_mode=resp.get("assistant_mode", "search"),
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                filters=refine_filters,
                context_extra={
                    "intent": "contextual_refine",
                    "universal": universal,
                    "response_goal": goal,
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
                payload_builder=_assistant_payload,
                reply_language=reply_lang,
            ),
        )

    # --- Session advisory / purpose (before marketplace intent) ---------------
    ctx_turn = analyze_contextual_turn(
        working_message,
        last_filters=last_filters,
        result_ctx=result_ctx,
    )

    from app.chatbot.image_context_memory import is_image_follow_up

    if is_image_follow_up(working_message, session_id):
        ctx_turn = {
            **ctx_turn,
            "turn_type": "none",
            "search_filters": None,
            "purpose_keys": [],
        }

    print(
        "[assistant_router]",
        f"contextual_turn={ctx_turn.get('turn_type')}",
        f"purpose={ctx_turn.get('purpose_key')}",
        f"has_last_machines={bool(result_ctx.get('last_machines'))}",
    )

    if ctx_turn.get("turn_type") == "multi_purpose_advisory":
        city = last_filters.get("city") or (result_ctx.get("filters") or {}).get("city")
        resp = await build_multi_purpose_advisory(
            database,
            purposes=ctx_turn.get("purpose_keys") or [],
            city=city,
            lang=reply_lang,
        )
        goal = "show_machine_results" if resp.get("machines") else "collect_machine_requirements"
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal=goal,
            intent="multi_purpose_advisory",
            assistant_mode=resp.get("assistant_mode", "recommendation"),
            reply_lang=reply_lang,
            tool_result={
                "message": resp["message"],
                "machines": resp.get("machines") or [],
                "suggestions": resp.get("suggestions") or [],
            },
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        from app.chatbot.chatbot_service import _persist_last_results

        machines = resp.get("machines") or []
        if machines:
            _persist_last_results(session_id, machines, {"city": city})
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=machines,
                assistant_mode=resp.get("assistant_mode", "recommendation"),
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "multi_purpose_advisory",
                    "purposes": ctx_turn.get("purpose_keys"),
                    "city": city,
                    "response_goal": goal,
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
            ),
        )

    if ctx_turn.get("turn_type") == "advisory_clarification":
        from app.ai.intent_signals import is_recommendation_broad_signal
        from app.chatbot.chatbot_service import (
            _save_pending_clarification,
            _save_recommendation_context,
        )
        from app.chatbot.assistant_intelligence import (
            build_purpose_pending,
            project_type_pending_state,
        )

        if is_recommendation_broad_signal(working_message):
            _save_recommendation_context(session_id, {"awaiting_project_type": True})
            _save_pending_clarification(session_id, project_type_pending_state())
            draft = recommendation_clarification_warm(lang=reply_lang)
            final = await _apply_dynamic_response(
                session_id=session_id,
                user_message=user_message,
                draft=draft,
                response_goal="recommendation_clarification",
                intent="machine_recommendation",
                assistant_mode="recommendation_clarification",
                reply_lang=reply_lang,
                tool_result={"suggestions": list(PROJECT_TYPE_CHIPS)[:6], "message": draft},
            )
            reply = final["message"]
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode="recommendation_clarification",
                    suggestions=final.get("suggestions") or list(PROJECT_TYPE_CHIPS)[:6],
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "machine_recommendation",
                        "pending_clarification": project_type_pending_state(),
                        "response_goal": "recommendation_clarification",
                        "response_signature": final.get("response_signature"),
                        "gateway_used": True,
                    },
                    input_meta=input_meta,
                ),
            )

        purpose_pending = build_purpose_pending(
            requested_category="",
            city=last_filters.get("city"),
        )
        _save_pending_clarification(session_id, purpose_pending)
        resp = build_advisory_clarification(lang=reply_lang)
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=resp["message"],
            response_goal="collect_machine_requirements",
            intent="advisory_clarification",
            assistant_mode="clarification",
            reply_lang=reply_lang,
            tool_result=resp,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "advisory_clarification",
                    "pending_clarification": purpose_pending,
                    "response_goal": "collect_machine_requirements",
                    "response_signature": final.get("response_signature"),
                    "gateway_used": True,
                },
            ),
        )

    if ctx_turn.get("turn_type") == "suitability":
        machine = ctx_turn.get("referenced_machine")
        if machine:
            city = last_filters.get("city") or (result_ctx.get("filters") or {}).get("city")
            resp = build_suitability_response(
                machine=machine,
                purpose_key=ctx_turn.get("purpose_key"),
                city=city,
                lang=reply_lang,
            )
            final = await _apply_dynamic_response(
                session_id=session_id,
                user_message=user_message,
                draft=resp["message"],
                response_goal="ask_followup_context",
                intent="machine_suitability",
                assistant_mode=resp.get("assistant_mode", "recommendation"),
                reply_lang=reply_lang,
                tool_result={
                    "message": resp["message"],
                    "suggestions": resp.get("suggestions") or [],
                    "preserve_machine_panel": True,
                },
            )
            reply = final["message"]
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode=resp.get("assistant_mode", "recommendation"),
                    suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "machine_suitability",
                        "preserve_machine_panel": True,
                        "referenced_machine": machine.get("name"),
                        "purpose_key": ctx_turn.get("purpose_key"),
                        "response_signature": final.get("response_signature"),
                        "gateway_used": True,
                    },
                ),
            )

    forced_filters = None
    if ctx_turn.get("turn_type") == "purpose_search":
        from app.ai.context_routing_gate import get_current_gate
        if (get_current_gate() or {}).get("block_previous_search_context"):
            ctx_turn = {**ctx_turn, "turn_type": "none", "search_filters": None}
    if ctx_turn.get("turn_type") == "purpose_search":
        sf = dict(ctx_turn.get("search_filters") or {})
        if sf.get("category") and not sf.get("city"):
            from app.chatbot.chatbot_service import _save_pending_clarification
            from app.chatbot.assistant_intelligence import (
                chips_from_categories,
                machine_purpose_city_message,
                map_purpose_to_categories,
            )

            pk = ctx_turn.get("purpose_key") or sf.get("purpose_key")
            purpose_pending = {
                "missing_field": "machine_purpose",
                "type": "machine_purpose",
                "purpose_key": pk,
                "category": sf.get("category"),
                "missing": ["city"],
                "source": "purpose_without_city",
            }
            _save_pending_clarification(session_id, purpose_pending)
            draft = machine_purpose_city_message(pk or "work", lang=reply_lang)
            cats = map_purpose_to_categories(pk or "") if pk else []
            suggestions = chips_from_categories(cats[:3]) + ["Jaipur", "Delhi", "Mumbai"]
            final = await _apply_dynamic_response(
                session_id=session_id,
                user_message=user_message,
                draft=draft,
                response_goal="ask_city",
                intent="machine_purpose_clarification",
                assistant_mode="clarification",
                reply_lang=reply_lang,
                classification=classification,
                tool_result={"suggestions": suggestions, "message": draft},
            )
            reply = final["message"]
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode="clarification",
                    suggestions=final.get("suggestions") or suggestions,
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "machine_purpose_clarification",
                        "pending_clarification": purpose_pending,
                        "purpose_key": pk,
                        "response_goal": "ask_city",
                        "response_signature": final.get("response_signature"),
                        "gateway_used": True,
                    },
                    input_meta=input_meta,
                ),
            )
        forced_filters = sf
        print(f"[assistant_router] purpose_search filters={forced_filters}")

    working_message_ctx = working_message
    if ctx_turn.get("turn_type") == "reference_enrich" and ctx_turn.get("enriched_message"):
        if not ctx_turn.get("reference_enrich_blocked"):
            working_message_ctx = ctx_turn["enriched_message"]
            try:
                from app.ai.assistant_debug_trace import record_context_routing
                record_context_routing({
                    "reference_enrich_applied": True,
                    "reference_enrich_blocked_reason": "",
                })
            except Exception:
                pass
        else:
            try:
                from app.ai.assistant_debug_trace import record_context_routing
                record_context_routing({
                    "reference_enrich_applied": False,
                    "reference_enrich_blocked_reason": ctx_turn.get("reference_enrich_blocked_reason") or "",
                })
            except Exception:
                pass

    from app.chatbot.image_context_memory import (
        is_image_follow_up,
        resolve_message_with_image_context,
    )

    working_for_classify = working_message_ctx
    used_img_ctx = False
    if is_image_follow_up(working_message_ctx, session_id):
        img_resolved, used_img_ctx = resolve_message_with_image_context(
            session_id, working_message_ctx,
        )
        if used_img_ctx:
            working_for_classify = img_resolved

    router_ctx = {
        "last_filters": last_filters,
        "greeted": greeted,
        "last_results": result_ctx,
        "pending": _get_pending_clarification(session_id),
        **(context or {}),
    }
    if conv_state:
        router_ctx = {**state_to_router_context(conv_state), **router_ctx}
        last_filters = router_ctx.get("last_filters") or last_filters

    from app.ai.context_routing_gate import get_current_gate, sanitize_router_context
    router_ctx = sanitize_router_context(router_ctx, get_current_gate() or {})
    last_filters = router_ctx.get("last_filters") or {}

    classification = await classify_assistant_intent(working_for_classify, router_ctx)
    _log_classification(user_message, classification)

    intent = str(classification.get("intent") or "")
    if used_img_ctx and intent in (
        "refund_return", "order_issue", "payment_issue", "booking_issue",
        "support", "help", "document_question", "document_qa", "greeting",
        "frustration", "abusive", "out_of_scope",
    ):
        used_img_ctx = False
    elif used_img_ctx:
        working_message_ctx = working_for_classify
        print(f"[assistant_router] image_context_injected message={working_message_ctx[:120]!r}")
        classification["used_image_context"] = True

    from app.ai.safe_action_router import resolve_action_decision
    from app.chatbot.image_context_memory import get_image_context as _get_img_ctx

    router_ctx["has_image_context"] = bool(_get_img_ctx(session_id))
    router_ctx["has_document_context"] = rag_has_documents(session_id)
    action_decision = resolve_action_decision(
        classification,
        router_ctx,
        message=working_message_ctx,
    )
    try:
        from app.ai.assistant_debug_trace import record_action_decision, record_routing
        record_action_decision(action_decision)
        record_routing(
            selected_action=action_decision.get("selected_action") or "",
            tool_used=action_decision.get("allowed_tool") or "none",
            should_search_machines=bool(action_decision.get("should_search_machines")),
        )
    except Exception:
        pass

    intent = classification.get("intent") or "unknown"
    should_search = bool(classification.get("should_search_machines"))
    if not action_decision.get("should_search_machines"):
        classification["should_search_machines"] = False
        should_search = False
    entities = classification.get("entities") or {}
    if conv_state:
        merge_incoming_turn(
            conv_state,
            message=working_message_ctx,
            parsed=parse_query(working_message_ctx),
            entities=entities,
            intent=intent,
        )
        conv_state["_last_action_decision"] = action_decision
        router_ctx = {**state_to_router_context(conv_state), **router_ctx}
        last_filters = router_ctx.get("last_filters") or last_filters

    if (
        action_decision.get("selected_action") == "ask_missing_machine_fields"
        and conv_state
        and (entities.get("city") or (conv_state.get("collected_fields") or {}).get("city"))
        and not (entities.get("category") or (conv_state.get("collected_fields") or {}).get("category"))
    ):
        req_resp = await _try_early_requirement_clarification(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message,
            conv_state=conv_state,
            reply_lang=reply_lang,
            input_meta=input_meta,
        )
        if req_resp is not None:
            return req_resp

    print(
        f"[assistant_router] assistant_mode={action_decision.get('assistant_mode') or classification.get('assistant_mode', intent)} "
        f"action={action_decision.get('selected_action')} tool={action_decision.get('allowed_tool')}"
    )

    # --- Frustration recovery (no search) ------------------------------------
    if intent == "frustration":
        resp = build_response("frustration", lang=reply_lang, message=working_message)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent="frustration",
            assistant_mode="support",
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            classification=classification,
            entities=entities,
            input_meta=input_meta,
            response_goal="frustration_recovery",
        )

    # --- Acknowledgement without substantive answer ----------------------------
    if intent == "acknowledgement":
        reply = (
            "Got it. Tell me the machine type and city, or pick an option below."
            if reply_lang == "english"
            else "Theek hai. Machine type aur city bata dein, ya neeche se option choose karein."
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=reply,
            intent="acknowledgement",
            assistant_mode="conversational",
            reply_lang=reply_lang,
            suggestions=["Excavator", "Road Roller", "Crane", "Need support"],
            classification=classification,
            input_meta=input_meta,
            response_goal="continue_pending_flow",
        )

    # --- Structured search refinement (city switch, brand filter, etc.) --------
    refine_route = await _try_search_refinement_route(
        session_id=session_id,
        user_message=user_message,
        working_message=working_message_ctx,
        database=database,
        gate=gate,
        last_filters=last_filters,
        reply_lang=reply_lang,
        input_meta=input_meta,
        classification=classification,
        action_decision=action_decision,
    )
    if refine_route is not None:
        return refine_route

    # --- Brand / inventory query (permission-matrix routed) --------------------
    if action_decision.get("intent") == "machine_brand_query" or intent == "machine_brand_query":
        return await _route_brand_inventory_action(
            session_id=session_id,
            user_message=user_message,
            database=database,
            action_decision=action_decision,
            classification=classification,
            entities=entities,
            last_filters=last_filters,
            reply_lang=reply_lang,
            input_meta=input_meta,
        )

    # --- Budget follow-up refinement -------------------------------------------
    if intent in ("higher_budget_query", "cheaper_option_query"):
        from app.chatbot.intent_resolver import resolve_user_intent

        pending = _get_pending_clarification(session_id)
        resolved = await resolve_user_intent(
            session_id,
            working_message_ctx,
            last_filters=last_filters,
            pending=pending,
            greeted=greeted,
            router_intent=intent,
        )
        merged = resolved.get("filters") or {}
        if merged.get("category") or merged.get("city"):
            return await _guarded_machine_search(
                session_id=session_id,
                message=working_message_ctx,
                database=database,
                classification={
                    **classification,
                    "should_search_machines": True,
                    "intent": intent,
                },
                action_decision=action_decision,
                forced_filters=merged,
            )
        reply = (
            "I can help with that. Which machine category and city should I use?"
            if reply_lang == "english"
            else "Theek hai. Kaunsi machine category aur city use karun?"
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=reply,
            intent=intent,
            assistant_mode="clarification",
            reply_lang=reply_lang,
            suggestions=["Excavator in Jaipur", "Road Roller", "Contact support"],
            classification=classification,
            entities=entities,
            input_meta=input_meta,
        )

    # --- Document Q&A (inline RAG — explicit document intent ONLY) -----------
    if _document_query_allowed(intent, working_message):
        if not rag_has_documents(session_id):
            return await _document_qa_response(
                session_id=session_id,
                user_message=user_message,
                reply_lang=reply_lang,
                no_document=True,
                classification=classification,
                input_meta=input_meta,
            )
        rag = ask_rag_question(working_message_ctx, session_id=session_id)
        if rag.get("success"):
            return await _document_qa_response(
                session_id=session_id,
                user_message=user_message,
                reply_lang=reply_lang,
                rag_result=rag,
                classification=classification,
                input_meta=input_meta,
            )
        return await _document_qa_response(
            session_id=session_id,
            user_message=user_message,
            reply_lang=reply_lang,
            no_document=True,
            classification=classification,
            input_meta=input_meta,
        )

    # --- Image reference without saved image context — clarify, no search -----
    from app.chatbot.image_context_memory import (
        get_image_context,
        has_strong_image_reference,
        has_weak_image_reference,
        mentions_explicit_machine,
    )

    if (
        intent in ("image_search_followup", "machine_availability")
        or (
            not mentions_explicit_machine(working_message)
            and (has_strong_image_reference(working_message) or has_weak_image_reference(working_message))
        )
    ) and not get_image_context(session_id):
        reply = (
            "I could not confidently detect a construction machine from your last image. "
            "Please upload a clear machine photo or tell me the machine type and city."
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=reply,
            intent="image_clarification",
            assistant_mode="image_clarification",
            reply_lang=reply_lang,
            suggestions=[
                "Excavator", "JCB / Backhoe Loader", "Crane", "Road Roller",
                "Dump Truck", "Crawler Drill", "Motor Grader", "Wheel Loader",
            ],
            classification=classification,
            input_meta=input_meta,
        )

    # --- Greeting ------------------------------------------------------------
    if intent == "greeting":
        first_time = not greeted
        _save_session_context(session_id, {**session_ctx, "greeted": True})
        reply = greeting_message(first_time=first_time, lang=reply_lang)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=reply,
            intent="greeting",
            assistant_mode="greeting",
            reply_lang=reply_lang,
            suggestions=list(_GREETING_CHIPS),
            classification=classification,
            input_meta=input_meta,
        )

    # --- Support / help / out-of-scope (never search) -------------------------
    has_selected = bool(
        (session_ctx.get("selected_machine") or {}).get("name")
        or (session_ctx.get("selected_machine") or {}).get("id")
    )
    if is_blocked_search_intent(intent) or (
        intent == "contact_owner" and not (
            last_filters.get("category")
            or last_filters.get("brand")
            or has_selected
            or result_ctx.get("last_machines")
        )
    ):
        if intent in ("compare_machine", "machine_comparison"):
            from app.ai.universal_turn_engine import _comparison_shape, _detect_brands, _detect_category
            from app.chatbot.query_parser import parse_query

            parsed_cmp = parse_query(working_message)
            cmp_turn = await classify_universal_turn_async(
                working_message,
                session_ctx=session_ctx,
                result_ctx=result_ctx,
                last_filters=last_filters,
                greeted=greeted,
            )
            if cmp_turn.get("shape") != "comparison":
                cmp_turn = _comparison_shape(working_message, parsed_cmp) or {
                    **cmp_turn,
                    "shape": "comparison",
                    "brands": (
                        cmp_turn.get("brands")
                        or entities.get("brands")
                        or _detect_brands(working_message)
                        or list(parsed_cmp.get("brands") or [])
                    ),
                    "category": (
                        cmp_turn.get("category")
                        or entities.get("category")
                        or _detect_category(working_message)
                        or parsed_cmp.get("category")
                    ),
                    "needs_clarification": False,
                    "original_message": working_message,
                }
            return await _respond_comparison_turn(
                session_id=session_id,
                user_message=user_message,
                working_message=working_message,
                database=database,
                turn=cmp_turn,
                last_filters=last_filters,
                reply_lang=reply_lang,
                input_meta=input_meta,
                classification=classification,
            )

        has_machine_ctx = bool(
            last_filters.get("category") or last_filters.get("brand")
        )
        resp = build_response(
            intent,
            entities=entities,
            lang=reply_lang,
            has_machine_context=has_machine_ctx,
            message=working_message,
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent=intent,
            assistant_mode=resp.get("assistant_mode", "support"),
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            handover=resp.get("handover"),
            classification=classification,
            entities=entities,
            input_meta=input_meta,
        )

    # --- Unknown without search permission ------------------------------------
    if intent == "unknown" and not should_search:
        resp = build_response("unknown", entities=entities, lang=reply_lang, message=working_message)
        if is_broad_vague_query(
            working_message,
            session_collected=(get_current_state() or {}).get("collected_fields"),
        ) or resolve_purpose_key(working_message):
            from app.chatbot.assistant_intelligence import build_broad_machine_request_response
            from app.chatbot.chatbot_service import _save_pending_clarification

            bresp = build_broad_machine_request_response(lang=reply_lang)
            _save_pending_clarification(session_id, bresp["pending"])
            resp = {
                "message": (
                    "I'm not fully sure which machine you need. "
                    "Can you tell me the work type and city?"
                ),
                "assistant_mode": "clarification",
                "suggestions": bresp.get("suggestions") or [],
            }
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent="unknown",
            assistant_mode="unknown",
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            classification=classification,
            entities=entities,
            input_meta=input_meta,
            response_goal="clarify_unknown",
        )

    # --- Project / machine recommendation -----------------------------------
    if intent == "machine_recommendation":
        from app.chatbot.chatbot_service import (
            _get_recommendation_context,
            _save_pending_clarification,
            _save_recommendation_context,
        )

        rec_ctx = _get_recommendation_context(session_id)
        awaiting = bool(rec_ctx and rec_ctx.get("awaiting_project_type"))
        project_key = parse_project_type_option(working_message)
        if not project_key and awaiting:
            project_key = (rec_ctx or {}).get("project_type")
        if not project_key:
            project_key = detect_project_type(working_message)
        if not project_key:
            _save_recommendation_context(session_id, {"awaiting_project_type": True})
            _save_pending_clarification(session_id, project_type_pending_state())
            reply = recommendation_clarification_warm(lang=reply_lang)
            return await _support_response(
                session_id=session_id,
                user_message=user_message,
                reply=reply,
                intent="machine_recommendation",
                assistant_mode="recommendation_clarification",
                reply_lang=reply_lang,
                suggestions=list(PROJECT_TYPE_CHIPS)[:6],
                classification=classification,
                input_meta=input_meta,
                response_goal="recommendation_clarification",
                extra={"pending_clarification": project_type_pending_state()},
            )
        return await _route_project_recommendation(
            session_id=session_id,
            user_message=user_message,
            working_message=working_message_ctx,
            database=database,
            project_key=project_key,
            classification=classification,
            input_meta=input_meta,
            reply_lang=reply_lang,
        )

    # --- Machine search (gate: should_search_machines OR forced advisory) -----
    if not should_search and not forced_filters:
        if conv_state:
            req_resp = await _try_early_requirement_clarification(
                session_id=session_id,
                user_message=user_message,
                working_message=working_message,
                conv_state=conv_state,
                reply_lang=reply_lang,
                input_meta=input_meta,
            )
            if req_resp is not None:
                return req_resp
        resp = build_response("unknown", entities=entities, lang=reply_lang, message=working_message)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent=intent,
            assistant_mode="unknown",
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            classification=classification,
            entities=entities,
            input_meta=input_meta,
        )

    # --- City-only without category → requirement collection, not search --------
    if conv_state and not forced_filters:
        collected = conv_state.get("collected_fields") or {}
        ent_city = entities.get("city") or collected.get("city")
        ent_cat = entities.get("category") or entities.get("machine_type") or collected.get("category")
        from app.ai.search_refinement_engine import detect_refinement_type

        is_refinement = bool(detect_refinement_type(working_message_ctx, parse_query(working_message_ctx)))
        if ent_city and not ent_cat and not is_refinement and intent in (
            "machine_search", "rent_machine", "buy_machine", "unknown",
        ):
            req_resp = await _try_early_requirement_clarification(
                session_id=session_id,
                user_message=user_message,
                working_message=working_message,
                conv_state=conv_state,
                reply_lang=reply_lang,
                input_meta=input_meta,
            )
            if req_resp is not None:
                return req_resp

    if not is_machine_search_intent(intent) and not forced_filters:
        resp = build_response(intent, entities=entities, lang=reply_lang, message=working_message)
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent=intent,
            assistant_mode=resp.get("assistant_mode", "support"),
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            handover=resp.get("handover"),
            classification=classification,
            entities=entities,
            input_meta=input_meta,
        )

    return await _guarded_machine_search(
        session_id=session_id,
        message=working_message_ctx,
        database=database,
        classification=classification,
        action_decision=action_decision,
        forced_filters=forced_filters,
    )
