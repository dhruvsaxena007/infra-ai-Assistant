"""
Brand-level advisory comparison — generalized mechanism.

When users ask which brand/company is better (structural compare signal),
produce a specification table + summary from domain knowledge (LLM),
NOT a marketplace inventory search.

Listing-level comparison (two cards with prices) remains in comparison_service.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.ai.category_mapping import category_label, detect_all_brands, detect_requested_category
from app.ai.intent_signals import (
    _COMPARISON_CONNECTOR_RE,
    _COMPARISON_SIGNAL_RE,
    is_machine_comparison_signal,
)
from app.ai.query_parser import parse_query

# Hindi/Hinglish: "jcb ke road roller badiya hote hai ya hitachi ke"
_HINDI_BRAND_VS = re.compile(
    r"(?:"
    r"\b\w+\s+ke\b.{0,80}\b(?:ya|or|vs\.?|versus)\b.{0,40}\b(?:\w+\s+ke|\w+)\b"
    r"|(?:badiya|badhiya|acch[ae]|achh[ae]|sahi|behtar|better|best)"
    r"\s*(?:hote|hai|hain|hoti|hot)?\s*(?:hai|hain)?\s*(?:ya|or)\b"
    r"|(?:kaun\s+sa|kaunsi|which)\s+(?:company|brand|machine).{0,40}(?:better|acch[ae]|badiya|behtar)"
    r")",
    re.I,
)

# Explicit marketplace listing comparison — keep inventory path
_LISTING_COMPARE_ACTION = re.compile(
    r"(?:"
    r"\b(?:available|listing|listings|milega|milegi|dikhao|dikhaiye|show\s+me|find|search|"
    r"book|contact\s+owner|for\s+rent|for\s+sale|for\s+buy|kiraye|kiraya)\b"
    r"|(?:in|mein|mai)\s+[A-Za-z\u0900-\u097F]{3,}"
    r")",
    re.I,
)


def _parse_entities(message: str, parsed: Optional[dict] = None) -> dict:
    return parsed if parsed is not None else parse_query(message or "")


def _infer_category(message: str, category: Optional[str]) -> Optional[str]:
    if category:
        return category
    text = message or ""
    if re.search(r"\bexcavat(?:or|ion)\b", text, re.I):
        return "excavator"
    from app.ai.universal_turn_engine import _detect_category

    return _detect_category(text) or detect_requested_category(text)


def is_brand_advisory_comparison(
    message: str,
    parsed: Optional[dict] = None,
    *,
    ignore_session_city: bool = True,
) -> bool:
    """
    True when the user asks a general brand/model suitability comparison,
    not a live listing search in a city.
    """
    text = (message or "").strip()
    if not text:
        return False

    if not is_machine_comparison_signal(text, _parse_entities(text, parsed)):
        if not (_COMPARISON_SIGNAL_RE.search(text) or _HINDI_BRAND_VS.search(text)):
            return False

    p = _parse_entities(text, parsed)
    brands = list(p.get("brands") or detect_all_brands(text))
    category = p.get("category") or detect_requested_category(text)

    if len(brands) < 2:
        if not (_HINDI_BRAND_VS.search(text) and category and len(brands) >= 1):
            return False

    # Explicit listing/geo marketplace action in the same message → inventory compare
    if _LISTING_COMPARE_ACTION.search(text):
        if re.search(
            r"\b(?:in|mein|mai|at|near|around)\s+[A-Za-z\u0900-\u097F]{2,}",
            text,
            re.I,
        ):
            return False
        if re.search(r"\b(?:available|listing|milega|dikhao|contact\s+owner|book)\b", text, re.I):
            return False

    return bool(category or len(brands) >= 2)


def _default_spec_rows(brand_a: str, brand_b: str, category: Optional[str]) -> list[dict[str, str]]:
    cat = category_label(category) if category else "Equipment"
    return [
        {"label": "Category", "a": cat, "b": cat},
        {"label": "Brand", "a": brand_a, "b": brand_b},
        {"label": "Typical applications", "a": "—", "b": "—"},
        {"label": "Build quality / durability", "a": "—", "b": "—"},
        {"label": "Fuel efficiency", "a": "—", "b": "—"},
        {"label": "Maintenance / parts availability", "a": "—", "b": "—"},
        {"label": "Operator comfort", "a": "—", "b": "—"},
        {"label": "Resale value", "a": "—", "b": "—"},
        {"label": "Best suited for", "a": "—", "b": "—"},
    ]


def _format_table_md(brand_a: str, brand_b: str, rows: list[dict[str, Any]]) -> str:
    header = f"| Specification | {brand_a} | {brand_b} |"
    divider = "| --- | --- | --- |"
    lines = [
        f"| {r.get('label', '—')} | {r.get('a', '—')} | {r.get('b', '—')} |"
        for r in rows[:12]
    ]
    return "\n".join([header, divider, *lines]) if lines else ""


async def build_brand_advisory_comparison(
    *,
    brands: list[str],
    category: Optional[str],
    user_message: str,
    lang: str = "english",
) -> dict[str, Any]:
    """
    Generate brand-level comparison table + summary via domain knowledge (LLM).
    Does NOT invent live marketplace prices or availability.
    """
    compare_brands = brands[:2] if len(brands) >= 2 else brands
    if len(compare_brands) < 2:
        compare_brands = (compare_brands + ["CAT", "JCB"])[:2]

    brand_a, brand_b = compare_brands[0], compare_brands[1]
    category = _infer_category(user_message, category)
    cat_label = category_label(category) if category else "construction equipment (general)"
    rows = _default_spec_rows(brand_a, brand_b, category)
    summary = ""
    better_overall = brand_a
    value_pick = brand_a
    work_fit = f"Depends on site conditions and job type for {cat_label}."

    try:
        from app.core.config import settings
        if settings.GROQ_API_KEY:
            from app.core.groq_client import groq_chat_completion

            system = (
                "You are InfraForge's heavy-equipment advisor for India. "
                "Compare two brands for a machine category using general industry knowledge. "
                "Return ONLY valid JSON with keys: "
                "rows (array of {label,a,b}), summary (string), better_overall (string), "
                "value_for_money (string), best_for_work (string). "
                "Rules: Do NOT invent live marketplace listings, prices, availability, or owner contact. "
                "Specs may be typical/indicative ranges — say so in summary if uncertain. "
                "Be practical for Indian construction sites."
            )
            user = (
                f"Language for summary: {lang}\n"
                f"Category: {cat_label}\n"
                f"Brand A: {brand_a}\n"
                f"Brand B: {brand_b}\n"
                f"User question: {user_message[:500]}\n"
                "Fill rows with concise comparable specs (applications, durability, fuel, maintenance, "
                "parts network in India, operator comfort, resale, suitability by job scale)."
            )
            raw = groq_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.35,
                tag="brand_advisory_comparison",
            )
            text = ""
            if raw:
                text = (raw.choices[0].message.content or "").strip()
            if text:
                # Strip markdown fences if present
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                data = json.loads(text)
                if isinstance(data.get("rows"), list) and data["rows"]:
                    rows = data["rows"]
                summary = str(data.get("summary") or "").strip()
                better_overall = str(data.get("better_overall") or better_overall).strip()
                value_pick = str(data.get("value_for_money") or value_pick).strip()
                work_fit = str(data.get("best_for_work") or work_fit).strip()
    except Exception as exc:
        print(f"[brand_advisory_comparison] llm_failed: {exc}")

    if not summary:
        summary = (
            f"For {cat_label}, both {brand_a} and {brand_b} are established options in India. "
            f"{brand_a} is often chosen for value and parts availability; "
            f"{brand_b} for specific site requirements. "
            "For live rent/buy prices in your city, I can search current listings."
        )

    table_md = _format_table_md(brand_a, brand_b, rows)
    intro = f"**{cat_label.title()} — {brand_a} vs {brand_b} (general comparison)**"
    msg = intro
    if table_md:
        msg += f"\n\n{table_md}"
    msg += (
        f"\n\n**Summary:** {summary}\n\n"
        f"**Overall:** {better_overall}\n"
        f"**Value for money:** {value_pick}\n"
        f"**Best for your work:** {work_fit}\n\n"
        "_Indicative industry comparison — for live listings and prices in your city, ask me to search._"
    )

    comparison_payload = {
        "comparison_rows": [
            {"label": r.get("label", "—"), "a": r.get("a", "—"), "b": r.get("b", "—"), "key": f"row_{i}"}
            for i, r in enumerate(rows[:12])
        ],
        "llm_summary": summary,
        "better_for_budget": value_pick,
        "better_rating": better_overall,
        "overall_recommendation": better_overall,
        "value_for_money": value_pick,
        "machine_1": {"name": brand_a, "brand": brand_a},
        "machine_2": {"name": brand_b, "brand": brand_b},
        "advisory_comparison": True,
        "cross_type_warning": False,
    }

    return {
        "message": msg,
        "assistant_mode": "comparison",
        "machines": [],
        "comparison": comparison_payload,
        "comparison_rows": comparison_payload["comparison_rows"],
        "llm_summary": summary,
        "better_for_budget": value_pick,
        "better_rating": better_overall,
        "overall_recommendation": better_overall,
        "value_for_money": value_pick,
        "suggestions": [
            f"Search {cat_label} in Jaipur",
            f"Search {brand_a} {cat_label}",
            f"Search {brand_b} {cat_label}",
        ],
    }
