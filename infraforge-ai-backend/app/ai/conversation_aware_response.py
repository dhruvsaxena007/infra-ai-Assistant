"""
Global conversation-aware response generation.

Controls natural wording and variant selection — never intent, search, or factual data.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from app.core.config import settings
from app.ai.response_plan import GOAL_SUGGESTIONS as _SUGGESTIONS

Variant = dict[str, Any]

# Goals where backend draft carries verified facts — never replace with generic template text.
_FACTUAL_DRAFT_GOALS = frozenset({
    "show_machine_results",
    "answer_document_question",
    "explain_no_result",
    "suggest_similar_machines",
    "show_brand_inventory",
    "check_brand_availability",
    "show_comparison",
    "continue_pending_flow",
    "recommendation_clarification",
    "support_collect_details",
    "support_recovery",
    "explain_security_deposit",
    "explain_rental_process",
    # Social / conversational — backend draft is the source of truth.
    "greet_user",
    "acknowledge_name",
    "respond_wellbeing",
    "respond_conversational",
    "respond_appreciation",
    "respond_gratitude",
    "respond_satisfaction",
    "respond_flow_ack",
    "domain_knowledge_answer",
    "assistant_identity",
    "meta_help",
    "memory_answer",
    "support_guidance",
    "offer_handover",
})

_EMPATHY_PREFIX: dict[str, str] = {
    "explain_no_result": "I understand this is frustrating. ",
    "collect_transaction_id": "I am sorry you are dealing with this. ",
    "collect_booking_id": "I am sorry for the inconvenience. ",
}

_VARIANTS: dict[str, list[Variant]] = {
    "greet_user": [
        {"id": "greet_a", "style": "warm", "use_name": False,
         "english": "Hello! I can help you search machines, compare options, rent or buy, and handle support on InfraForge.",
         "hinglish": "Namaste! Main machine search, compare, rent/buy aur support me help kar sakta hoon."},
        {"id": "greet_b", "style": "professional", "use_name": False,
         "english": "Welcome to InfraForge. Tell me what machine or help you need today.",
         "hinglish": "InfraForge me welcome. Bataiye kaunsi machine ya help chahiye."},
        {"id": "greet_c", "style": "warm", "use_name": True,
         "english": "Hello, {name}! Ready when you are — search, compare, booking, or support.",
         "hinglish": "Hello, {name}! Jab ready hon — search, compare, booking ya support."},
    ],
    "acknowledge_name": [
        {"id": "name_a", "style": "warm", "use_name": True,
         "english": "Nice to meet you, {name}. How can I help you with InfraForge today?",
         "hinglish": "Nice to meet you, {name}. Aaj InfraForge me kaise madad kar sakta hoon?"},
        {"id": "name_b", "style": "professional", "use_name": True,
         "english": "Good to connect, {name}. I can help with machine search, recommendations, and support.",
         "hinglish": "Good to connect, {name}. Machine search, recommendation ya support — bataiye."},
        {"id": "name_c", "style": "warm", "use_name": True,
         "english": "Thanks for introducing yourself, {name}. What would you like to do first?",
         "hinglish": "Thanks {name}. Pehle kya karna hai — search, compare ya support?"},
    ],
    "collect_machine_requirements": [
        {"id": "cmr_a", "style": "direct", "use_name": False,
         "english": "Sure. What work do you need the machine for, and which city is the project in?",
         "hinglish": "Theek hai. Kaunsa kaam hai aur project kis city me hai?"},
        {"id": "cmr_b", "style": "helpful", "use_name": False,
         "english": "I can help with that. Tell me the work type and location first.",
         "hinglish": "Main help kar sakta hoon. Pehle work type aur city bata dein."},
        {"id": "cmr_c", "style": "professional", "use_name": True,
         "english": "Before I suggest equipment, {name}, I need the job type and city.",
         "hinglish": "Equipment suggest karne se pehle, {name}, job type aur city chahiye."},
        {"id": "cmr_d", "style": "helpful", "use_name": False,
         "english": "No problem. Share the work requirement and city, and I will narrow down suitable machines.",
         "hinglish": "Koi problem nahi. Work requirement aur city share karein, main suitable machines suggest karunga."},
    ],
    "ask_city": [
        {"id": "city_a", "style": "direct", "use_name": False,
         "english": "Got it. Which city is your site in?",
         "hinglish": "Theek hai. Site kaunse sheher me hai?"},
        {"id": "city_b", "style": "helpful", "use_name": True,
         "english": "Understood, {name}. Which city should I search in?",
         "hinglish": "Samajh gaya, {name}. Kaunsi city me search karun?"},
        {"id": "city_c", "style": "direct", "use_name": False,
         "english": "Which city do you need the machine in?",
         "hinglish": "Kaunsi city me machine chahiye?"},
    ],
    "ask_purpose": [
        {"id": "pur_a", "style": "direct", "use_name": False,
         "english": "What type of work is the machine for — digging, lifting, compaction, transport, or loading?",
         "hinglish": "Kaunsa kaam hai — digging, lifting, compaction, transport ya loading?"},
        {"id": "pur_b", "style": "helpful", "use_name": False,
         "english": "Tell me the work type so I can suggest the right equipment category.",
         "hinglish": "Work type bata dein taaki sahi equipment category suggest kar sakun."},
    ],
    "collect_transaction_id": [
        {"id": "txn_a", "style": "empathetic", "use_name": False,
         "english": "I understand this is frustrating. Please share your booking ID or transaction ID so I can guide you correctly.",
         "hinglish": "Samajh sakta hoon. Booking ID ya transaction ID share karein taaki sahi guide kar sakun."},
        {"id": "txn_b", "style": "professional", "use_name": True,
         "english": "I can help with the payment issue, {name}. Share your booking or transaction ID when you have it.",
         "hinglish": "Payment issue me help kar sakta hoon, {name}. Booking ya transaction ID share karein."},
        {"id": "txn_c", "style": "empathetic", "use_name": False,
         "english": "Sorry you are facing this. A booking ID or registered mobile number will help us check the status.",
         "hinglish": "Sorry for the trouble. Booking ID ya registered mobile number se status check ho sakta hai."},
    ],
    "collect_booking_id": [
        {"id": "book_a", "style": "empathetic", "use_name": False,
         "english": "I can help with that. Please share your booking or order ID.",
         "hinglish": "Main help kar sakta hoon. Booking ya order ID share karein."},
        {"id": "book_b", "style": "professional", "use_name": True,
         "english": "To proceed, {name}, please share your booking ID or registered mobile number.",
         "hinglish": "Aage badhne ke liye, {name}, booking ID ya registered mobile number chahiye."},
    ],
    "offer_handover": [
        {"id": "hand_a", "style": "professional", "use_name": False,
         "english": "I can connect you with InfraForge support for this. Use Call, WhatsApp, or Raise Request below.",
         "hinglish": "Iske liye support se connect kar sakte hain. Neeche Call, WhatsApp ya Raise Request use karein."},
        {"id": "hand_b", "style": "empathetic", "use_name": True,
         "english": "Let me get you to the right team, {name}. Support options are below.",
         "hinglish": "Sahi team tak pahunchata hoon, {name}. Support options neeche hain."},
    ],
    "out_of_scope_boundary": [
        {"id": "oos_a", "style": "polite", "use_name": False,
         "english": "I focus on InfraForge marketplace — machines, rent/buy, booking, and support. How can I help with that?",
         "hinglish": "Main InfraForge marketplace me help karta hoon — machines, rent/buy, booking, support."},
        {"id": "oos_b", "style": "polite", "use_name": False,
         "english": "That is outside what I can help with here. I can assist with construction machine search and marketplace support.",
         "hinglish": "Ye mere scope se bahar hai. Main construction machine search aur marketplace support me help kar sakta hoon."},
    ],
    "continue_followup": [
        {"id": "cont_a", "style": "helpful", "use_name": False,
         "english": "I am not fully sure yet. Can you tell me what you need — machine search, booking help, or support?",
         "hinglish": "Poora clear nahi hai. Machine search, booking help ya support — kya chahiye?"},
        {"id": "cont_b", "style": "helpful", "use_name": True,
         "english": "Could you clarify what you would like to do next, {name}?",
         "hinglish": "Agla step clarify kar dein, {name}?"},
    ],
    "respond_wellbeing": [
        {"id": "wb_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "respond_conversational": [
        {"id": "conv_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "respond_appreciation": [
        {"id": "app_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "respond_gratitude": [
        {"id": "grat_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "respond_satisfaction": [
        {"id": "sat_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "respond_flow_ack": [
        {"id": "flow_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "domain_knowledge_answer": [
        {"id": "dk_a", "style": "informative", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "assistant_identity": [
        {"id": "id_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "explain_no_result": [
        {"id": "nor_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "nor_b", "style": "empathetic", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "explain_no_result_with_recovery": [
        {"id": "nor_rec_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "nor_rec_b", "style": "empathetic", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "suggest_similar_machines": [
        {"id": "sim_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "show_machine_results": [
        {"id": "res_a", "style": "direct", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "answer_document_question": [
        {"id": "doc_a", "style": "professional", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "ask_image_clarification": [
        {"id": "img_a", "style": "helpful", "use_name": False,
         "english": "Please upload a clear machine photo or tell me the machine type and city.",
         "hinglish": "Clear machine photo upload karein ya machine type aur city bata dein."},
    ],
    "ask_document_upload": [
        {"id": "du_a", "style": "helpful", "use_name": False,
         "english": "Upload a PDF or document in this chat first, then ask your question about it.",
         "hinglish": "Pehle PDF/document upload karein, phir uske baare me poochiye."},
        {"id": "du_b", "style": "direct", "use_name": False,
         "english": "I need a document first — upload a PDF, then I can answer questions from it.",
         "hinglish": "Pehle document upload karein, phir main usse related questions answer kar sakta hoon."},
    ],
    "show_brand_inventory": [
        {"id": "brand_a", "style": "direct", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "brand_b", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "brand_c", "style": "professional", "use_name": True,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "check_brand_availability": [
        {"id": "bav_a", "style": "direct", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "bav_b", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "show_comparison": [
        {"id": "cmp_a", "style": "direct", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "cmp_b", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "cmp_c", "style": "professional", "use_name": True,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "frustration_recovery": [
        {"id": "fr_a", "style": "empathetic", "use_name": False,
         "english": "I understand this is frustrating. I am here to help — share your booking ID or tell me what went wrong.",
         "hinglish": "Samajh sakta hoon ye frustrating hai. Main help ke liye hoon — booking ID share karein ya problem bata dein."},
        {"id": "fr_b", "style": "empathetic", "use_name": True,
         "english": "Sorry about the trouble, {name}. Let us fix this — share booking details or pick support below.",
         "hinglish": "Sorry for trouble, {name}. Isko fix karte hain — booking details share karein ya support choose karein."},
        {"id": "fr_c", "style": "empathetic", "use_name": False,
         "english": "I hear you. Tell me the issue or booking ID and I will guide you to the right next step.",
         "hinglish": "Sun liya. Issue ya booking ID bata dein, main sahi next step guide karunga."},
    ],
    "continue_pending_flow": [
        {"id": "pend_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "pend_b", "style": "direct", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "pend_c", "style": "warm", "use_name": True,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "recommendation_clarification": [
        {"id": "rec_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "rec_b", "style": "guiding", "use_name": False,
         "english": "To recommend the right machines, tell me your project type — road work, building, earthwork, or compaction.",
         "hinglish": "Sahi machines recommend karne ke liye project type bata dein — road work, building, earthwork ya compaction."},
        {"id": "rec_c", "style": "warm", "use_name": True,
         "english": "{name}, what kind of project is this — road, building, earthwork, or compaction?",
         "hinglish": "{name}, project kis type ka hai — road, building, earthwork ya compaction?"},
    ],
    "ask_followup_context": [
        {"id": "afu_a", "style": "helpful", "use_name": False,
         "english": "What would you like to do next — refine search, compare, or contact owner?",
         "hinglish": "Agla step kya hai — search refine, compare ya owner contact?"},
        {"id": "afu_b", "style": "direct", "use_name": True,
         "english": "Happy to continue, {name}. Pick an option below or tell me what you need.",
         "hinglish": "Continue kar sakte hain, {name}. Neeche option choose karein ya bata dein kya chahiye."},
    ],
    "support_collect_details": [
        {"id": "sup_a", "style": "empathetic", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "sup_b", "style": "professional", "use_name": True,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "support_recovery": [
        {"id": "sr_a", "style": "empathetic", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "sr_b", "style": "empathetic", "use_name": False,
         "english": "I can help with this. Share your booking or transaction ID — I will not claim any status until verified.",
         "hinglish": "Main help kar sakta hoon. Booking ya transaction ID share karein — verified status tabhi batayenge."},
    ],
    "clarify_unknown": [
        {"id": "unk_a", "style": "helpful", "use_name": False,
         "english": "I am not fully sure yet. Can you tell me — machine search, booking help, or support?",
         "hinglish": "Poora clear nahi hai. Machine search, booking help ya support — kya chahiye?"},
        {"id": "unk_b", "style": "guiding", "use_name": True,
         "english": "Could you clarify what you need, {name}? I can help with machines, rent/buy, or support.",
         "hinglish": "Clarify kar dein kya chahiye, {name}? Machines, rent/buy ya support me help kar sakta hoon."},
        {"id": "unk_c", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "meta_help": [
        {"id": "mh_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "memory_answer": [
        {"id": "mem_a", "style": "warm", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "support_guidance": [
        {"id": "sg_a", "style": "professional", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
        {"id": "sg_b", "style": "empathetic", "use_name": True,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "offer_handover": [
        {"id": "oh_a", "style": "professional", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "explain_security_deposit": [
        {"id": "dep_a", "style": "professional", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
    "explain_rental_process": [
        {"id": "rent_a", "style": "helpful", "use_name": False,
         "english": "{draft}", "hinglish": "{draft}"},
    ],
}


def _lang_key(language: str) -> str:
    lang = (language or "english").lower()
    return "hinglish" if lang in ("hinglish", "hindi") else "english"


def _variant_signature(variant_id: str, response_goal: str) -> str:
    return hashlib.sha256(f"{response_goal}|{variant_id}".encode()).hexdigest()[:16]


def _pick_variant(
    *,
    session_id: str,
    response_goal: str,
    session_context: dict[str, Any],
    sentiment: str = "neutral",
    draft: str = "",
    language: str = "english",
    name: str | None = None,
) -> Variant:
    variants = _VARIANTS.get(response_goal)
    if not variants:
        if draft.strip():
            variants = [{"id": "draft_fallback", "style": "helpful", "use_name": False,
                         "english": "{draft}", "hinglish": "{draft}"}]
        else:
            variants = _VARIANTS["clarify_unknown"]
    recent_ids: list[str] = list(session_context.get("recent_variant_ids") or [])[-3:]
    recent_sigs: list[str] = list(
        session_context.get("recent_response_signatures")
        or session_context.get("avoid_repeating")
        or []
    )[-3:]

    candidates = [v for v in variants if v["id"] not in recent_ids] or variants

    if sentiment == "frustrated":
        empathetic = [v for v in candidates if v.get("style") == "empathetic"]
        if empathetic:
            candidates = empathetic

    lang = _lang_key(language)
    non_repeat: list[Variant] = []
    for v in candidates:
        template = v.get(lang) or v.get("english") or ""
        msg = _format_template(template, name=name, draft=draft, use_name=bool(v.get("use_name")))
        sig = hashlib.sha256(f"{response_goal}|{msg.strip().lower()[:200]}".encode()).hexdigest()[:16]
        if sig not in recent_sigs and _variant_signature(v["id"], response_goal) not in recent_sigs:
            non_repeat.append(v)
    if non_repeat:
        candidates = non_repeat

    turn = int(session_context.get("turn_count") or 0)
    msg_seed = hashlib.sha256((session_context.get("last_user_message") or "").encode()).hexdigest()[:8]
    seed = f"{session_id}|{response_goal}|{turn}|{len(recent_ids)}|{len(recent_sigs)}|{msg_seed}"
    idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(candidates)
    return candidates[idx]


def _format_template(template: str, *, name: Optional[str], draft: str = "", use_name: bool = False) -> str:
    out = template.replace("{draft}", draft)
    if use_name and name:
        out = out.replace("{name}", name)
    else:
        out = out.replace(", {name}", "").replace("{name}, ", "").replace("{name}", "")
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = out.replace(" ,", ",").replace(",.", ".")
    return out


def generate_conversation_aware_response(
    *,
    intent: str,
    assistant_mode: str,
    response_goal: str,
    entities: Optional[dict[str, Any]] = None,
    missing_fields: Optional[list[str]] = None,
    tool_result: Optional[dict[str, Any]] = None,
    session_context: Optional[dict[str, Any]] = None,
    previous_turns: Optional[list[dict]] = None,
    language: str = "english",
    sentiment: str = "neutral",
    session_id: str = "",
    draft_message: str = "",
) -> dict[str, Any]:
    ctx = session_context or {}
    ents = entities or {}
    tool = tool_result or {}
    name = ents.get("name") or ctx.get("user_name")
    draft = draft_message or tool.get("message") or ""
    ctx = {**ctx, "last_user_message": ctx.get("last_user_message") or draft[:80]}

    variant = _pick_variant(
        session_id=session_id or ctx.get("session_id", "default"),
        response_goal=response_goal,
        session_context=ctx,
        sentiment=sentiment,
        draft=draft,
        language=language,
        name=name,
    )

    lang = _lang_key(language)
    template = variant.get(lang) or variant.get("english") or draft

    if response_goal in _FACTUAL_DRAFT_GOALS and draft.strip():
        message = draft
        if sentiment in ("frustrated", "urgent") and response_goal in _EMPATHY_PREFIX:
            message = _EMPATHY_PREFIX[response_goal] + draft
    else:
        message = _format_template(
            template,
            name=name,
            draft=draft,
            use_name=bool(variant.get("use_name")),
        )
        if not message and draft:
            message = draft

    suggestions = list(_SUGGESTIONS.get(response_goal) or [])
    if tool.get("suggestions"):
        suggestions = list(tool.get("suggestions") or [])

    preserve = tool.get("preserve_machine_panel")
    if preserve is None:
        preserve = bool(tool.get("machines"))

    return {
        "message": message,
        "suggestions": suggestions[:8],
        "response_style": variant.get("style", "professional"),
        "response_variant_id": variant.get("id"),
        "next_best_action": tool.get("next_best_action") or response_goal,
        "preserve_machine_panel": preserve,
        "response_goal": response_goal,
    }


async def finalize_assistant_reply(
    *,
    draft_message: str,
    intent: str,
    assistant_mode: str,
    response_goal: str,
    entities: Optional[dict] = None,
    missing_fields: Optional[list] = None,
    tool_result: Optional[dict] = None,
    session_context: Optional[dict] = None,
    language: str = "english",
    sentiment: str = "neutral",
    session_id: str = "",
    user_query: str = "",
    classification: Optional[dict] = None,
) -> dict[str, Any]:
    """Response Plan -> dynamic LLM/fallback -> memory."""
    from app.ai.assistant_response_gateway import deliver_assistant_response

    ctx = dict(session_context or {})
    result = await deliver_assistant_response(
        session_id=session_id or ctx.get("session_id") or "default",
        user_message=user_query,
        draft_message=draft_message,
        response_goal=response_goal,
        intent=intent,
        assistant_mode=assistant_mode,
        session_context=ctx,
        classification=classification,
        entities=entities,
        missing_fields=missing_fields,
        tool_result=tool_result,
        language=language,
        sentiment=sentiment,
    )
    from app.ai.response_safety_guard import apply_false_claim_guard, build_fact_constraints
    from app.ai.context_routing_gate import get_current_gate

    known = {
        "collected_fields": (ctx.get("conversation_state") or {}).get("collected_fields") or {},
        "last_support_context": (ctx.get("conversation_state") or {}).get("last_support_context") or {},
        "selected_machine": ctx.get("selected_machine") or (ctx.get("conversation_state") or {}).get("selected_machine"),
    }
    constraints = build_fact_constraints(
        intent=intent,
        response_goal=response_goal,
        known_context=known,
        tool_result=tool_result,
        intent_family=(get_current_gate() or {}).get("family"),
    )
    message, guard_applied = apply_false_claim_guard(
        result.get("message") or draft_message,
        constraints=constraints,
    )
    if guard_applied:
        try:
            from app.ai.assistant_debug_trace import record_context_routing
            record_context_routing({"false_claim_guard_applied": True})
        except Exception:
            pass
    return {
        "message": message,
        "suggestions": result.get("suggestions") or [],
        "response_style": result.get("response_style", "professional"),
        "response_variant_id": result.get("response_variant_id") or result.get("response_signature"),
        "response_signature": result.get("response_signature"),
        "next_best_action": result.get("next_best_action") or response_goal,
        "preserve_machine_panel": result.get("preserve_machine_panel", False),
        "response_goal": response_goal,
        "llm_polish_used": bool(result.get("llm_generated")),
        "llm_generated": bool(result.get("llm_generated")),
        "fallback_used": bool(result.get("fallback_used")),
        "updated_session_context": result.get("updated_session_context"),
        "response_plan": result.get("response_plan"),
    }


def log_response_debug(
    *,
    normalized_message: str,
    classification: dict[str, Any],
    response: dict[str, Any],
    action: str = "",
    tool: str = "",
    validation_errors: Optional[list] = None,
) -> None:
    if settings.ENVIRONMENT not in ("development", "dev", "local"):
        return
    print(
        "[response_debug]",
        f"msg={normalized_message[:80]!r}",
        f"intent={classification.get('llm_intent') or classification.get('intent')}",
        f"confidence={classification.get('confidence')}",
        f"mode={classification.get('assistant_mode')}",
        f"goal={response.get('response_goal')}",
        f"variant={response.get('response_variant_id') or response.get('response_signature')}",
        f"style={response.get('response_style')}",
        f"action={action}",
        f"tool={tool}",
        f"llm={response.get('llm_generated')}",
        f"fallback={response.get('fallback_used')}",
        f"polish={response.get('llm_polish_used')}",
        f"validation_errors={validation_errors or classification.get('validation_notes')}",
    )
