"""
Universal marketplace query understanding.

Decides whether the user is:
  - asking for NEW advice / multi-task recommendations
  - following up about ONE shown machine
  - starting a purpose-based search
  - asking something else

This prevents mis-routing indirect queries to wrong handlers.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import detect_requested_category
from app.chatbot.assistant_intelligence import detect_all_work_purposes

# New advisory / recommendation — NOT a follow-up about one machine.
_ADVISORY_REQUEST_RE = re.compile(
    r"(?:"
    r"\b(?:suggest|recommend|advise|guide)\b"
    r"|\b(?:which|what)\s+machines?\b"
    r"|\bbest\s+machines?\b"
    r"|\bsuitable\s+for\s+(?:these|those|the\s+work|both|such|my)"
    r"|\b(?:want|need)\s+machines?\s+for"
    r"|\bmachines?\s+(?:for|to)\s+"
    r"|\bkaunsi\s+machines?\b"
    r"|\bsuggest\s+me\b"
    r")",
    re.I,
)

_DEMONSTRATIVE_RE = re.compile(
    r"(?:\bthis\b|\bit\b|\bthat\b|\bthese\b|\bthose\b"
    r"|\bye\b|\byeh\b|will\s+this|can\s+this|is\s+this|kya\s+ye)",
    re.I,
)

_MACHINE_FOLLOWUP_RE = re.compile(
    r"(?:"
    r"(?:will|can|would|is|does)\s+(?:this|it|ye|yeh)\b"
    r"|(?:this|it|ye)\s+(?:help|work|good|suitable)"
    r"|(?:help|work|good|suitable)\s+for\s+(?:this|it|ye)"
    r")",
    re.I,
)


def is_advisory_request(message: str) -> bool:
    """User wants suggestions — not asking about one specific prior machine."""
    text = (message or "").strip()
    if not text:
        return False
    if _ADVISORY_REQUEST_RE.search(text):
        return True
    purposes = detect_all_work_purposes(text)
    if len(purposes) >= 2:
        return True
    if len(purposes) >= 1 and re.search(
        r"\b(?:suggest|recommend|suitable|which|what)\b", text, re.I,
    ):
        return True
    return bool(
        len(purposes) >= 1
        and re.search(r"\b(?:and|aur|also|plus)\b", text, re.I)
    )


def is_single_machine_followup(message: str, *, has_machine_context: bool) -> bool:
    """
    True only when user clearly refers to ONE previously shown machine.
    """
    text = (message or "").strip()
    if not text or not has_machine_context:
        return False
    if is_advisory_request(text):
        return False
    if len(detect_all_work_purposes(text)) >= 2:
        return False
    if _MACHINE_FOLLOWUP_RE.search(text):
        return True
    if _DEMONSTRATIVE_RE.search(text) and len(text.split()) <= 20:
        if re.search(r"\b(?:help|work|good|suitable|fit)\b", text, re.I):
            return True
    return False


def understand_marketplace_query(
    message: str,
    *,
    last_filters: dict,
    result_ctx: dict,
    has_name_reference: bool = False,
) -> dict[str, Any]:
    """
    Universal query shape — drives routing for ANY indirect/relevant message.
    """
    msg = (message or "").strip()
    purposes = detect_all_work_purposes(msg)
    explicit_cat = detect_requested_category(msg)

    # Delivery/logistics support — not a purpose-based machine search.
    if re.search(
        r"deliver|delivery\s+(?:charge|cost|kab)|transport\s+(?:charge|kaun|cost|charges)"
        r"|machine\s+kab\s+(?:aayegi|deliver)|pickup\s+kaise",
        msg,
        re.I,
    ):
        return {
            "shape": "general",
            "purposes": purposes,
            "city": last_filters.get("city"),
            "explicit_category": explicit_cat,
            "is_advisory": False,
            "is_followup": False,
        }

    has_machines = bool(result_ctx.get("last_machines"))
    city = last_filters.get("city") or (result_ctx.get("filters") or {}).get("city")

    base: dict[str, Any] = {
        "shape": "general",
        "purposes": purposes,
        "city": city,
        "explicit_category": explicit_cat,
        "is_advisory": is_advisory_request(msg),
        "is_followup": False,
    }

    # Multi-task or advisory → recommend machines per purpose (never old-machine suitability)
    if is_advisory_request(msg) and purposes:
        base["shape"] = "multi_purpose_advisory"
        return base

    if len(purposes) >= 2:
        base["shape"] = "multi_purpose_advisory"
        return base

    # Single machine follow-up (will this help…)
    if is_single_machine_followup(msg, has_machine_context=has_machines or has_name_reference):
        base["shape"] = "machine_suitability_followup"
        base["is_followup"] = True
        base["purpose_key"] = purposes[0] if purposes else None
        return base

    # Single purpose, new request → search primary category
    if purposes and not explicit_cat and not is_advisory_request(msg):
        if re.search(r"\b(?:need|want|chahiye|looking)\b", msg, re.I) or len(purposes) == 1:
            base["shape"] = "purpose_search"
            return base

    # Advisory without detected purpose — still guide, don't stuck on old machine
    if is_advisory_request(msg):
        base["shape"] = "advisory_clarification"
        return base

    base["shape"] = "general"
    return base
