"""
Suggestion chip resolver - maps UI suggestion labels to executable user actions.

Mechanism-level: every chip from GOAL_SUGGESTIONS / support flows resolves to a
sendable message or UI action using session context (not phrase-specific hacks).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.response_plan import GOAL_SUGGESTIONS
from app.ai.image_turn_models import all_image_clarification_chips, image_chip_to_intent

# Chips that open UI affordances instead of sending chat text
UI_ACTION_CHIPS: dict[str, str] = {
    "Upload image": "open_image_picker",
    "Upload clearer image": "open_image_picker",
    "Voice search": "open_voice",
    "Document Q&A": "open_document",
    "Upload document": "open_document",
    "Upload PDF": "open_document",
    "Raise request": "open_support_modal",
    "Raise Request": "open_support_modal",
    "Call support": "open_support_modal",
    "WhatsApp": "open_support_modal",
}

# Static send-text for chips without session context
_STATIC_CHIP_MESSAGES: dict[str, str] = {
    "Search Machine": "excavator in jaipur",
    "Search machine": "excavator in jaipur",
    "Ask recommendation": "road project ke liye best machine kaunsi hai?",
    "Contact support": "I need help from support",
    "Talk to support": "I need help from support",
    "Booking issue": "booking me issue hai",
    "Order issue": "I ordered a machine and I have a problem",
    "Refund/Return": "I want refund",
    "Payment issue": "payment failed amount deducted",
    "Booking policy": "What is the rental cancellation policy?",
    "Share booking ID": "My booking ID is ",
    "Share transaction ID": "My transaction ID is ",
    "Share order ID": "My order ID is ",
    "Digging": "excavator for digging work",
    "Lifting": "crane for lifting work",
    "Compaction": "road roller for compaction",
    "Loading": "wheel loader for loading",
    "Transport": "dump truck for transport",
    "Road work": "road work ke liye machine chahiye",
    "Building": "building construction ke liye machine chahiye",
    "Earthwork": "earthwork ke liye machine chahiye",
    "Jaipur": "machines in Jaipur",
    "Delhi": "machines in Delhi",
    "Mumbai": "machines in Mumbai",
    "Pune": "machines in Pune",
    "Excavator": "excavator",
    "Road Roller": "road roller",
    "Crane": "crane",
    "Backhoe Loader": "backhoe loader",
    "Rent only": "show rent only listings",
    "Show cheaper options": "show cheaper options",
    "Compare machines": "compare machines from my last search",
    "Contact owner": "how do I contact the owner",
    "Search nearby cities": "search in nearby cities",
    "Try similar machines": "show similar machines",
    "Increase budget": "show options with higher budget",
    "Show other brands": "show other brands",
    "Search by text": "excavator in jaipur",
    "Select machine type": "excavator",
    "Compare brands": "compare JCB vs CAT excavators",
    "Tell city for listings": "Which city should I search for machine listings?",
}


def _normalize_chip_key(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip().lower())


# Normalize chip label for lookup (case/spacing tolerant)
_CHIP_ALIASES: dict[str, str] = {}
for chips in GOAL_SUGGESTIONS.values():
    for chip in chips:
        key = _normalize_chip_key(chip)
        _CHIP_ALIASES.setdefault(key, chip)
for chip in _STATIC_CHIP_MESSAGES:
    _CHIP_ALIASES.setdefault(_normalize_chip_key(chip), chip)
for chip in UI_ACTION_CHIPS:
    _CHIP_ALIASES.setdefault(_normalize_chip_key(chip), chip)
for chip in all_image_clarification_chips():
    _CHIP_ALIASES.setdefault(_normalize_chip_key(chip), chip)


def all_known_chips() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for chip in list(_STATIC_CHIP_MESSAGES) + list(UI_ACTION_CHIPS) + [
        c for chips in GOAL_SUGGESTIONS.values() for c in chips
    ]:
        key = _normalize_chip_key(chip)
        if key not in seen:
            seen.add(key)
            out.append(chip)
    return out


def is_suggestion_chip(message: str) -> bool:
    key = _normalize_chip_key(message)
    return key in _CHIP_ALIASES or key in {
        _normalize_chip_key(k) for k in _STATIC_CHIP_MESSAGES
    }


def _last_knowledge_context(session_ctx: dict[str, Any]) -> dict[str, Any]:
    conv = session_ctx.get("conversation_state") or session_ctx.get("_conversation_state") or {}
    return (
        conv.get("last_knowledge_context")
        or session_ctx.get("last_knowledge_context")
        or {}
    )


def _last_search_filters(session_ctx: dict[str, Any]) -> dict[str, Any]:
    conv = session_ctx.get("conversation_state") or session_ctx.get("_conversation_state") or {}
    return (
        conv.get("last_search_filters")
        or session_ctx.get("last_search_filters")
        or session_ctx.get("last_filters")
        or {}
    )


def _machine_label(knowledge: dict[str, Any]) -> str:
    if knowledge.get("display_name"):
        return str(knowledge["display_name"])
    parts = [p for p in (knowledge.get("brand"), knowledge.get("model")) if p]
    if parts:
        return " ".join(parts)
    cat = knowledge.get("category") or knowledge.get("subject")
    return str(cat or "this machine")


def _last_image_context(session_ctx: dict[str, Any]) -> dict[str, Any]:
    conv = session_ctx.get("conversation_state") or session_ctx.get("_conversation_state") or {}
    img = conv.get("last_image_context") or session_ctx.get("last_image_context") or {}
    if img:
        return img
    session_id = (session_ctx.get("session_id") or "").strip()
    if session_id:
        from app.chatbot.image_context_memory import get_image_context
        return get_image_context(session_id) or {}
    return {}


def _contextual_message(chip_key: str, session_ctx: dict[str, Any]) -> Optional[str]:
    knowledge = _last_knowledge_context(session_ctx)
    filters = _last_search_filters(session_ctx)
    image_ctx = _last_image_context(session_ctx)
    machine = _machine_label(knowledge) if knowledge else ""
    city = filters.get("city") or knowledge.get("city") or image_ctx.get("user_city") or ""
    category = (
        filters.get("category")
        or knowledge.get("category")
        or knowledge.get("subject")
        or image_ctx.get("detected_category")
        or ""
    )
    brand = knowledge.get("brand") or filters.get("brand") or image_ctx.get("detected_brand") or ""

    chip_intent = image_chip_to_intent(chip_key) or image_chip_to_intent(
        _CHIP_ALIASES.get(chip_key, chip_key)
    )
    if chip_intent and image_ctx.get("detected_category"):
        parts = []
        if chip_intent == "similar_category":
            parts.append("similar")
        elif chip_intent == "exact_match":
            parts.append("exact same")
        elif chip_intent == "identify_only":
            return "which machine is this"
        if brand:
            parts.append(brand)
        parts.append(image_ctx.get("detected_category") or category)
        if city:
            parts.append(f"in {city}")
        return " ".join(p for p in parts if p).strip()

    if chip_key == _normalize_chip_key("Search this machine"):
        if machine:
            return f"search {machine}" + (f" in {city}" if city else "")
        if brand and category:
            return f"search {brand} {category}" + (f" in {city}" if city else "")
        return _STATIC_CHIP_MESSAGES.get("Search Machine")

    if chip_key == _normalize_chip_key("Compare brands"):
        if brand and machine:
            other = "Komatsu" if brand.lower() in ("jcb", "cat", "caterpillar") else "JCB"
            return f"compare {brand} vs {other}" + (f" {category}" if category else "")
        return _STATIC_CHIP_MESSAGES.get("Compare brands")

    if chip_key == _normalize_chip_key("Ask recommendation"):
        if category or machine:
            target = category or machine
            return f"recommend best {target}" + (f" for work in {city}" if city else " for my project")
        return _STATIC_CHIP_MESSAGES.get("Ask recommendation")

    if chip_key == _normalize_chip_key("Show cheaper options"):
        base = category or machine or "machines"
        loc = f" in {city}" if city else ""
        return f"show cheaper {base} options{loc}"

    if chip_key == _normalize_chip_key("Tell city for listings"):
        return "Which city should I search for machine listings?"

    return None


def resolve_suggestion_chip(
    chip_label: str,
    *,
    session_ctx: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Resolve a suggestion chip to an executable action.

    Returns:
        action: send_message | ui_action
        message: text to send (when action=send_message)
        ui_action: picker/modal id (when action=ui_action)
        intent_hint: optional routing hint
        chip: canonical chip label
    """
    raw = (chip_label or "").strip()
    key = _normalize_chip_key(raw)
    canonical = _CHIP_ALIASES.get(key, raw)
    ctx = session_ctx or {}

    ui = UI_ACTION_CHIPS.get(canonical) or UI_ACTION_CHIPS.get(raw)
    if ui:
        return {
            "action": "ui_action",
            "ui_action": ui,
            "message": "",
            "intent_hint": None,
            "chip": canonical,
            "from_suggestion_chip": True,
        }

    contextual = _contextual_message(key, ctx)
    if contextual:
        hint = "machine_search"
        if key == _normalize_chip_key("Compare brands"):
            hint = "comparison"
        elif key == _normalize_chip_key("Ask recommendation"):
            hint = "recommendation"
        elif key == _normalize_chip_key("Contact support"):
            hint = "support"
        return {
            "action": "send_message",
            "message": contextual,
            "ui_action": None,
            "intent_hint": hint,
            "chip": canonical,
            "from_suggestion_chip": True,
        }

    for label, msg in _STATIC_CHIP_MESSAGES.items():
        if _normalize_chip_key(label) == key:
            hint = None
            if "support" in key or key in (
                _normalize_chip_key("Booking issue"),
                _normalize_chip_key("Refund/Return"),
                _normalize_chip_key("Payment issue"),
            ):
                hint = "support"
            elif "recommend" in key:
                hint = "recommendation"
            elif "compare" in key:
                hint = "comparison"
            elif key in (
                _normalize_chip_key("Search Machine"),
                _normalize_chip_key("Search machine"),
                _normalize_chip_key("Show cheaper options"),
            ):
                hint = "machine_search"
            return {
                "action": "send_message",
                "message": msg,
                "ui_action": None,
                "intent_hint": hint,
                "chip": label,
                "from_suggestion_chip": True,
            }

    return {
        "action": "send_message",
        "message": raw,
        "ui_action": None,
        "intent_hint": None,
        "chip": raw,
        "from_suggestion_chip": True,
    }


def save_knowledge_context(
    state: dict[str, Any],
    knowledge_turn: dict[str, Any],
) -> None:
    """Persist last discussed machine/brand for contextual suggestion chips."""
    if not knowledge_turn:
        return
    payload = {
        k: knowledge_turn.get(k)
        for k in (
            "kind", "brand", "model", "category", "display_name",
            "subject", "subject_type", "city",
        )
        if knowledge_turn.get(k)
    }
    if payload:
        state["last_knowledge_context"] = payload
