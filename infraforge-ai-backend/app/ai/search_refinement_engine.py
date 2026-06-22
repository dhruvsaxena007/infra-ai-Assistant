"""
Structured search refinement — cheaper, budget, city switch, brand filter, rent/buy, operator.
Requires eligible last_search_filters; merges only changed fields.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import detect_cheaper, detect_list_all, detect_max_price
from app.ai.context_routing_gate import (
    FAMILY_SEARCH_REFINEMENT,
    should_apply_previous_context,
    _CONTEXT_MACHINE_SEARCH,
)
from app.ai.query_parser import parse_query

_CITY_SWITCH_RE = re.compile(
    r"\b(?:same\s+in|also\s+in|what\s+about|switch\s+to|city\s+me\s+bhi|"
    r"(?:same|wahi)\s+(?:in|me|mai))\b",
    re.I,
)
_RENT_ONLY_RE = re.compile(r"\b(?:rent\s+only|hire\s+only|kiraye\s+pe\s+hi)\b", re.I)
_BUY_ONLY_RE = re.compile(r"\b(?:buy\s+only|purchase\s+only|khareedna\s+hi)\b", re.I)
_OPERATOR_RE = re.compile(r"\b(?:with\s+operator|operator\s+ke\s+sath|bina\s+operator)\b", re.I)
_HIGHER_BUDGET_RE = re.compile(
    r"\b(?:higher\s+budget|increase\s+budget|more\s+expensive|premium|badha\s+budget|zyada\s+budget)\b",
    re.I,
)
_BRAND_FILTER_RE = re.compile(
    r"\b(?:brand\s+only|only\s+brand|sirf\s+brand|filter\s+brand|brand\s+filter)\b",
    re.I,
)

_DEFAULT = {
    "category": None, "city": None, "region": None, "max_price": None,
    "brand": None, "model": None, "listing_type": None,
}


def detect_refinement_type(message: str, parsed: dict | None = None) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    p = parsed or parse_query(text)
    if detect_cheaper(text) or re.search(r"\b(?:cheaper|sasta|lower\s+price|affordable)\b", text, re.I):
        return "cheaper_options"
    if _HIGHER_BUDGET_RE.search(text):
        return "higher_budget"
    if p.get("max_price") is not None and not p.get("category"):
        return "budget_cap"
    if _CITY_SWITCH_RE.search(text) and p.get("city"):
        return "city_switch"
    if _RENT_ONLY_RE.search(text):
        return "rent_only"
    if _BUY_ONLY_RE.search(text):
        return "buy_only"
    if _OPERATOR_RE.search(text):
        return "with_operator"
    if p.get("brand") and not p.get("category"):
        return "brand_filter"
    if _BRAND_FILTER_RE.search(text) and p.get("brand"):
        return "brand_filter"
    if detect_list_all(text):
        return "list_all"
    return None


def apply_search_refinement(
    message: str,
    *,
    last_filters: dict[str, Any],
    parsed: dict | None = None,
    intent_family: str | None = None,
    entities: dict | None = None,
) -> dict[str, Any]:
    """
    Return {filters, refinement_type, missing_fields, context_eligible, block_reason}.
    """
    parsed = parsed or parse_query(message)
    entities = entities or {}
    last = {**_DEFAULT, **{k: v for k, v in (last_filters or {}).items() if v is not None}}

    refinement = detect_refinement_type(message, parsed)
    allowed, block_reason = should_apply_previous_context(
        intent_family or FAMILY_SEARCH_REFINEMENT,
        context_type=_CONTEXT_MACHINE_SEARCH,
        message_features={"refinement": bool(refinement), "has_city": bool(parsed.get("city"))},
    )

    if not last.get("category") and not last.get("city") and not last.get("brand"):
        return {
            "filters": {},
            "refinement_type": refinement,
            "missing_fields": ["category", "city"],
            "context_eligible": False,
            "block_reason": "no_eligible_last_search_filters",
        }

    if not allowed and refinement:
        return {
            "filters": {},
            "refinement_type": refinement,
            "missing_fields": ["previous_search_context"],
            "context_eligible": False,
            "block_reason": block_reason,
        }

    merged = dict(last)
    rtype = refinement

    if rtype == "cheaper_options":
        if merged.get("max_price"):
            merged["max_price"] = int(float(merged["max_price"]) * 0.75)
    elif rtype == "higher_budget":
        if merged.get("max_price"):
            merged["max_price"] = int(float(merged["max_price"]) * 1.35)
    elif rtype == "budget_cap":
        merged["max_price"] = parsed.get("max_price")
    elif rtype == "city_switch":
        if parsed.get("city"):
            merged["city"] = parsed["city"]
            merged["region"] = None
    elif rtype == "rent_only":
        merged["listing_type"] = "rent"
    elif rtype == "buy_only":
        merged["listing_type"] = "sell"
    elif rtype in ("brand_filter",):
        brand = parsed.get("brand") or entities.get("brand")
        if brand:
            merged["brand"] = brand
    elif parsed.get("listing_type"):
        from app.utils.machine_normalizer import normalize_listing_type_filter
        merged["listing_type"] = normalize_listing_type_filter(parsed["listing_type"])

    for key in ("category", "city", "brand", "model", "listing_type"):
        if parsed.get(key) and rtype not in ("city_switch",):
            if key == "city" and _CITY_SWITCH_RE.search(message):
                merged["city"] = parsed["city"]
            elif key != "city" or not merged.get("city"):
                if parsed.get(key):
                    if key == "listing_type":
                        from app.utils.machine_normalizer import normalize_listing_type_filter
                        merged[key] = normalize_listing_type_filter(parsed[key])
                    else:
                        merged[key] = parsed[key]

    return {
        "filters": {k: v for k, v in merged.items() if v is not None},
        "refinement_type": rtype,
        "missing_fields": [],
        "context_eligible": True,
        "block_reason": "",
    }
