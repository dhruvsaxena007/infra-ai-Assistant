"""
Central catalog-driven entity resolver for marketplace queries.

Order: normalize → Hindi/Hinglish → exact category → aliases → brand → model
→ model-implied category → conflict resolution → confidence notes.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.brand_catalog import detect_brand as catalog_detect_brand
from app.ai.category_mapping import (
    canonicalize_category,
    detect_model,
    detect_requested_category,
)
from app.ai.query_parser import parse_query

_MODEL_IMPLIED_CATEGORY: dict[str, str] = {
    "3dx": "backhoe loader",
    "4dx": "backhoe loader",
    "2dx": "backhoe loader",
    "320d": "excavator",
    "pc200": "excavator",
}

_INVENTORY_LIST_RE = re.compile(
    r"\b(?:which\s+brands?|what\s+brands?|konse?\s+brands?|brands?\s+(?:for|in|available)|"
    r"categories?\s+for\s+brand|list\s+(?:all\s+)?brands?)\b",
    re.I,
)
_MARKETPLACE_SEARCH_RE = re.compile(
    r"\b(?:rent|buy|hire|kiraye|kiraya|chahiye|dikhao|available|need|want|search|find|show|"
    r"milega|milta|milegi|dikhado|book|listing)\b",
    re.I,
)
_CITY_IN_PHRASE_RE = re.compile(r"\b(?:in|me|mai|near|around|ke?\s+liye)\b", re.I)


def resolve_entities(
    message: str,
    *,
    parsed: dict | None = None,
    session_context: dict | None = None,
) -> dict[str, Any]:
    """Resolve category, brand, model, city, listing_type, budget from message."""
    text = (message or "").strip()
    p = dict(parsed or parse_query(text))
    notes: list[str] = []
    confidence = 0.6

    category = p.get("category") or detect_requested_category(text)
    if category:
        category = canonicalize_category(category) or category
        confidence = max(confidence, 0.85)

    brand = p.get("brand") or catalog_detect_brand(text)
    model = p.get("model") or detect_model(text)
    city = p.get("city")
    listing_type = p.get("listing_type")
    budget = p.get("max_price")

    if model and not category:
        implied = _MODEL_IMPLIED_CATEGORY.get(str(model).lower().replace(" ", ""))
        if implied:
            category = implied
            notes.append(f"model_{model}_implies_{implied}")
            confidence = max(confidence, 0.75)

    if brand and category and p.get("category") and canonicalize_category(p["category"]) != category:
        if p.get("category"):
            category = canonicalize_category(p["category"]) or p["category"]
            notes.append("explicit_category_overrides_model_inference")
            confidence = max(confidence, 0.9)

    intent_shape = _classify_search_shape(text, p, brand=brand, category=category, city=city)

    return {
        "category": category,
        "brand": brand,
        "model": model,
        "city": city,
        "listing_type": listing_type,
        "budget": budget,
        "max_price": budget,
        "brands": p.get("brands") or ([brand] if brand else []),
        "intent_shape": intent_shape,
        "confidence": confidence,
        "validation_notes": notes,
        "parsed": p,
    }


def _classify_search_shape(
    text: str,
    parsed: dict,
    *,
    brand: str | None,
    category: str | None,
    city: str | None,
) -> str:
    """Disambiguate brand inventory vs brand-filtered machine search."""
    if _INVENTORY_LIST_RE.search(text):
        return "brand_inventory"
    if brand and not category:
        if city or _CITY_IN_PHRASE_RE.search(text):
            if _MARKETPLACE_SEARCH_RE.search(text) or len(text.split()) <= 6:
                return "brand_or_model_search"
        if _MARKETPLACE_SEARCH_RE.search(text):
            return "brand_or_model_search"
        ctx = parsed
        if ctx.get("listing_type") or ctx.get("max_price") is not None:
            return "brand_or_model_search"
    if category or city or brand:
        return "machine_search"
    return "unknown"


def is_brand_marketplace_search(
    message: str,
    parsed: dict | None = None,
) -> bool:
    """True when brand (+ optional city) signals a listing search, not inventory."""
    resolved = resolve_entities(message, parsed=parsed)
    return resolved.get("intent_shape") == "brand_or_model_search"
