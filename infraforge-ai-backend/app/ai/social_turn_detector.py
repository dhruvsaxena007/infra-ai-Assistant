"""
Unified social / appreciation / satisfaction turn detection.

Single authority for short conversational turns that must NOT be routed to
capability boundaries or generic intro templates.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.query_parser import parse_query

_APPRECIATION_RE = re.compile(
    r"(?:"
    r"\b(?:good(?:\s+job|\s+work|\s+one)?|great|awesome|superb|excellent|"
    r"perfect|nice|amazing|helpful|useful|well\s+done|nice\s+one|fantastic)\b|"
    r"\byou(?:'re|\s+are)\s+(?:good|great|awesome|helpful|amazing|the\s+best)\b|"
    r"\b(?:bahut|bohot)\s+(?:accha|achha|badhiya|badiya)\b"
    r")",
    re.I,
)

_SATISFACTION_ACK_RE = re.compile(
    r"^(?:"
    r"ok(?:ay)?(?:\s+(?:good|nice|perfect|great|fine|cool|thanks|thank\s+you))?|"
    r"good|nice|perfect|great|cool|fine|sounds\s+good|"
    r"theek(?:\s+hai|\s+lag(?:ta|r)\s+hai)?|"
    r"achha(?:\s+hai|\s+lag(?:ta|r)\s+hai)?|"
    r"satisfied|works\s+for\s+me|"
    r"(?:that(?:'s|\s+is)|this(?:'s|\s+is))\s+(?:good|great|perfect|fine|helpful|nice)"
    r")[\s!.?]*$",
    re.I,
)

_FLOW_ACK_RE = re.compile(
    r"^(?:"
    r"ok(?:ay)?|yes|yeah|yep|yup|sure|fine|cool|right|"
    r"haan|ha|ji|theek(?:\s*hai)?|thik(?:\s*hai)?|"
    r"continue|go\s+ahead|proceed|got\s*it|understood|samajh\s+gaya"
    r")[\s!.?]*$",
    re.I,
)

_SEARCH_SHAPE_RE = re.compile(
    r"\b(?:"
    r"search|find|show|need|want|rent|buy|purchase|hire|excavator|crane|"
    r"roller|loader|machine|equipment|jaipur|delhi|mumbai|compare|price"
    r")\b",
    re.I,
)


def _has_recent_machine_context(ctx: dict | None) -> bool:
    if not ctx:
        return False
    last = ctx.get("last_filters") or {}
    if last.get("category") or last.get("city") or last.get("brand"):
        return True
    if ctx.get("last_machines_count"):
        return True
    last_results = ctx.get("last_results") or {}
    if last_results.get("last_machines") or last_results.get("count"):
        return True
    collected = ctx.get("collected_fields") or {}
    if collected.get("category") or collected.get("city"):
        return True
    conv = ctx.get("conversation_state") or {}
    if conv.get("last_visible_results"):
        return True
    return False


def _response_goal_for_kind(kind: str) -> str:
    return {
        "thanks": "respond_gratitude",
        "appreciation": "respond_appreciation",
        "satisfaction": "respond_satisfaction",
        "wellbeing": "respond_wellbeing",
        "wellbeing_reciprocal": "respond_wellbeing",
        "user_state": "respond_wellbeing",
        "polite_social": "respond_appreciation",
        "flow_ack": "respond_flow_ack",
        "name_intro": "acknowledge_name",
        "assistant_identity": "assistant_identity",
        "greeting": "greet_user",
    }.get(kind, "respond_conversational")


def is_social_turn(message: str, ctx: Optional[dict] = None) -> bool:
    """True when the message is a social/conversational turn (not equipment search)."""
    return detect_social_turn(message, ctx) is not None


def detect_social_turn(
    message: str,
    ctx: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    """
    Return social turn metadata or None.
    Keys: kind, response_goal, confidence, has_machine_context, draft_hint
    """
    text = (message or "").strip()
    if not text:
        return None

    ctx = ctx or {}
    parsed = parse_query(text)
    has_machine_ctx = _has_recent_machine_context(ctx)
    pending = ctx.get("pending") or ctx.get("pending_clarification")

    if _SEARCH_SHAPE_RE.search(text) and len(text.split()) > 3:
        if not _APPRECIATION_RE.search(text) and not _SATISFACTION_ACK_RE.match(text):
            return None

    from app.chatbot.assistant_intelligence import is_greeting

    if is_greeting(text):
        return {
            "kind": "greeting",
            "subtype": "greeting",
            "response_goal": _response_goal_for_kind("greeting"),
            "confidence": 0.95,
            "has_machine_context": has_machine_ctx,
            "original_message": text,
        }

    from app.ai.knowledge_query_engine import knowledge_turn_from_message

    if knowledge_turn_from_message(text, parsed, session_ctx=ctx):
        return None

    from app.ai.universal_turn_engine import analyze_universal_turn

    turn = analyze_universal_turn(
        text,
        session_ctx=ctx,
        result_ctx=ctx.get("last_results") or {},
        last_filters=ctx.get("last_filters") or {},
        greeted=bool(ctx.get("greeted")),
    )
    if turn.get("shape") == "conversational":
        kind = turn.get("subtype") or "conversational"
        return {
            **turn,
            "kind": kind,
            "response_goal": _response_goal_for_kind(kind),
            "confidence": 0.9,
            "has_machine_context": has_machine_ctx,
        }

    if _APPRECIATION_RE.search(text) and not parsed.get("category") and not parsed.get("city"):
        return {
            "kind": "appreciation",
            "subtype": "appreciation",
            "response_goal": "respond_appreciation",
            "confidence": 0.88,
            "has_machine_context": has_machine_ctx,
            "original_message": text,
        }

    if _SATISFACTION_ACK_RE.match(text) and has_machine_ctx:
        return {
            "kind": "satisfaction",
            "subtype": "satisfaction",
            "response_goal": "respond_satisfaction",
            "confidence": 0.9,
            "has_machine_context": True,
            "original_message": text,
        }

    if _FLOW_ACK_RE.match(text) and (pending or has_machine_ctx):
        return {
            "kind": "flow_ack",
            "subtype": "flow_ack",
            "response_goal": "respond_flow_ack",
            "confidence": 0.85,
            "has_machine_context": has_machine_ctx,
            "original_message": text,
        }

    return None


def build_social_response_draft(
    social: dict[str, Any],
    *,
    lang: str = "english",
    user_name: str | None = None,
) -> dict[str, Any]:
    """Minimal factual draft — LLM polishes via response gateway."""
    from app.ai.assistant_brain import build_conversational_response, sanitize_display_name

    kind = social.get("kind") or social.get("subtype") or "conversational"
    name = sanitize_display_name(user_name or social.get("user_name"))

    if kind in ("thanks", "wellbeing", "wellbeing_reciprocal", "user_state", "polite_social", "name_intro", "assistant_identity", "greeting"):
        turn = {**social, "subtype": kind, "user_name": name}
        return build_conversational_response(turn, lang=lang)

    if kind == "appreciation":
        greet = f", {name}" if name else ""
        if lang == "hinglish":
            msg = (
                f"Shukriya{greet}! Main InfraForge par machine search, compare, rent/buy "
                f"aur support me madad ke liye hoon — jab chaho bata dena."
            )
        else:
            msg = (
                f"Thank you{greet}! Glad I could help. I'm here whenever you need "
                f"machine search, comparisons, rent/buy options, or platform support."
            )
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Compare machines", "Search another city", "Contact owner"],
        }

    if kind == "satisfaction":
        if lang == "hinglish":
            msg = (
                "Achha lagta hai! Agla step — owner se contact karein, compare karein, "
                "ya rent/buy filter laga kar aur options dekhein."
            )
        else:
            msg = (
                "Glad that works for you. You can contact the owner from the card, "
                "compare two listings, or filter results by rent vs buy when you're ready."
            )
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Contact owner", "Compare machines", "Show buy options"],
            "preserve_machines": True,
        }

    if kind == "flow_ack":
        if social.get("has_machine_context"):
            if lang == "hinglish":
                msg = "Theek hai! Cards se compare ya contact kar sakte ho — aur kuch chahiye ho to batao."
            else:
                msg = "Sounds good! Use the cards to compare or contact an owner — let me know if you need anything else."
            suggestions = ["Compare machines", "Contact owner", "Show cheaper options"]
        else:
            if lang == "hinglish":
                msg = "Theek hai! Machine type aur city bata do — main search start kar dunga."
            else:
                msg = "Got it! Tell me the machine type and city when you're ready and I'll search for you."
            suggestions = ["Search machine", "Ask recommendation", "Contact support"]
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": suggestions,
            "preserve_machines": bool(social.get("has_machine_context")),
        }

    return build_conversational_response({"subtype": kind, "user_name": name}, lang=lang)
