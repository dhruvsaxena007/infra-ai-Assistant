"""
Deterministic text understanding (rules-first).

Produces the same JSON shape as the legacy Groq `understand_user_text` helper so
routes can attach `text_understanding` without an extra LLM call.
"""

from __future__ import annotations

from app.ai.category_mapping import (
    detect_cheaper,
    detect_free_request,
    detect_list_all,
    detect_override,
    detect_requested_category,
)
from app.ai.query_parser import parse_query


def _detect_intent(message: str, filters: dict) -> str:
    if detect_free_request(message):
        return "free_request"
    if detect_list_all(message):
        return "list_all"
    if detect_override(message):
        return "override"
    if detect_cheaper(message):
        return "cheaper_options"
    lower = (message or "").lower()
    if any(p in lower for p in ("what about", "instead", "same in", "switch to")):
        return "city_switch"
    if filters.get("category") or filters.get("brand") or filters.get("city"):
        return "search"
    return "unknown"


def understand_user_text_rules(message: str) -> dict:
    """
    Rules-only understanding. Returns {success, data} compatible with Groq path.
    """
    message = (message or "").strip()
    if not message:
        return {"success": False, "error": "empty message"}

    filters = parse_query(message)
    category = filters.get("category")
    translated = message
    if category:
        translated = f"{category} {message}".strip()

    intent = _detect_intent(message, filters)

    return {
        "success": True,
        "data": {
            "original_message": message,
            "translated_query": translated,
            "machine_type": category or "",
            "brand": filters.get("brand") or "",
            "model": filters.get("model") or "",
            "city": filters.get("city") or "",
            "max_price": filters.get("max_price"),
            "min_price": None,
            "condition": filters.get("condition") or "",
            "pincode": filters.get("pincode") or "",
            "listing_type": filters.get("listing_type") or "",
            "rent_type": filters.get("rent_type") or "",
            "intent": intent,
            "is_follow_up": intent in ("city_switch", "cheaper_options", "override"),
            "source": "rules",
        },
    }
