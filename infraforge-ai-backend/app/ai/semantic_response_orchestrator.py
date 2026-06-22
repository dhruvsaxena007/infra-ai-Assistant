"""
Semantic Response Orchestrator — routes high-confidence semantic understanding
BEFORE domain-gateway false boundaries and legacy misclassification.

Mechanism-level: uses SemanticTurnUnderstanding + response_mode, not phrase hacks.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.semantic_turn_gateway import SemanticTurnUnderstanding


async def try_semantic_orchestrated_route(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    semantic: SemanticTurnUnderstanding,
    mode_decision: dict[str, Any],
    parsed: dict[str, Any],
    reply_lang: str,
    input_meta: dict | None,
    database,
    conv_state: dict | None,
    assistant_router_module: Any,
) -> Optional[dict]:
    """
    Execute canonical response for semantic intents. Returns API envelope or None.
    """
    intent = semantic.primary_intent
    mode = semantic.response_mode or mode_decision.get("response_mode")
    confidence = float(semantic.confidence or 0)

    # Only route when semantic layer is confident enough (rules or validated LLM)
    routable = {
        "meta_help", "memory_question", "frustration", "support",
        "domain_knowledge", "recommendation", "comparison",
        "clarification_answer", "search_refinement", "machine_search",
        "off_topic",
    }
    if intent not in routable and mode not in routable:
        return None
    if confidence < 0.72 and semantic.layer != "llm":
        if intent not in ("memory_question", "meta_help", "frustration", "support"):
            return None

    _apply_dynamic = assistant_router_module._apply_dynamic_response
    _assistant_payload = assistant_router_module._assistant_payload
    success_response = assistant_router_module.success_response
    from app.chatbot.memory import save_conversation

    # --- Meta help ------------------------------------------------------------
    if intent == "meta_help" or mode == "meta_help":
        from app.ai.response_mode_gateway import build_meta_help_draft

        tool = await build_meta_help_draft(lang=reply_lang)
        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=tool["message"],
            response_goal=tool.get("response_goal") or "meta_help",
            intent="general_marketplace_help",
            assistant_mode="conversational",
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
                    "response_goal": "meta_help",
                    "semantic_understanding": semantic.to_dict(),
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    # --- Memory question ------------------------------------------------------
    if intent == "memory_question" or mode == "memory_answer":
        from app.ai.response_mode_gateway import build_memory_answer_draft
        from app.chatbot.chatbot_service import _get_session_context

        session_ctx = _get_session_context(session_id)
        semantic.context_reference.setdefault(
            "user_name",
            session_ctx.get("user_name")
            or (session_ctx.get("collected_fields") or {}).get("name"),
        )
        tool = await build_memory_answer_draft(
            semantic,
            session_ctx=session_ctx,
            lang=reply_lang,
        )
        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=tool["message"],
            response_goal=tool.get("response_goal") or "memory_answer",
            intent="user_introduction",
            assistant_mode="conversational",
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
                    "intent": "user_introduction",
                    "response_goal": "memory_answer",
                    "semantic_understanding": semantic.to_dict(),
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    # --- Frustration recovery -------------------------------------------------
    if intent == "frustration" or mode == "frustration_recovery":
        from app.ai.assistant_brain import build_response

        resp = build_response("frustration", lang=reply_lang, message=working_message)
        return await assistant_router_module._support_response(
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

    # --- Support --------------------------------------------------------------
    if intent == "support" or mode == "support" or mode_decision.get("force_support"):
        from app.ai.assistant_brain import build_response

        resp = build_response("support_request", lang=reply_lang, message=working_message)
        return await assistant_router_module._support_response(
            session_id=session_id,
            user_message=user_message,
            reply=resp["message"],
            intent="support_request",
            assistant_mode=resp.get("assistant_mode", "support"),
            reply_lang=reply_lang,
            suggestions=resp.get("suggestions") or [],
            handover=resp.get("handover"),
            input_meta=input_meta,
            response_goal="support_guidance",
        )

    # --- Domain knowledge -----------------------------------------------------
    if intent == "domain_knowledge" or mode == "domain_knowledge" or mode_decision.get("force_knowledge"):
        from app.ai.knowledge_query_engine import build_knowledge_answer, knowledge_turn_from_message

        kq = (
            (semantic.context_reference or {}).get("knowledge")
            or knowledge_turn_from_message(working_message, parsed, session_ctx=conv_state)
        )
        if kq:
            turn = {**kq, "shape": "knowledge_answer", "kind": kq.get("kind")}
            tool = await build_knowledge_answer(turn, user_message=working_message, lang=reply_lang)
            final = await _apply_dynamic(
                session_id=session_id,
                user_message=user_message,
                draft=tool["message"],
                response_goal=tool.get("response_goal") or "domain_knowledge_answer",
                intent=kq.get("kind") or "domain_knowledge",
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
                        "intent": kq.get("kind") or "domain_knowledge",
                        "response_goal": tool.get("response_goal"),
                        "semantic_understanding": semantic.to_dict(),
                        "gateway_used": True,
                    },
                    input_meta=input_meta,
                ),
            )

    # --- Comparison (brand advisory or prior results) -------------------------
    if intent == "comparison" or mode == "comparison" or semantic.should_compare:
        ref = semantic.context_reference or {}
        state = conv_state or {}
        last_machines = (
            state.get("last_visible_results")
            or (state.get("last_results") or {}).get("last_machines")
            or []
        )

        # Compare machines from previous search results
        if ref.get("type") == "best_among_previous" and len(last_machines) >= 2:
            from app.ai.comparison_service import compare_machines, generate_comparison_summary

            m1, m2 = last_machines[0], last_machines[1]
            cmp = compare_machines(m1, m2)
            draft = await generate_comparison_summary(m1, m2, cmp, lang=reply_lang)
            final = await _apply_dynamic(
                session_id=session_id,
                user_message=user_message,
                draft=draft,
                response_goal="show_comparison",
                intent="comparison",
                assistant_mode="comparison",
                reply_lang=reply_lang,
                tool_result={"comparison": cmp, "machines": [m1, m2]},
            )
            reply = final["message"]
            save_conversation(session_id, user_message, reply)
            extras = assistant_router_module._comparison_payload_extras(
                {"comparison": cmp, "machines": [m1, m2]}
            )
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode="comparison",
                    suggestions=final.get("suggestions") or ["Search Machine", "Contact owner"],
                    reply_language=reply_lang,
                    context_extra={
                        "intent": "comparison",
                        "response_goal": "show_comparison",
                        "semantic_understanding": semantic.to_dict(),
                        "gateway_used": True,
                    },
                    input_meta=input_meta,
                    **extras,
                ),
            )

        from app.ai.brand_comparison_advisory import (
            build_brand_advisory_comparison,
            is_brand_advisory_comparison,
        )
        from app.ai.category_mapping import detect_all_brands, detect_requested_category

        brands = list(parsed.get("brands") or detect_all_brands(working_message))
        category = parsed.get("category") or detect_requested_category(working_message)
        cmp_ctx = state.get("last_comparison_context") or {}
        if len(brands) < 2:
            brands = list(cmp_ctx.get("brands") or brands)

        if is_brand_advisory_comparison(working_message, parsed=parsed) or len(brands) >= 2:
            try:
                resp = await build_brand_advisory_comparison(
                    brands=brands,
                    category=category or cmp_ctx.get("category"),
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
                            "advisory_comparison": True,
                            "semantic_understanding": semantic.to_dict(),
                            "gateway_used": True,
                        },
                        input_meta=input_meta,
                        **cmp_extras,
                    ),
                )
            except Exception as exc:
                print(f"[semantic_orchestrator] comparison_failed: {exc}")

    # --- Recommendation (advisory first — do not dump stale search) -----------
    if intent == "recommendation" or mode == "recommendation" or semantic.should_recommend:
        from app.ai.domain_recommendation_engine import (
            build_recommendation_advisory_draft,
            recommend_machine_categories,
        )

        plan = recommend_machine_categories(working_message, parsed=parsed)
        city = parsed.get("city") or plan.get("city")
        tool = build_recommendation_advisory_draft(plan, lang=reply_lang)

        # If user gave city + clear category/purpose, search listings
        if city and plan.get("primary_category"):
            from app.chatbot.chatbot_service import execute_machine_search_turn

            filters = {
                "category": plan["primary_category"],
                "city": city,
                "max_price": parsed.get("max_price"),
                "listing_type": parsed.get("listing_type"),
            }
            classification = {
                "intent": "machine_recommendation",
                "should_search_machines": True,
                "confidence": confidence,
            }
            return await assistant_router_module._guarded_machine_search(
                session_id=session_id,
                message=working_message,
                database=database,
                classification=classification,
                forced_filters={k: v for k, v in filters.items() if v is not None},
                search_flags={
                    "recommended_categories": plan.get("categories") or [],
                    "purpose_key": plan.get("purpose_key"),
                },
            )

        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=tool["message"],
            response_goal="recommendation_advisory",
            intent="machine_recommendation",
            assistant_mode="recommendation",
            reply_lang=reply_lang,
            tool_result=tool,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        if conv_state is not None:
            conv_state["active_flow"] = "machine_recommendation"
            conv_state["last_recommendation_context"] = {
                "purpose_key": plan.get("purpose_key"),
                "primary_category": plan.get("primary_category"),
                "categories": plan.get("categories"),
                "city": city,
            }
            from app.ai.session_requirement_context import sync_turn_context_to_collected

            sync_turn_context_to_collected(
                conv_state,
                last_user_goal="recommendation",
                recommendation_context={
                    "purpose_key": plan.get("purpose_key"),
                    "primary_category": plan.get("primary_category"),
                    "categories": plan.get("categories"),
                    "city": city,
                },
            )
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="recommendation",
                suggestions=final.get("suggestions") or tool.get("suggestions") or [],
                reply_language=reply_lang,
                context_extra={
                    "intent": "machine_recommendation",
                    "response_goal": "recommendation_advisory",
                    "semantic_understanding": semantic.to_dict(),
                    "recommendation_plan": plan,
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    # --- Search / refinement (fragments + explicit search) ----------------------
    if (
        semantic.should_search
        or mode in ("machine_search", "search_refinement", "clarification_answer")
        or intent in ("machine_search", "clarification_answer", "search_refinement")
    ):
        has_filters = bool(
            parsed.get("category") or parsed.get("city") or parsed.get("max_price")
            or parsed.get("brand") or parsed.get("purpose_key")
        )
        if has_filters or semantic.is_fragment:
            from app.chatbot.chatbot_service import execute_machine_search_turn

            classification = {
                "intent": "machine_search",
                "should_search_machines": True,
                "confidence": confidence,
            }
            forced = {k: parsed.get(k) for k in (
                "category", "city", "max_price", "brand", "listing_type", "purpose_key",
            ) if parsed.get(k) is not None}
            return await assistant_router_module._guarded_machine_search(
                session_id=session_id,
                message=working_message,
                database=database,
                classification=classification,
                forced_filters=forced or None,
            )

    # --- Off-topic redirect ---------------------------------------------------
    if intent == "off_topic" or mode == "off_topic_redirect":
        from app.ai.safe_error_fallback import fallback_message_for_stage

        draft = fallback_message_for_stage("off_topic", lang=reply_lang, user_message=working_message)
        final = await _apply_dynamic(
            session_id=session_id,
            user_message=user_message,
            draft=draft,
            response_goal="off_topic_redirect",
            intent="out_of_scope",
            assistant_mode="clarification",
            reply_lang=reply_lang,
        )
        reply = final["message"]
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="clarification",
                suggestions=["Search Machine", "Contact support"],
                reply_language=reply_lang,
                context_extra={
                    "intent": "out_of_scope",
                    "semantic_understanding": semantic.to_dict(),
                    "gateway_used": True,
                },
                input_meta=input_meta,
            ),
        )

    return None
