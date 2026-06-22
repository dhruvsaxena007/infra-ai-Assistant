"""
Selected-machine context — generalized follow-up on a UI-selected or referenced listing.

Handles structural intents (not fixed phrases):
  - want / book / chahiye + demonstrative or active selection
  - contact owner / call seller
  - confirm interest in the highlighted card

Does NOT run a new marketplace search when the user is acting on one machine.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.conversation_context import slim_machine
from app.ai.query_parser import parse_query

# Demonstrative / deictic reference (English + Hindi Devanagari + Hinglish Latin)
_DEMONSTRATIVE_RE = re.compile(
    r"(?:"
    r"\b(?:this|that|these|those|it|same|selected|above|previous|last)\b"
    r"|\b(?:ye|yeh|ya|yahi|wahi|usi|us|iss|is|wo|voh|vo)\b"
    r"|\b(?:selected|choose|picked|select)\s+(?:machine|card|one|option)\b"
    r"|\b(?:machine|card)\s+(?:ye|yeh|wahi|selected)\b"
    r"|(?:ये|यह|वह|वो|यही|वही|उस|इस|उसी|इसी)"
    r"|(?:सेलेक्ट(?:ेड|ed)|चुनी|चुना)\s*(?:मशीन|machine)?"
    r"|(?:मशीन|machine)\s*(?:ये|यह|वह|selected|सेलेक्ट)"
    r")",
    re.I | re.UNICODE,
)

# User wants to proceed with a specific machine (not a fresh search)
_WANT_MACHINE_RE = re.compile(
    r"(?:"
    r"\b(?:want|need|like|prefer|choose|pick|take|confirm|proceed|go\s+with)\b"
    r"|\b(?:chahiye|chaiye|chahiy|lena|leni|lunga|lungi|book|rent|hire|kiraye?)\b"
    r"|\b(?:acchi|sahi|badhiya|theek)\s+(?:hai|lag(?:ti|ta)\s+hai)\b"
    r"|\bmujhe\s+(?:ye|yeh|wahi|ye\s+wali)\b"
    r"|\bi\s+(?:want|need)\s+(?:this|that|it)\b"
    r"|(?:मुझे|मैं\s+को|चाहिए|चाहिये|ले(?:ना|नी|ंगा|ंगी)|बुक|किराए?)"
    r")",
    re.I | re.UNICODE,
)

_CONTACT_OWNER_RE = re.compile(
    r"(?:"
    r"contact\s+owner|call\s+owner|talk\s+to\s+owner|reach\s+owner|owner\s+se"
    r"|owner\s+(?:ka\s+number|contact|phone|details)"
    r"|seller\s+(?:contact|se\s+baat)|malik\s+se|contact\s+seller"
    r"|(?:मालिक|owner)\s*(?:से|se)?\s*(?:बात|contact|call)?"
    r"|(?:contact|call)\s*(?:owner|seller|मालिक)?"
    r")",
    re.I | re.UNICODE,
)

# Explicit fresh search — overrides selected-machine handling
_FRESH_SEARCH_OVERRIDE_RE = re.compile(
    r"(?:"
    r"\b(?:another|different|other|dusri|dusra|alag|new|change)\s+(?:city|machine|type|brand)\b"
    r"|\b(?:show\s+(?:me\s+)?(?:all|more|other)|dikhao\s+(?:aur|sab)|search\s+again)\b"
    r"|\b(?:in|mein|mai)\s+[A-Za-z\u0900-\u097F]{3,}\b.*\b(?:dikhao|search|find|chahiye)\b"
    r")",
    re.I,
)


def resolve_active_machine(
    message: str,
    *,
    session_ctx: dict | None = None,
    result_ctx: dict | None = None,
    conv_state: dict | None = None,
) -> Optional[dict]:
    """
    Resolve the machine the user is referring to.
    Priority: UI selected_machine → name overlap in results → top result.
    """
    session_ctx = session_ctx or {}
    result_ctx = result_ctx or {}
    conv_state = conv_state or {}

    selected = (
        session_ctx.get("selected_machine")
        or conv_state.get("selected_machine")
        or {}
    )
    if selected and (selected.get("name") or selected.get("id") or selected.get("_id")):
        return slim_machine(selected) if selected.get("category") or selected.get("name") else selected

    machines = result_ctx.get("last_machines") or []
    msg = (message or "").strip().lower()
    if machines:
        for m in machines:
            name = (m.get("name") or "").lower()
            if name and name in msg:
                return m
        if _DEMONSTRATIVE_RE.search(msg):
            return machines[0]

    top = result_ctx.get("top_machine")
    if top and _DEMONSTRATIVE_RE.search(message or ""):
        return top
    return None


def _has_active_selection(
    session_ctx: dict | None,
    conv_state: dict | None,
) -> bool:
    sel = (session_ctx or {}).get("selected_machine") or (conv_state or {}).get("selected_machine")
    return bool(sel and (sel.get("name") or sel.get("id") or sel.get("_id")))


def detect_selected_machine_turn(
    message: str,
    parsed: dict | None = None,
    *,
    session_ctx: dict | None = None,
    result_ctx: dict | None = None,
    conv_state: dict | None = None,
) -> Optional[dict[str, Any]]:
    """
    Return turn payload when user acts on a selected/referenced machine.
    None → not a selected-machine turn (caller may search normally).
    """
    text = (message or "").strip()
    if not text or _FRESH_SEARCH_OVERRIDE_RE.search(text):
        return None

    parsed = parsed or parse_query(text)
    machine = resolve_active_machine(
        text,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
        conv_state=conv_state,
    )
    has_selection = _has_active_selection(session_ctx, conv_state)
    has_demo = bool(_DEMONSTRATIVE_RE.search(text))
    has_results = bool((result_ctx or {}).get("last_machines"))

    if not machine and not (has_selection and has_demo):
        if not (has_selection and _WANT_MACHINE_RE.search(text) and len(text.split()) <= 8):
            return None

    if not machine and has_selection:
        raw = (session_ctx or {}).get("selected_machine") or (conv_state or {}).get("selected_machine")
        if raw:
            machine = slim_machine(raw) if raw.get("name") else raw

    if not machine:
        return None

    if _CONTACT_OWNER_RE.search(text):
        return {
            "action": "contact_owner",
            "machine": machine,
            "reason": "contact_owner_signal",
        }

    # Want / book / chahiye on selected or demonstrative reference
    if _WANT_MACHINE_RE.search(text) and (has_demo or has_selection or has_results):
        # Explicit category + city in message = fresh/refined search unless deictic reference
        if parsed.get("city") and parsed.get("category") and not has_demo:
            return None
        return {
            "action": "want_booking",
            "machine": machine,
            "reason": "want_selected_machine",
        }

    if has_selection and has_demo and len(text.split()) <= 6:
        return {
            "action": "want_booking",
            "machine": machine,
            "reason": "short_demonstrative_selection",
        }

    return None


def build_selected_machine_response(
    *,
    machine: dict,
    action: str,
    lang: str = "english",
) -> dict[str, Any]:
    """Rich booking / contact guidance for one machine — no new search."""
    from app.utils.machine_normalizer import format_price_label
    from app.chatbot.language import localized_booking_guidance, pick_lang

    name = machine.get("name") or machine.get("brand") or "this machine"
    city = machine.get("city") or ""
    category = machine.get("category") or machine.get("category_display") or ""
    price = format_price_label(machine) if machine.get("price_per_day") or machine.get("price") else None
    avail = machine.get("availability_status") or machine.get("availability") or ""

    label = category or name
    base_guidance = localized_booking_guidance(label=name, city=city, lang=lang)

    if action == "contact_owner":
        intro = pick_lang(
            lang,
            english=f"Great choice — **{name}**{f' in {city.title()}' if city else ''}.",
            hindi=f"बढ़िया — **{name}**{f' ({city})' if city else ''}.",
            hinglish=f"Great choice — **{name}**{f' {city} me' if city else ''}.",
        )
        step = pick_lang(
            lang,
            english="Tap **Contact Owner** on that card — you'll reach the listing owner directly to confirm dates, site location, and rent terms.",
            hindi="उस कार्ड पर **Contact Owner** दबाएँ — मालिक से सीधे तारीख, साइट और किराए की शर्तें तय करें।",
            hinglish="Us card par **Contact Owner** dabayein — owner se dates, site aur rent terms confirm karein.",
        )
        msg = f"{intro}\n\n{step}"
    else:
        intro = pick_lang(
            lang,
            english=f"Got it — you want **{name}**{f' in {city.title()}' if city else ''}.",
            hindi=f"ठीक है — आपको **{name}**{f' ({city})' if city else ''} chahiye.",
            hinglish=f"Samajh gaya — aapko **{name}**{f' {city} me' if city else ''} chahiye.",
        )
        details = []
        if price:
            details.append(price)
        if avail:
            details.append(str(avail).replace("_", " ").title())
        detail_line = " · ".join(details) if details else ""
        msg = intro
        if detail_line:
            msg += f"\n\n{detail_line}"
        msg += f"\n\n{base_guidance}"

    return {
        "message": msg,
        "assistant_mode": "booking_guidance" if action == "want_booking" else "contact_owner",
        "machines": [machine],
        "preserve_machines": True,
        "suggestions": [
            "Contact owner",
            "Compare similar",
            "Show cheaper options",
        ],
        "response_goal": "booking_guidance" if action == "want_booking" else "contact_owner",
    }
