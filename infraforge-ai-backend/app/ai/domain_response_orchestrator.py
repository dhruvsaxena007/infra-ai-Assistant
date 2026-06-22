"""
Phase 12 — maps DomainInterpretation to router actions and response plans.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.domain_models import (
    DomainInterpretation,
    MODE_CLARIFICATION,
    MODE_CONVERSATIONAL,
    MODE_DOMAIN_ANSWER,
    MODE_REFUSAL,
    MODE_TOOL_ACTION,
    MODE_UNRELATED_REDIRECT,
    MODE_UNSUPPORTED_SERVICE,
    REQ_MARKETPLACE_ACTION,
)
from app.core.config import settings


def build_capability_boundary_plan(interp: DomainInterpretation, *, lang: str = "english") -> dict[str, Any]:
    """Response plan for unsupported_service or unrelated_redirect modes."""
    goal = (interp.user_goal or "").strip()
    closest = interp.capability.closest_supported_capability or "machine search"
    asset = interp.entities.requested_asset or goal[:80]

    if interp.response_mode == MODE_UNSUPPORTED_SERVICE:
        if lang == "hindi":
            draft = (
                f"Samajh gaya — aap {asset[:60]} ke baare me pooch rahe hain. "
                f"Yeh InfraForge marketplace par abhi supported listing type nahi lagta. "
                f"Main aapko {closest.replace('_', ' ')} me madad kar sakta hoon."
            )
        elif lang == "hinglish":
            draft = (
                f"Samajh gaya — aap {asset[:60]} ke baare me pooch rahe ho. "
                f"Yeh InfraForge par abhi supported listing nahi hai. "
                f"Closest option: {closest.replace('_', ' ')}."
            )
        else:
            draft = (
                f"I understand you're asking about {asset[:60]}. "
                f"That doesn't appear to be a supported listing type on InfraForge right now. "
                f"I can help with {closest.replace('_', ' ')} instead."
            )
        goal_name = "unsupported_service_boundary"
        suggestions = ["Search Machine", "Ask recommendation", "Contact support"]
    else:
        if lang == "hindi":
            draft = (
                f"Main InfraForge ka construction aur heavy-equipment assistant hoon. "
                f"Aapka sawal ({goal[:50]}) is domain se bahar hai. "
                f"Kya main aapko machine search, rental, ya platform support me madad karun?"
            )
        elif lang == "hinglish":
            draft = (
                f"Main InfraForge construction & equipment assistant hoon. "
                f"Yeh request ({goal[:50]}) hamare domain se bahar hai. "
                f"Machine search, rental, ya support me help chahiye?"
            )
        else:
            draft = (
                f"I'm InfraForge's construction and heavy-equipment assistant. "
                f"Your request ({goal[:50]}) is outside what I handle here. "
                f"Would you like help with machine search, rentals, or platform support?"
            )
        goal_name = "unrelated_redirect_boundary"
        suggestions = ["Search Machine", "Contact support", "Ask recommendation"]

    return {
        "message": draft,
        "suggestions": suggestions,
        "assistant_mode": "clarification",
        "response_goal": goal_name,
        "verified_facts": {
            "user_goal": goal,
            "domain_scope": interp.domain_scope,
            "relevance": interp.relevance,
            "closest_supported_capability": closest,
        },
        "capability_boundary": {
            "requested_asset_supported": interp.capability.requested_asset_supported,
            "closest_supported_capability": closest,
        },
        "prohibited_claims": ["availability", "booking_confirmed", "exact_price"],
    }


def should_skip_broad_machine_route(interp: DomainInterpretation) -> bool:
    """Hybrid mode: block broad_machine when catalog says unsupported."""
    if interp.response_mode == MODE_UNSUPPORTED_SERVICE:
        return True
    if interp.capability.requested_asset_supported is False and interp.capability.notes:
        if "marketplace_action_without_catalog_match" in interp.capability.notes:
            return True
    return False


def should_handle_via_domain_gateway(interp: DomainInterpretation) -> bool:
    """True when hybrid mode should route this interpretation directly."""
    if settings.domain_intelligence_off or settings.domain_intelligence_shadow:
        return False
    return interp.response_mode in (
        MODE_DOMAIN_ANSWER,
        MODE_CONVERSATIONAL,
        MODE_UNSUPPORTED_SERVICE,
        MODE_UNRELATED_REDIRECT,
        MODE_REFUSAL,
    )


async def try_domain_orchestrated_route(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    interp: DomainInterpretation,
    reply_lang: str,
    input_meta: dict | None,
    database,
    conv_state: dict | None,
    assistant_router_module: Any,
) -> Optional[dict]:
    """
    Execute domain-gateway response modes. Returns API response or None to fall through.
    """
    if not should_handle_via_domain_gateway(interp):
        return None

    from app.chatbot.memory import save_conversation
    from app.ai.domain_knowledge_service import generate_domain_knowledge_response

    _apply_dynamic = assistant_router_module._apply_dynamic_response
    _assistant_payload = assistant_router_module._assistant_payload
    success_response = assistant_router_module.success_response

    if interp.response_mode == MODE_CONVERSATIONAL:
        from app.ai.social_turn_detector import (
            _response_goal_for_kind,
            build_social_response_draft,
            detect_social_turn,
        )
        from app.chatbot.chatbot_service import _get_pending_clarification, _get_session_context

        session_ctx = _get_session_context(session_id)
        social_ctx = {
            **session_ctx,
            "pending": _get_pending_clarification(session_id),
            "last_filters": (conv_state or {}).get("last_search_filters") or {},
            "collected_fields": (conv_state or {}).get("collected_fields") or {},
            "conversation_state": conv_state,
            "greeted": bool(session_ctx.get("greeted")),
        }
        hint = interp.legacy_intent_hint or "conversational"
        social = detect_social_turn(working_message, social_ctx) or {
            "kind": hint,
            "subtype": hint,
            "response_goal": _response_goal_for_kind(hint),
            "has_machine_context": bool(social_ctx.get("last_results")),
            "original_message": working_message,
        }
        tool = build_social_response_draft(
            social,
            lang=reply_lang,
            user_name=session_ctx.get("user_name"),
        )
        goal = social.get("response_goal") or _response_goal_for_kind(social.get("kind") or "conversational")
        assistant_mode = "greeting" if social.get("kind") == "greeting" else "conversational"
        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=tool["message"],
            response_goal=goal,
            intent=social.get("kind") or "conversational",
            assistant_mode=assistant_mode,
            reply_lang=reply_lang,
            tool_result=tool,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        if social.get("kind") == "greeting" or social.get("subtype") == "greeting":
            from app.chatbot.chatbot_service import _save_session_context
            _save_session_context(session_id, {**session_ctx, "greeted": True})
        machines = []
        if tool.get("preserve_machines"):
            machines = (
                (session_ctx.get("last_results") or {}).get("last_machines")
                or (conv_state or {}).get("last_visible_results")
                or []
            )
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=machines,
                assistant_mode=assistant_mode,
                suggestions=final.get("suggestions") or tool.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": social.get("kind") or "conversational",
                    "response_goal": goal,
                    "domain_interpretation": interp.to_dict(),
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    if interp.response_mode == MODE_DOMAIN_ANSWER:
        from app.ai.knowledge_query_engine import (
            build_knowledge_answer,
            knowledge_turn_from_message,
        )
        from app.ai.query_parser import parse_query
        from app.ai.response_mode_gateway import build_meta_help_draft

        if interp.legacy_intent_hint == "general_marketplace_help" or interp.reason == "meta_help_signal":
            tool = await build_meta_help_draft(lang=reply_lang)
            goal = tool.get("response_goal") or "meta_help"
            final = await _apply_dynamic(
                session_id=session_id,
                user_message=user_message,
                draft=tool["message"],
                response_goal=goal,
                intent="general_marketplace_help",
                assistant_mode=tool.get("assistant_mode", "conversational"),
                reply_lang=reply_lang,
                tool_result=tool,
            )
            reply = final["message"]
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode="conversational",
                    suggestions=final.get("suggestions") or tool.get("suggestions") or [],
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "general_marketplace_help",
                        "response_goal": goal,
                        "domain_interpretation": interp.to_dict(),
                        "gateway_used": True,
                    },
                    input_meta=input_meta,
                ),
            )

        kq = knowledge_turn_from_message(working_message, parse_query(working_message))
        if kq:
            turn = {
                **kq,
                "shape": "knowledge_answer",
                "kind": kq.get("kind"),
                "subject": kq.get("subject"),
                "subject_type": kq.get("subject_type"),
            }
            tool = await build_knowledge_answer(
                turn,
                user_message=working_message,
                lang=reply_lang,
            )
            goal = tool.get("response_goal") or "domain_knowledge_answer"
            intent = kq.get("kind") or "domain_knowledge"
            final = await _apply_dynamic(
                session_id=session_id,
                user_message=user_message,
                draft=tool["message"],
                response_goal=goal,
                intent=intent,
                assistant_mode=tool.get("assistant_mode", "advisory"),
                reply_lang=reply_lang,
                tool_result=tool,
            )
            reply = final["message"]
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode=tool.get("assistant_mode", "advisory"),
                    suggestions=final.get("suggestions") or tool.get("suggestions") or [],
                    reply_language=reply_lang,
                    context_extra={
                        "intent": intent,
                        "response_goal": goal,
                        "domain_interpretation": interp.to_dict(),
                        "gateway_used": True,
                    },
                    input_meta=input_meta,
                ),
            )

        if interp.reason == "brand_advisory_comparison" or (
            interp.legacy_intent_hint == "machine_comparison"
            and interp.request_type == "domain_knowledge"
        ):
            from app.ai.brand_comparison_advisory import (
                build_brand_advisory_comparison,
                is_brand_advisory_comparison,
            )
            from app.ai.category_mapping import detect_all_brands, detect_requested_category

            brands = list(detect_all_brands(working_message))
            category = interp.entities.category or detect_requested_category(working_message)
            if is_brand_advisory_comparison(working_message):
                resp = await build_brand_advisory_comparison(
                    brands=brands,
                    category=category,
                    user_message=working_message,
                    lang=reply_lang,
                )
                cmp_extras = assistant_router_module._comparison_payload_extras(resp)
                final = await _apply_dynamic(
                    session_id=session_id,
                    user_message=user_message,
                    draft=resp["message"],
                    response_goal="show_comparison",
                    intent="comparison",
                    assistant_mode="comparison",
                    reply_lang=reply_lang,
                    tool_result={**resp, **cmp_extras},
                )
                reply = final["message"]
                save_conversation(session_id, user_message, reply)
                return success_response(
                    message=reply,
                    data=_assistant_payload(
                        message=reply,
                        machines=[],
                        assistant_mode="comparison",
                        suggestions=final.get("suggestions") or resp.get("suggestions") or [],
                        reply_language=reply_lang,
                        advisor_message=resp.get("llm_summary"),
                        context_extra={
                            "intent": "comparison",
                            "response_goal": "show_comparison",
                            "domain_interpretation": interp.to_dict(),
                            "advisory_comparison": True,
                            "gateway_used": True,
                        },
                        input_meta=input_meta,
                        **cmp_extras,
                    ),
                )

        tool = await generate_domain_knowledge_response(
            interp, user_message=working_message, lang=reply_lang,
        )
        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=tool["message"],
            response_goal=tool["response_goal"],
            intent="machine_advisory",
            assistant_mode="advisory",
            reply_lang=reply_lang,
            tool_result=tool,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        # Suspend machine flow without destroying state
        if conv_state and interp.context_action == "suspend":
            conv_state["_requirement_suspended"] = True
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="advisory",
                suggestions=final.get("suggestions") or tool.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "machine_advisory",
                    "response_goal": tool["response_goal"],
                    "domain_interpretation": interp.to_dict(),
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    if interp.response_mode in (MODE_UNSUPPORTED_SERVICE, MODE_UNRELATED_REDIRECT, MODE_REFUSAL):
        tool = build_capability_boundary_plan(interp, lang=reply_lang)
        intent = (
            "unsupported_service" if interp.response_mode == MODE_UNSUPPORTED_SERVICE
            else "out_of_scope"
        )
        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=tool["message"],
            response_goal=tool["response_goal"],
            intent=intent,
            assistant_mode="clarification",
            reply_lang=reply_lang,
            tool_result=tool,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=final.get("suggestions") or tool.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": intent,
                    "response_goal": tool["response_goal"],
                    "domain_interpretation": interp.to_dict(),
                    "boundary_response_generated": True,
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    return None


def build_domain_response_plan_extension(
    interp: DomainInterpretation,
    base_plan: dict[str, Any],
) -> dict[str, Any]:
    """Extend Response Plan with Phase 12 verified facts."""
    plan = dict(base_plan)
    plan["response_mode"] = interp.response_mode
    plan["user_goal"] = interp.user_goal
    plan["domain_scope"] = interp.domain_scope
    plan["verified_facts"] = {
        **(plan.get("verified_facts") or {}),
        "domain_interpretation": interp.to_dict(),
    }
    plan["capability_boundary"] = interp.capability.to_dict()
    plan["prohibited_claims"] = list(plan.get("prohibited_claims") or []) + [
        "invent_availability", "invent_price", "invent_booking_status",
    ]
    return plan
