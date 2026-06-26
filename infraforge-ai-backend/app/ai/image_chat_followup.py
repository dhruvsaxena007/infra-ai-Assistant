"""
Image chat follow-up executor — /chat continuations after /image-search.

Handles clarification chips, natural-language captions, city-only follow-ups,
availability checks, similar/exact intent, and brand-aware search using saved
image context (single source of truth in image_context_memory).
"""

from __future__ import annotations

from typing import Any

from app.ai.category_mapping import category_label, detect_brand, detect_model
from app.ai.image_turn_models import image_chip_to_intent
from app.ai.image_turn_resolver import (
    _clarification_chips,
    _exact_match_message,
    _lang_hint,
    build_search_message_for_image_intent,
    detect_image_text_intent,
)
from app.ai.query_parser import parse_query
from app.chatbot.image_context_memory import (
    get_image_context,
    save_image_context,
)

def _merge_entities(ctx: dict[str, Any], user_text: str) -> dict[str, Any]:
    parsed = parse_query(user_text or "")
    category = ctx.get("detected_category") or ctx.get("detected_machine_type")
    brand = ctx.get("detected_brand") or parsed.get("brand")
    model = ctx.get("detected_model") or parsed.get("model")
    city = parsed.get("city") or ctx.get("user_city")
    max_price = parsed.get("max_price") or ctx.get("user_max_price")
    listing_type = parsed.get("listing_type") or ctx.get("user_listing_type")

    if not brand:
        brand = detect_brand(user_text or "")
    if not model:
        model = detect_model(user_text or "")

    return {
        "category": category,
        "brand": brand,
        "model": model,
        "city": city,
        "max_price": max_price,
        "listing_type": listing_type,
        "confidence": float(ctx.get("confidence") or 0),
    }


def resolve_image_user_intent(user_text: str, ctx: dict[str, Any]) -> str | None:
    chip_intent = image_chip_to_intent(user_text)
    if chip_intent:
        return chip_intent

    pending = ctx.get("pending_image_intent")
    if pending:
        parsed = parse_query(user_text)
        if parsed.get("city") and len((user_text or "").split()) <= 4:
            return pending
        if parsed.get("max_price") or parsed.get("listing_type"):
            return pending

    return detect_image_text_intent(user_text)


def _identify_message(ctx: dict[str, Any], entities: dict[str, Any], lang: str) -> str:
    display = category_label(entities.get("category") or "machine")
    brand = entities.get("brand")
    model = entities.get("model")
    conf = float(entities.get("confidence") or ctx.get("confidence") or 0)
    conf_word = "high" if conf >= 0.55 else "medium" if conf >= 0.35 else "moderate"

    label_bits = [b for b in (brand, model, display) if b]
    label = " ".join(dict.fromkeys(label_bits)) if label_bits else display

    if lang == "hi":
        return (
            f"Is image me {label} jaisi machine lag rahi hai (confidence: {conf_word}). "
            "Agar chaho to similar machines ya availability check kar sakte hain."
        )
    return (
        f"This image looks like a {label} (confidence: {conf_word}). "
        "I have not searched listings yet — ask for similar machines or availability if you want."
    )


def _exact_match_search_message(entities: dict[str, Any]) -> str:
    return build_search_message_for_image_intent(
        image_intent="exact_match",
        entities=entities,
        user_text="",
    )


def _needs_city_for_search(entities: dict[str, Any], image_intent: str) -> bool:
    if image_intent in ("identify_only", "exact_match"):
        return False
    if entities.get("city"):
        return False
    return image_intent in ("similar_category", "availability_search", "exact_match")


def _city_clarification_message(entities: dict[str, Any], lang: str) -> str:
    display = category_label(entities.get("category") or "machine")
    brand = entities.get("brand")
    target = f"{brand} {display}".strip() if brand else display
    if lang == "hi":
        return f"Theek hai — {target} ke liye kaunsi city check karun? (jaise Jaipur, Delhi)"
    return f"Which city should I check for {target}? (e.g. Jaipur, Delhi)"


def _update_context_after_intent(
    session_id: str,
    ctx: dict[str, Any],
    *,
    image_intent: str,
    entities: dict[str, Any],
) -> None:
    updated = dict(ctx)
    updated["pending_image_intent"] = image_intent
    updated["awaiting_image_choice"] = image_intent in (
        "similar_category", "availability_search", "exact_match",
    )
    if entities.get("city"):
        updated["user_city"] = entities["city"]
        updated["awaiting_image_field"] = None
    elif _needs_city_for_search(entities, image_intent):
        updated["awaiting_image_field"] = "city"
    if entities.get("brand"):
        updated["detected_brand"] = entities["brand"]
    if entities.get("model"):
        updated["detected_model"] = entities["model"]
    save_image_context(session_id, full_context=updated)


async def try_image_chat_followup(
    *,
    session_id: str,
    user_message: str,
    working_message: str,
    database,
    reply_lang: str,
    session_ctx: dict[str, Any],
    conv_state: dict[str, Any] | None,
    input_meta: dict[str, Any] | None = None,
    assistant_router_module: Any,
) -> dict | None:
    """
    Execute image-context continuations on /chat before domain/off-topic routing.
    Returns a full success_response envelope or None to continue normal routing.
    """
    ctx = get_image_context(session_id)
    if not ctx:
        return None

    from app.chatbot.image_context_memory import is_image_flow_continuation

    if not is_image_flow_continuation(working_message, session_id):
        return None

    from app.ai.context_routing_gate import classify_message_family

    family = classify_message_family(working_message).get("family")
    if family in ("support_or_issue", "return_refund_or_booking_problem", "frustration_or_abuse"):
        return None

    text = (working_message or "").strip()
    lang = _lang_hint(text) if reply_lang == "english" else (
        "hi" if reply_lang in ("hindi", "hinglish") else "en"
    )
    image_intent = resolve_image_user_intent(text, ctx)
    if not image_intent:
        return None

    entities = _merge_entities(ctx, text)
    if not entities.get("category"):
        return None

    _update_context_after_intent(session_id, ctx, image_intent=image_intent, entities=entities)

    router = assistant_router_module
    _assistant_payload = router._assistant_payload
    _guarded_machine_search = router._guarded_machine_search
    _support_response = router._support_response
    _apply_dynamic_response = router._apply_dynamic_response

    # --- Identify only -------------------------------------------------------
    if image_intent == "identify_only":
        msg = _identify_message(ctx, entities, lang)
        final = await _apply_dynamic_response(
            session_id=session_id,
            user_message=user_message,
            draft=msg,
            response_goal="domain_knowledge_answer",
            intent="image_identify",
            assistant_mode="image_clarification",
            reply_lang=reply_lang,
        )
        return await _support_response(
            session_id=session_id,
            user_message=user_message,
            reply=final["message"],
            intent="image_identify",
            assistant_mode="image_clarification",
            reply_lang=reply_lang,
            suggestions=_clarification_chips(lang),
            input_meta=input_meta,
            extra={
                "response_goal": final.get("response_goal"),
                "image_intent": image_intent,
                "detected_category": entities.get("category"),
                "detected_brand": entities.get("brand"),
            },
        )

    # --- Exact match: honest + closest DB search when city known -------------
    if image_intent == "exact_match":
        if _needs_city_for_search(entities, "availability_search"):
            msg = _exact_match_message(entities.get("category") or "machine", lang)
            msg = f"{msg}\n\n{_city_clarification_message(entities, lang)}"
            final = await _apply_dynamic_response(
                session_id=session_id,
                user_message=user_message,
                draft=msg,
                response_goal="ask_image_clarification",
                intent="image_exact_match",
                assistant_mode="image_clarification",
                reply_lang=reply_lang,
            )
            return await _support_response(
                session_id=session_id,
                user_message=user_message,
                reply=final["message"],
                intent="image_exact_match",
                assistant_mode="image_clarification",
                reply_lang=reply_lang,
                suggestions=["Jaipur", "Delhi", "Similar machines"],
                input_meta=input_meta,
                extra={"image_intent": image_intent},
            )

        search_msg = _exact_match_search_message(entities)
        classification = {
            "intent": "machine_search",
            "should_search_machines": True,
            "entities": {
                "category": entities.get("category"),
                "city": entities.get("city"),
                "brand": entities.get("brand"),
                "model": entities.get("model"),
            },
            "used_image_context": True,
        }
        forced = {
            k: v for k, v in {
                "category": entities.get("category"),
                "city": entities.get("city"),
                "brand": entities.get("brand"),
                "model": entities.get("model"),
                "max_price": entities.get("max_price"),
                "listing_type": entities.get("listing_type"),
            }.items() if v
        }
        result = await _guarded_machine_search(
            session_id=session_id,
            message=search_msg,
            database=database,
            classification=classification,
            forced_filters=forced,
            search_flags={"image_intent": "exact_match", "from_image_context": True},
        )
        if result.get("success"):
            data = result.get("data") or {}
            lead = (
                "Exact same physical machine photo-match is not guaranteed, "
                "but here are the closest listings I found:"
                if lang == "en"
                else "Exact same photo-match guarantee nahi hai, lekin yeh closest listings hain:"
            )
            result["message"] = f"{lead}\n\n{result.get('message') or ''}".strip()
            ctx2 = get_image_context(session_id) or {}
            ctx2["awaiting_image_choice"] = False
            ctx2["pending_image_intent"] = None
            save_image_context(session_id, full_context=ctx2)
            data["assistant_mode"] = data.get("assistant_mode") or "image_search"
            data["image_intent"] = "exact_match"
            result["data"] = data
        return result

    # --- Similar / availability: search or ask city only -----------------------
    if image_intent in ("similar_category", "availability_search"):
        if _needs_city_for_search(entities, image_intent):
            msg = _city_clarification_message(entities, lang)
            final = await _apply_dynamic_response(
                session_id=session_id,
                user_message=user_message,
                draft=msg,
                response_goal="ask_image_clarification",
                intent="image_exact_match",
                assistant_mode="image_clarification",
                reply_lang=reply_lang,
            )
            return await _support_response(
                session_id=session_id,
                user_message=user_message,
                reply=final["message"],
                intent="image_search_followup",
                assistant_mode="image_clarification",
                reply_lang=reply_lang,
                suggestions=["Jaipur", "Delhi", "Mumbai", "Similar machines"],
                input_meta=input_meta,
                extra={
                    "image_intent": image_intent,
                    "pending_image_intent": image_intent,
                    "awaiting_image_field": "city",
                },
            )

        search_msg = build_search_message_for_image_intent(
            image_intent=image_intent,
            entities=entities,
            user_text=text,
        )
        classification = {
            "intent": "machine_search",
            "should_search_machines": True,
            "entities": {
                "category": entities.get("category"),
                "city": entities.get("city"),
                "brand": entities.get("brand"),
                "model": entities.get("model"),
            },
            "used_image_context": True,
        }
        forced = {
            k: v for k, v in {
                "category": entities.get("category"),
                "city": entities.get("city"),
                "brand": entities.get("brand"),
                "model": entities.get("model"),
                "max_price": entities.get("max_price"),
                "listing_type": entities.get("listing_type"),
            }.items() if v
        }
        result = await _guarded_machine_search(
            session_id=session_id,
            message=search_msg,
            database=database,
            classification=classification,
            forced_filters=forced,
            search_flags={
                "image_intent": image_intent,
                "from_image_context": True,
                "prefer_brand": bool(entities.get("brand")),
            },
        )
        if result.get("success"):
            data = result.get("data") or {}
            ctx2 = get_image_context(session_id) or {}
            ctx2["awaiting_image_choice"] = False
            ctx2["pending_image_intent"] = None
            ctx2["awaiting_image_field"] = None
            save_image_context(session_id, full_context=ctx2)
            data["assistant_mode"] = data.get("assistant_mode") or "image_search"
            data["image_intent"] = image_intent
            result["data"] = data
        return result

    return None
