"""
Semantic turn classifier — Groq LLM understands ANY phrasing (direct/indirect).

This is the universal backstop when rule signals are uncertain.
NOT trained on fixed example sentences — classifies by turn *role* + session context.

Enable: USE_GROQ_UNIVERSAL_CLASSIFIER=auto (default) — on when GROQ_API_KEY exists.
Disable: USE_GROQ_UNIVERSAL_CLASSIFIER=false
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.ai.category_mapping import detect_brand, detect_requested_category
from app.ai.conversation_context import resolve_referenced_machine
from app.core.config import settings

_VALID_SHAPES = frozenset({
    "conversational",
    "comparison",
    "machine_attribute",
    "contextual_refine",
    "defer",
})

_VALID_ACTIONS = frozenset({
    "cheaper_options",
    "compare_similar",
    "contact_owner",
})

_VALID_SUBTYPES = frozenset({
    "name_intro",
    "wellbeing",
    "wellbeing_reciprocal",
    "user_state",
    "thanks",
    "specs",
    "fuel",
    "need_reference",
})


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def _session_summary(
    *,
    session_ctx: dict,
    result_ctx: dict,
    last_filters: dict,
    greeted: bool,
) -> str:
    machines = result_ctx.get("last_machines") or []
    lines = [
        f"greeted={greeted}",
        f"user_name={session_ctx.get('user_name') or 'unknown'}",
        f"last_filters={json.dumps({k: last_filters.get(k) for k in ('category', 'city', 'brand', 'max_price', 'listing_type') if last_filters.get(k) is not None})}",
    ]
    if machines:
        lines.append("last_shown_machines:")
        for i, m in enumerate(machines[:5], 1):
            lines.append(
                f"  {i}. {m.get('name')} | brand={m.get('brand')} | "
                f"category={m.get('category')} | city={m.get('city')}"
            )
    else:
        lines.append("last_shown_machines=none")
    return "\n".join(lines)


def _build_prompt(message: str, context_block: str) -> str:
    return f"""You are the turn classifier for InfraForge — a construction machine marketplace assistant in India.

Users write in English, Hindi, Hinglish, with typos, speech-to-text errors, and indirect phrasing.
Your job: understand what the user MEANS (not match exact phrases) and classify the turn.

SESSION CONTEXT:
{context_block}

USER MESSAGE (raw):
{message}

Return ONLY valid JSON (no markdown):
{{
  "corrected_message": "fix typos/grammar; keep meaning; empty string if unchanged",
  "shape": "conversational | comparison | machine_attribute | contextual_refine | defer",
  "subtype": "name_intro | wellbeing | wellbeing_reciprocal | user_state | thanks | specs | fuel | need_reference | null",
  "contextual_action": "cheaper_options | compare_similar | contact_owner | null",
  "user_name": "extracted first name or null",
  "brands": ["brand1", "brand2"],
  "category": "machine category or empty",
  "defer_intent": "search | support | recommendation | unknown | null",
  "confidence": 0.0 to 1.0,
  "reason": "one short line"
}}

SHAPE RULES (apply by meaning, any wording):

1. conversational — social chat ONLY; NEVER search machines:
   - greetings, how are you, name introductions (any typo: "my name id X", "call me X", "people know me as X")
   - thanks, small talk, wellbeing, "what about you"
   - NO machine category/city search intent

2. comparison — user wants to compare options/brands/models (direct OR indirect):
   - "JCB vs CAT", "which is better", "Hyundai ya CAT acche hain", "generally which brand is good for road roller"
   - Even if category mentioned — if intent is COMPARE not FIND, shape=comparison

3. machine_attribute — user asks ABOUT a machine already shown or referenced:
   - specs, fuel, weight, dimensions, "tell me about it/this/that", "kitna fuel leta hai"
   - Requires reference to prior results OR demonstrative (this/that/it/ye)
   - NOT a new search

4. contextual_refine — short follow-up on PREVIOUS search/results (session has context):
   - cheaper/lower price/sasta options, compare similar, contact owner
   - "show something cheaper", "koi sasta", "is se kam", chip-style clicks
   - Uses last_filters / last_shown_machines — NOT a fresh search

5. defer — hand off to search/support router:
   - user wants to FIND/RENT/BUY machines (new search)
   - refund, payment, booking, support
   - set defer_intent accordingly

CRITICAL:
- Fix speech typos in corrected_message (id→is, hundai→hyundai, etc.)
- Indirect Hindi/Hinglish must map to the same shape as English equivalents
- If session has last machines and user asks about "it/this/ye" → machine_attribute NOT search
- If session has filters and user wants cheaper/similar → contextual_refine NOT search
- Name introduction is ALWAYS conversational even with typos
- confidence >= 0.85 only when clearly sure
"""


def _normalize_brands(raw: list) -> list[str]:
    out: list[str] = []
    for b in raw or []:
        s = str(b).strip()
        if not s:
            continue
        canon = detect_brand(s) or s.title()
        if canon not in out:
            out.append(canon)
    return out


def semantic_to_turn_payload(
    data: dict,
    *,
    original_message: str,
    normalized_message: str,
    parsed: dict,
    session_ctx: dict,
    result_ctx: dict,
    last_filters: dict,
) -> dict[str, Any]:
    """Map Groq JSON → universal turn dict (same shape as rules engine)."""
    shape = (data.get("shape") or "defer").strip().lower()
    if shape not in _VALID_SHAPES:
        shape = "defer"

    corrected = (data.get("corrected_message") or "").strip() or normalized_message
    conf = float(data.get("confidence") or 0.7)
    base: dict[str, Any] = {
        "shape": shape,
        "confidence": conf,
        "reason": f"semantic_{data.get('reason') or shape}",
        "parsed": parsed,
        "original_message": original_message,
        "normalized_message": corrected,
        "layer": "groq_semantic",
        "semantic": data,
    }

    if corrected.lower() != normalized_message.lower():
        base["normalization"] = {
            "original": original_message,
            "corrected": corrected,
            "layer": "groq_semantic",
        }

    if shape == "conversational":
        subtype = (data.get("subtype") or "wellbeing").strip().lower()
        if subtype not in _VALID_SUBTYPES:
            subtype = "wellbeing"
        name = data.get("user_name") or session_ctx.get("user_name")
        if name:
            name = str(name).strip().title()
        return {
            **base,
            "subtype": subtype,
            "turn_type": "conversational",
            "assistant_mode": "conversational",
            "user_name": name,
        }

    if shape == "comparison":
        brands = _normalize_brands(data.get("brands") or [])
        category = (data.get("category") or "").strip().lower() or detect_requested_category(corrected)
        if not brands:
            brands = _normalize_brands([detect_brand(corrected)] if detect_brand(corrected) else [])
        return {
            **base,
            "brands": brands,
            "category": category or None,
            "needs_clarification": len(brands) < 2 and not category,
            "turn_type": "in_chat_compare",
            "assistant_mode": "comparison",
        }

    if shape == "machine_attribute":
        subtype = (data.get("subtype") or "specs").strip().lower()
        if subtype not in ("fuel", "specs", "need_reference"):
            subtype = "fuel" if "fuel" in corrected.lower() else "specs"
        ref = resolve_referenced_machine(corrected, result_ctx)
        if not ref:
            machines = result_ctx.get("last_machines") or []
            ref = machines[0] if machines else None
        if not ref:
            return {
                **base,
                "shape": "machine_attribute",
                "subtype": "need_reference",
                "turn_type": "machine_detail",
                "assistant_mode": "clarification",
            }
        return {
            **base,
            "subtype": subtype,
            "machine": ref,
            "turn_type": "machine_detail",
            "assistant_mode": "machine_detail",
        }

    if shape == "contextual_refine":
        action = (data.get("contextual_action") or "cheaper_options").strip().lower()
        if action not in _VALID_ACTIONS:
            action = "cheaper_options"
        ref = resolve_referenced_machine(corrected, result_ctx) or result_ctx.get("top_machine")
        return {
            **base,
            "action": action,
            "machine": ref,
            "filters": {
                k: last_filters.get(k)
                for k in ("category", "city", "region", "max_price", "brand", "listing_type")
                if last_filters.get(k) is not None
            },
            "turn_type": "contextual_refine",
            "assistant_mode": action,
        }

    return {
        **base,
        "turn_type": "defer",
        "assistant_mode": "defer",
        "defer_intent": data.get("defer_intent") or "unknown",
    }


async def classify_turn_semantically(
    message: str,
    *,
    session_ctx: Optional[dict] = None,
    result_ctx: Optional[dict] = None,
    last_filters: Optional[dict] = None,
    greeted: bool = False,
    parsed: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    """Groq semantic classification — returns None on failure/disabled."""
    if not settings.groq_universal_enabled or not settings.GROQ_API_KEY:
        return None

    text = (message or "").strip()
    if not text:
        return None

    session_ctx = session_ctx or {}
    result_ctx = result_ctx or {}
    last_filters = last_filters or {}
    parsed = parsed or {}

    try:
        from app.core.groq_client import groq_chat_completion

        prompt = _build_prompt(
            text,
            _session_summary(
                session_ctx=session_ctx,
                result_ctx=result_ctx,
                last_filters=last_filters,
                greeted=greeted,
            ),
        )
        response = groq_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            tag="semantic_turn",
        )
        if not response or not response.choices:
            return None
        content = response.choices[0].message.content or ""
        data = _extract_json(content)
        turn = semantic_to_turn_payload(
            data,
            original_message=message,
            normalized_message=text,
            parsed=parsed,
            session_ctx=session_ctx,
            result_ctx=result_ctx,
            last_filters=last_filters,
        )
        print(
            "[semantic_turn]",
            f"shape={turn.get('shape')}",
            f"conf={turn.get('confidence')}",
            f"reason={turn.get('reason')}",
        )
        return turn
    except Exception as exc:
        print(f"[semantic_turn] failed: {exc}")
        return None
