"""
Session conversation context: last results, filters, and contextual turn detection.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import category_label, detect_requested_category
from app.ai.query_understanding import understand_marketplace_query
from app.chatbot.assistant_intelligence import (
    category_suits_purpose,
    detect_all_work_purposes,
    primary_category_for_purpose,
)

_DEMONSTRATIVE_RE = re.compile(
    r"(?:\bthis\b|\bit\b|\bthat\b|\bthese\b|\bthose\b"
    r"|\bye\b|\byeh\b|will\s+this|can\s+this|is\s+this|kya\s+ye)",
    re.I,
)


def slim_machine(machine: dict) -> dict:
    """Compact machine snapshot for session memory — keeps fields needed for follow-ups."""
    specs = machine.get("specifications") or {}
    return {
        "id": str(machine.get("_id") or machine.get("id") or ""),
        "name": machine.get("name") or "",
        "category": (machine.get("category") or "").lower(),
        "category_display": machine.get("category_display") or machine.get("category") or "",
        "city": machine.get("city") or "",
        "brand": machine.get("brand") or "",
        "model": machine.get("model") or "",
        "specifications": dict(specs) if specs else {},
        "description": machine.get("description") or "",
        "rating": machine.get("rating"),
        "price_per_day": machine.get("price_per_day"),
        "listing_type": machine.get("listing_type"),
        "rent_type": machine.get("rent_type"),
        "availability": machine.get("availability"),
        "availability_status": machine.get("availability_status"),
        "image_url": machine.get("image_url"),
    }


def build_result_context(machines: list[dict], filters: dict) -> dict[str, Any]:
    slim = [slim_machine(m) for m in (machines or [])[:8] if m]
    return {
        "last_machines": slim,
        "top_machine": slim[0] if slim else None,
        "filters": {
            k: filters.get(k)
            for k in ("category", "city", "region", "listing_type", "max_price")
            if filters.get(k) is not None
        },
    }


def get_result_context(session_context: dict) -> dict[str, Any]:
    return (session_context or {}).get("last_results") or {}


def _name_overlap(message: str, machine: dict) -> bool:
    name = (machine.get("name") or "").lower()
    if not name:
        return False
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", name) if t not in ("heavy", "duty", "the")]
    if not tokens:
        return False
    msg = message.lower()
    hits = sum(1 for t in tokens[:6] if t in msg)
    return hits >= min(2, max(1, len(tokens) // 2))


def resolve_referenced_machine(
    message: str,
    result_ctx: dict,
    *,
    selected_machine: dict | None = None,
) -> Optional[dict]:
    if selected_machine and (selected_machine.get("name") or selected_machine.get("id")):
        msg = (message or "").strip()
        if _DEMONSTRATIVE_RE.search(msg) or len(msg.split()) <= 8:
            return slim_machine(selected_machine) if selected_machine.get("name") else selected_machine

    machines = result_ctx.get("last_machines") or []
    if not machines:
        return result_ctx.get("top_machine")
    msg = (message or "").strip()
    for m in machines:
        if _name_overlap(msg, m):
            return m
    if _DEMONSTRATIVE_RE.search(msg):
        return machines[0]
    return None


def has_contextual_reference(message: str, result_ctx: dict) -> bool:
    if not result_ctx.get("last_machines"):
        return False
    msg = (message or "").strip()
    if _DEMONSTRATIVE_RE.search(msg):
        return True
    return any(_name_overlap(msg, m) for m in result_ctx["last_machines"])


def analyze_contextual_turn(
    message: str,
    *,
    last_filters: dict,
    result_ctx: dict,
) -> dict[str, Any]:
    """
    Route contextual turns using universal query understanding (not phrase hacks).
    """
    msg = (message or "").strip()
    base: dict[str, Any] = {
        "turn_type": "none",
        "purpose_key": None,
        "purpose_keys": [],
        "referenced_machine": None,
        "search_filters": None,
        "enriched_message": None,
        "query_shape": "general",
    }
    if not msg:
        return base

    has_name_ref = any(
        _name_overlap(msg, m) for m in (result_ctx.get("last_machines") or [])
    )
    understanding = understand_marketplace_query(
        msg,
        last_filters=last_filters,
        result_ctx=result_ctx,
        has_name_reference=has_name_ref,
    )
    base["query_shape"] = understanding.get("shape", "general")
    purposes = understanding.get("purposes") or detect_all_work_purposes(msg)
    base["purpose_keys"] = purposes
    city = understanding.get("city") or last_filters.get("city")
    explicit_cat = detect_requested_category(msg)

    # --- Multi-purpose / advisory (NEW request — ignore last machine) ----------
    if understanding.get("shape") == "multi_purpose_advisory":
        return {
            **base,
            "turn_type": "multi_purpose_advisory",
            "purpose_keys": purposes,
        }

    if understanding.get("shape") == "advisory_clarification":
        return {**base, "turn_type": "advisory_clarification"}

    # --- Single machine follow-up only ---------------------------------------
    if understanding.get("shape") == "machine_suitability_followup":
        ref = resolve_referenced_machine(msg, result_ctx)
        return {
            **base,
            "turn_type": "suitability",
            "purpose_key": purposes[0] if purposes else None,
            "referenced_machine": ref or result_ctx.get("top_machine"),
        }

    if understanding.get("shape") == "purpose_search" and purposes and not explicit_cat:
        pk = purposes[0]
        primary = primary_category_for_purpose(pk)
        if primary:
            return {
                **base,
                "turn_type": "purpose_search",
                "purpose_key": pk,
                "search_filters": {
                    "category": primary,
                    "city": city,
                    "listing_type": last_filters.get("listing_type"),
                    "max_price": last_filters.get("max_price"),
                    "purpose_key": pk,
                    "requested_category": primary,
                },
            }

    # --- Demonstrative enrich (short ref, not advisory) ----------------------
    ref = resolve_referenced_machine(msg, result_ctx)
    if ref and _DEMONSTRATIVE_RE.search(msg) and not understanding.get("is_advisory"):
        from app.ai.context_routing_gate import get_current_gate, should_allow_reference_enrich

        gate = get_current_gate() or {}
        allowed, block_reason = should_allow_reference_enrich(
            gate,
            message=msg,
            has_last_machines=bool(result_ctx.get("last_machines")),
        )
        if not allowed:
            base["reference_enrich_blocked"] = True
            base["reference_enrich_blocked_reason"] = block_reason
            return base
        cat = ref.get("category") or ""
        if cat and not explicit_cat:
            return {
                **base,
                "turn_type": "reference_enrich",
                "referenced_machine": ref,
                "enriched_message": f"{cat} {msg}".strip(),
                "reference_enrich_applied": True,
            }

    return base


def category_fits_purpose(category: str, purpose_key: str) -> bool:
    return category_suits_purpose(category, purpose_key)
