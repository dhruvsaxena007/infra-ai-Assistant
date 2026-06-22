"""
Central assistant brain for InfraForge Marketplace.

Decides intent first, then routes to support responses or machine search.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.contextual_assistant import (
    build_advisory_clarification,
    build_multi_purpose_advisory,
    build_suitability_response,
)
from app.ai.conversation_context import analyze_contextual_turn, get_result_context
from app.ai.intent_classifier import classify_intent
from app.ai.support_response_service import build_response
from app.chatbot.assistant_intelligence import greeting_message, _GREETING_CHIPS
from app.chatbot.language import detect_query_language
from app.chatbot.memory import save_conversation
from app.utils.response import success_response


def _log_classification(message: str, classification: dict[str, Any]) -> None:
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


def _assistant_payload(
    *,
    message: str,
    machines: list | None = None,
    assistant_mode: str,
    suggestions: list | None = None,
    handover: dict | None = None,
    reply_language: str | None = None,
    **extra,
) -> dict:
    from app.chatbot.assistant_intelligence import build_response_context

    context_extra = dict(extra.pop("context_extra", None) or {})
    if reply_language:
        context_extra["reply_language"] = reply_language
    context_extra["assistant_mode"] = assistant_mode
    context_extra["intent"] = extra.pop("intent", assistant_mode)

    return {
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


async def handle_assistant_message(
    session_id: str,
    user_message: str,
    database,
    context: Optional[dict] = None,
) -> dict:
    """
    Central entry: classify intent, route to support or machine search.
    """
    from app.chatbot.chatbot_service import execute_machine_search_turn
    from app.chatbot.chatbot_service import (
        _get_last_filters,
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

    last_filters = _get_last_filters(session_id)
    session_ctx = _get_session_context(session_id)
    greeted = bool(session_ctx.get("greeted"))
    result_ctx = get_result_context(session_ctx)

    # --- Layer 0: session memory (last machines + purpose follow-ups) --------
    ctx_turn = analyze_contextual_turn(
        user_message,
        last_filters=last_filters,
        result_ctx=result_ctx,
    )
    print(
        "[assistant_router]",
        f"contextual_turn={ctx_turn.get('turn_type')}",
        f"purpose={ctx_turn.get('purpose_key')}",
        f"has_last_machines={bool(result_ctx.get('last_machines'))}",
    )

    reply_lang = detect_query_language(user_message)

    if ctx_turn.get("turn_type") == "multi_purpose_advisory":
        city = last_filters.get("city") or (result_ctx.get("filters") or {}).get("city")
        resp = await build_multi_purpose_advisory(
            database,
            purposes=ctx_turn.get("purpose_keys") or [],
            city=city,
            lang=reply_lang,
        )
        reply = resp["message"]
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
                suggestions=resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "multi_purpose_advisory",
                    "purposes": ctx_turn.get("purpose_keys"),
                    "city": city,
                },
            ),
        )

    if ctx_turn.get("turn_type") == "advisory_clarification":
        resp = build_advisory_clarification(lang=reply_lang)
        reply = resp["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={"intent": "advisory_clarification"},
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
            reply = resp["message"]
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode=resp.get("assistant_mode", "recommendation"),
                    suggestions=resp.get("suggestions") or [],
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "machine_suitability",
                        "preserve_machine_panel": True,
                        "referenced_machine": machine.get("name"),
                        "purpose_key": ctx_turn.get("purpose_key"),
                    },
                ),
            )

    forced_filters = None
    if ctx_turn.get("turn_type") == "purpose_search":
        forced_filters = ctx_turn.get("search_filters")
        print(f"[assistant_router] purpose_search filters={forced_filters}")

    working_message = user_message
    if ctx_turn.get("turn_type") == "reference_enrich" and ctx_turn.get("enriched_message"):
        working_message = ctx_turn["enriched_message"]

    router_ctx = {
        "last_filters": last_filters,
        "greeted": greeted,
        "last_results": result_ctx,
        **(context or {}),
    }

    classification = await classify_intent(working_message, router_ctx)
    _log_classification(user_message, classification)

    intent = classification.get("intent") or "unknown"
    should_search = bool(classification.get("should_search_machines")) or bool(forced_filters)
    entities = classification.get("entities") or {}

    assistant_mode = intent
    if intent == "greeting":
        assistant_mode = "greeting"
    elif intent in ("order_issue", "refund_return", "payment_issue"):
        assistant_mode = intent
    elif intent == "out_of_scope":
        assistant_mode = "out_of_scope"
    elif intent == "unknown":
        assistant_mode = "unknown"
    elif intent == "platform_how_to":
        assistant_mode = "platform_how_to"

    print(f"[assistant_router] assistant_mode={assistant_mode}")

    # --- Greeting ------------------------------------------------------------
    if intent == "greeting":
        first_time = not greeted
        _save_session_context(session_id, {**session_ctx, "greeted": True})
        reply = greeting_message(first_time=first_time, lang=reply_lang)
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="greeting",
                suggestions=list(_GREETING_CHIPS) if first_time else [],
                reply_language=reply_lang,
                context_extra={"intent": "greeting", "classification": classification},
            ),
        )

    # Intents that must NEVER trigger machine search
    _NO_SEARCH = frozenset({
        "refund_return", "order_issue", "payment_issue", "security_deposit",
        "delivery_logistics", "complaint", "support_request",
        "platform_how_to", "general_marketplace_help", "booking_help",
        "document_question", "out_of_scope", "compare_machine",
    })

    # --- Non-search: support, help, out-of-scope --------------------------
    if intent in _NO_SEARCH or (
        intent == "contact_owner" and not (
            last_filters.get("category") or last_filters.get("brand")
        )
    ):
        has_machine_ctx = bool(
            last_filters.get("category") or last_filters.get("brand")
        )
        resp = build_response(
            intent,
            entities=entities,
            lang=reply_lang,
            has_machine_context=has_machine_ctx,
        )
        reply = resp["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode=resp.get("assistant_mode", "support"),
                suggestions=resp.get("suggestions") or [],
                handover=resp.get("handover"),
                reply_language=reply_lang,
                context_extra={
                    "intent": intent,
                    "classification": classification,
                    "entities": entities,
                },
            ),
        )

    # Unknown without search signals → guided response, no machine search
    if intent == "unknown" and not should_search:
        resp = build_response("unknown", entities=entities, lang=reply_lang)
        reply = resp["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="unknown",
                suggestions=resp.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={"intent": intent, "classification": classification},
            ),
        )

    # --- Machine search / recommendation / clarification / follow-ups --------
    return await execute_machine_search_turn(
        session_id,
        working_message,
        database,
        classification=classification,
        forced_filters=forced_filters,
    )
