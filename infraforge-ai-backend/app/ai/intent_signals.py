"""
Generalized intent signal detection for rules-first routing.

Uses Phase 2 parser entities (category, brand, brands) — not hardcoded example phrases.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import (
    detect_all_brands,
    detect_cheaper,
    detect_requested_category,
)
from app.ai.query_parser import parse_query
from app.chatbot.assistant_intelligence import (
    is_broad_vague_query,
    is_recommendation_query,
    resolve_purpose_key,
)

# ---------------------------------------------------------------------------
# Structural patterns (language families — not fixed sentences)
# ---------------------------------------------------------------------------

_BRAND_INVENTORY_RE = re.compile(
    r"(?:"
    r"which\s+brands?|what\s+brands?|brands?\s+(?:do\s+you\s+have|available|hai)|"
    r"konse?\s+brands?|kaun\s+kaun\s+se\s+brands?|"
    r"(?:companies?|makers?|manufacturers?)\s+(?:available|hai|hain|do\s+you\s+have)|"
    r"available\s+(?:brands?|companies?)|"
    r"(?:brand|company)\s+(?:list|options?)|"
    r"milta\s+hai\s+kya|available\s+hai|milega\s+kya|"
    r"ke\s+brands?\s+hai|ke\s+brand\s+hai"
    r")",
    re.I,
)

_COMPARISON_CONNECTOR_RE = re.compile(
    r"\b(?:vs\.?|versus|compare|comparison|better|best|prefer|acch[ae]|behtar|"
    r"or|ya|aur|difference\s+between)\b",
    re.I,
)

_COMPARISON_SIGNAL_RE = re.compile(
    r"(?:"
    r"\bcompare\b|comparison|versus|\bvs\.?\b|"
    r"(?:better|best|prefer|acch[ae]|behtar|badiya|badhiya)\b.{0,60}\b(?:or|ya|aur)\b|"
    r"\b(?:or|ya|aur)\b.{0,60}\b(?:better|best|acch[ae]|behtar|badiya|badhiya)\b|"
    r"(?:badiya|badhiya|acch[ae]|behtar)\s*(?:hote|hai|hain|hoti|hot)?\s*(?:hai|hain)?\s*(?:ya|or)\b|"
    r"which\s+is\s+better|kaun\s+sa\s+(?:better|acch[ae]|behtar|badiya)|"
    r"which\s+(?:company|brand).{0,40}(?:better|acch[ae]|badiya|behtar)|"
    r"difference\s+between|"
    r"\b(?:backhoe|excavator|roller|compactor|crane|loader|bulldozer)\b.{0,40}\b(?:or|ya|vs\.?|versus)\b.{0,40}\b(?:backhoe|excavator|roller|compactor|crane|loader|bulldozer)\b|"
    r"(?:for|ke\s+liye).{0,30}(?:digging|compaction|lifting|transport|loading|earthwork)"
    r")",
    re.I,
)

_HIGHER_BUDGET_RE = re.compile(
    r"(?:"
    r"higher\s+budget|high\s+budget|premium\s+option|expensive\s+option|"
    r"budget\s+badh|badha\s+du|price\s+badh|thoda\s+expensive|thoda\s+mehnga|"
    r"mehnga\s+option|costly\s+option|better\s+option.{0,30}(?:higher|premium|expensive)|"
    r"(?:premium|expensive|higher\s+price|upper\s+range).{0,30}option"
    r")",
    re.I,
)

_CHEAPER_OPTION_RE = re.compile(
    r"(?:"
    r"cheaper|sasta|kam\s+price|low\s+price|lower\s+price|affordable|"
    r"rent\s+only|buy\s+only|sell\s+only|kiraye\s+pe|purchase\s+only|"
    r"nearby\s+city|paas\s+ki\s+city|same\s+machine|wahi\s+machine|"
    r"(?:brand|company)\s+ka\s+hai|"
    r"show\s+(?:rent|buy)|only\s+(?:rent|buy)"
    r")",
    re.I,
)

_ACKNOWLEDGEMENT_RE = re.compile(
    r"^(?:"
    r"ok(?:ay)?|yes|yeah|yep|yup|sure|fine|cool|right|"
    r"haan|ha|ji|theek(?:\s*hai)?|thik(?:\s*hai)?|"
    r"continue|go\s+ahead|proceed|chaliye|aage\s+badho|"
    r"got\s*it|understood|samajh\s+gaya"
    r")[\s!.?]*$",
    re.I,
)

_FRUSTRATION_RE = re.compile(
    r"(?:"
    r"\b(?:useless|worthless|not\s+helpful|unhelpful|waste\s+of\s+time)\b|"
    r"you\s+(?:are\s+)?(?:useless|stupid|dumb|idiot|hopeless)|"
    r"(?:bekar|bekaar)\s+(?:answer|reply|response)|"
    r"kuch\s+samajh\s+nahi|samajh\s+nahi\s+(?:aata|aa\s+raha)|"
    r"wrong\s+(?:again|answer|reply)|galat\s+(?:answer|jawab)|"
    r"not\s+helping|help\s+nahi|madad\s+nahi|"
    r"useless\s+assistant|bekar\s+assistant"
    r")",
    re.I,
)

_RENT_BROAD_RE = re.compile(
    r"\b(?:rent|hire|kiraye|kiraya)\b.{0,40}\b(?:machine|equipment|machinery|saman)\b",
    re.I,
)
_BUY_BROAD_RE = re.compile(
    r"\b(?:buy|purchase|khareed)\b.{0,40}\b(?:machine|equipment|machinery|saman)\b",
    re.I,
)
_EQUIPMENT_BROAD_RE = re.compile(
    r"\b(?:construction\s+)?(?:equipment|machinery)\s+chahiye\b|"
    r"\bsite\s+ke\s+liye\s+(?:equipment|machine|saman)\b",
    re.I,
)


def _has_session_search_context(ctx: Optional[dict]) -> bool:
    last = (ctx or {}).get("last_filters") or {}
    return bool(last.get("category") or last.get("city") or last.get("brand"))


def _parsed_or_parse(message: str, parsed: Optional[dict]) -> dict:
    return parsed if parsed is not None else parse_query(message)


_BRAND_ONLY_INVENTORY_RE = re.compile(
    r"\b(?:brands?|companies?|makers?|manufacturers?)\b",
    re.I,
)


def is_brand_filter_refinement_signal(
    message: str,
    ctx: Optional[dict] = None,
    parsed: Optional[dict] = None,
) -> bool:
    """Brand-only follow-up on an existing search session — filter, not inventory."""
    text = (message or "").strip()
    if not text or not _has_session_search_context(ctx):
        return False
    p = _parsed_or_parse(text, parsed)
    if not p.get("brand") or p.get("category"):
        return False
    if re.search(r"\bbrand\s+only\b", text, re.I):
        return True
    return len(text.split()) <= 5 and bool(p.get("brand"))


def is_brand_only_inventory_signal(
    message: str,
    parsed: Optional[dict] = None,
) -> bool:
    """Brand mentioned without category — user wants brand coverage or categories."""
    text = (message or "").strip()
    if not text:
        return False
    p = _parsed_or_parse(text, parsed)
    brand = p.get("brand") or ((p.get("brands") or [None])[0])
    if not brand or p.get("category"):
        return False
    if re.search(r"\bbrand\s+only\b", text, re.I):
        return False
    from app.ai.catalog_entity_resolver import is_brand_marketplace_search

    if is_brand_marketplace_search(text, p):
        return False
    if _BRAND_ONLY_INVENTORY_RE.search(text):
        return True
    return len(text.split()) <= 4 and bool(brand) and not p.get("city")


def is_brand_inventory_signal(message: str) -> bool:
    """User asks which brands are available (inventory/listing), not a single-brand check."""
    return bool(_BRAND_INVENTORY_RE.search((message or "").strip()))


def is_brand_availability_signal(
    message: str,
    parsed: Optional[dict] = None,
) -> bool:
    """User asks whether a specific brand is available for a category."""
    text = (message or "").strip()
    if not text:
        return False
    p = _parsed_or_parse(text, parsed)
    if not (p.get("brand") and p.get("category")):
        return False
    return bool(re.search(r"(?:milta|milega|available|hai\s+kya|have\s+you|stock|carry)", text, re.I))


def is_machine_brand_query_signal(
    message: str,
    parsed: Optional[dict] = None,
) -> bool:
    """
    User asks which brands/companies are available for a category or segment.
    """
    text = (message or "").strip()
    if not text:
        return False
    p = _parsed_or_parse(text, parsed)
    if not _BRAND_INVENTORY_RE.search(text):
        # Single-brand availability: "Hyundai excavator milta hai kya?"
        if p.get("brand") and p.get("category"):
            if re.search(r"(?:milta|milega|available|hai\s+kya|have\s+you)", text, re.I):
                return True
        return False
    return bool(p.get("category") or p.get("brand") or p.get("brands"))


def is_machine_comparison_signal(
    message: str,
    parsed: Optional[dict] = None,
) -> bool:
    """Structural comparison — brands, categories, or suitability."""
    text = (message or "").strip()
    if not text:
        return False
    p = _parsed_or_parse(text, parsed)
    brands = p.get("brands") or detect_all_brands(text)
    cat = p.get("category") or detect_requested_category(text)

    # Concrete search shape (category + city/budget) without compare connector.
    if cat and (p.get("city") or p.get("max_price") is not None):
        if len(brands) < 2 and not _COMPARISON_CONNECTOR_RE.search(text):
            return False

    if _COMPARISON_SIGNAL_RE.search(text):
        if len(brands) >= 2 or cat:
            return True
        if re.search(
            r"\b(?:backhoe|excavator|roller|compactor|crane|loader|bulldozer)\b.*"
            r"\b(?:or|ya|vs\.?|versus)\b.*"
            r"\b(?:backhoe|excavator|roller|compactor|crane|loader|bulldozer)\b",
            text,
            re.I,
        ):
            return True
        if re.search(r"(?:for|ke\s+liye).{0,40}(?:digging|compaction|lifting|earthwork)", text, re.I):
            return True
    return False


def is_higher_budget_signal(
    message: str,
    ctx: Optional[dict] = None,
    parsed: Optional[dict] = None,
) -> bool:
    text = (message or "").strip()
    if not text or not _HIGHER_BUDGET_RE.search(text):
        return False
    p = _parsed_or_parse(text, parsed)
    # New explicit full search — not a budget follow-up
    if p.get("category") and p.get("city") and not _has_session_search_context(ctx):
        return False
    return _has_session_search_context(ctx) or bool(p.get("category"))


def is_cheaper_option_signal(
    message: str,
    ctx: Optional[dict] = None,
    parsed: Optional[dict] = None,
) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    p = _parsed_or_parse(text, parsed)
    if detect_cheaper(text) or _CHEAPER_OPTION_RE.search(text):
        if _has_session_search_context(ctx):
            return True
        if p.get("brand") and not p.get("category") and _has_session_search_context(ctx):
            return True
    if p.get("listing_type") and _has_session_search_context(ctx) and not p.get("category"):
        return True
    if p.get("brand") and _has_session_search_context(ctx) and len(text.split()) <= 6:
        return True
    return False


def is_acknowledgement_signal(
    message: str,
    ctx: Optional[dict] = None,
) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if not _ACKNOWLEDGEMENT_RE.match(text):
        return False
    pending = (ctx or {}).get("pending")
    return bool(pending) or _has_session_search_context(ctx)


def is_frustration_signal(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_FRUSTRATION_RE.search(text))


def is_broad_machine_request_signal(
    message: str,
    parsed: Optional[dict] = None,
) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    p = _parsed_or_parse(text, parsed)
    if p.get("category") or p.get("city") or p.get("brand"):
        return False
    if is_broad_vague_query(text):
        return True
    if _RENT_BROAD_RE.search(text) or _BUY_BROAD_RE.search(text):
        return True
    if _EQUIPMENT_BROAD_RE.search(text):
        return True
    return False


def is_recommendation_broad_signal(
    message: str,
    parsed: Optional[dict] = None,
) -> bool:
    text = (message or "").strip()
    if not text or not is_recommendation_query(text):
        return False
    p = _parsed_or_parse(text, parsed)
    has_work = bool(resolve_purpose_key(text) or p.get("category"))
    has_city = bool(p.get("city"))
    return not (has_work and has_city)


def enrich_entities_from_context(
    entities: dict[str, Any],
    parsed: dict,
    ctx: Optional[dict],
) -> dict[str, Any]:
    """Merge session filters into entities for follow-up intents."""
    from app.ai.context_routing_gate import get_current_gate

    gate = get_current_gate() or {}
    if gate.get("block_previous_search_context") or (ctx or {}).get("_context_blocked"):
        return dict(entities)

    last = (ctx or {}).get("last_filters") or {}
    out = dict(entities)
    if not out.get("machine_type"):
        out["machine_type"] = parsed.get("category") or last.get("category")
    if not out.get("city"):
        out["city"] = parsed.get("city") or last.get("city")
    if not out.get("brand"):
        out["brand"] = parsed.get("brand") or last.get("brand")
    if out.get("max_price") is None and parsed.get("max_price") is None:
        out["max_price"] = last.get("max_price")
    brands = parsed.get("brands") or detect_all_brands((ctx or {}).get("message") or "")
    if brands:
        out["brands"] = brands
    return out


def current_message_requirement_entities(
    message: str,
    parsed: dict | None = None,
    entities: dict | None = None,
) -> dict[str, Any]:
    """Requirement fields explicitly present in the current user message only."""
    parsed = _parsed_or_parse(message, parsed)
    entities = entities or {}
    out: dict[str, Any] = {}

    category = (
        entities.get("category")
        or entities.get("machine_type")
        or entities.get("machine_category")
        or parsed.get("category")
        or detect_requested_category(message)
    )
    city = entities.get("city") or parsed.get("city")
    purpose = (
        entities.get("purpose")
        or resolve_purpose_key(message)
        or parsed.get("purpose_key")
    )
    brand = entities.get("brand") or parsed.get("brand")
    budget = entities.get("max_price") or entities.get("budget") or parsed.get("max_price")
    listing_type = entities.get("listing_type") or parsed.get("listing_type")

    for key, val in (
        ("category", category),
        ("city", city),
        ("purpose", purpose),
        ("brand", brand),
        ("budget", budget),
        ("listing_type", listing_type),
    ):
        if val is not None and val != "" and val != []:
            out[key] = val
    return out


def is_fresh_broad_machine_intent(
    message: str,
    parsed: dict | None = None,
    entities: dict | None = None,
) -> bool:
    """
    True when the user starts a new vague machine request without refinement signals.
    Stale session filters must not be reused in this case.
    """
    from app.ai.search_refinement_engine import detect_refinement_type

    parsed = _parsed_or_parse(message, parsed)
    entities = entities or {}
    if detect_refinement_type(message, parsed):
        return False
    if current_message_requirement_entities(message, parsed, entities):
        return False
    return is_broad_vague_query(message, session_collected=None)
