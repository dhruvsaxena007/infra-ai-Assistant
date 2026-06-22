"""
Contextual and multi-purpose advisory responses.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.category_mapping import category_label
from app.ai.conversation_context import category_fits_purpose
from app.chatbot.assistant_intelligence import (
    _PURPOSE_LABELS,
    all_categories_for_purpose,
    primary_category_for_purpose,
)
from app.utils.machine_repository import search_by_filters
from app.utils.sanitize import deduplicate_machines, without_embeddings


def build_suitability_response(
    *,
    machine: dict,
    purpose_key: Optional[str],
    city: Optional[str],
    lang: str = "english",
) -> dict[str, Any]:
    """Explain whether ONE referenced machine fits stated work."""
    name = machine.get("name") or "This machine"
    cat = machine.get("category") or ""
    cat_label = category_label(cat) if cat else "machine"
    purpose_key = purpose_key or "digging"
    purpose_label = _PURPOSE_LABELS.get(purpose_key, purpose_key)
    city_title = (city or machine.get("city") or "").title() or "your area"
    fits = category_fits_purpose(cat, purpose_key)

    better = primary_category_for_purpose(purpose_key)
    better_label = category_label(better) if better else "another machine type"
    alt_cats = all_categories_for_purpose(purpose_key)
    alt_labels = [category_label(c) for c in alt_cats[:3] if c != cat]

    if fits:
        msg = (
            f"Yes — {name} ({cat_label}) can be used for {purpose_label.lower()}. "
            f"Check specs and rent terms on the card."
        )
        if lang == "hinglish":
            msg = (
                f"Haan — {name} ({cat_label}) {purpose_label.lower()} ke liye use ho sakta hai."
            )
        mode = "recommendation"
    else:
        alt_text = ", ".join(alt_labels) if alt_labels else better_label
        msg = (
            f"{name} is a {cat_label} — not the primary choice for {purpose_label.lower()}. "
            f"Better options: {alt_text}."
        )
        if lang == "hinglish":
            msg = (
                f"{name} ({cat_label}) {purpose_label.lower()} ke liye primary choice nahi hai. "
                f"Better: {alt_text}."
            )
        mode = "clarification"

    suggestions = [f"{category_label(c)} in {city_title}" for c in alt_cats[:2] if city]
    if not suggestions and better and city:
        suggestions.append(f"{better_label} in {city_title}")

    return {
        "message": msg,
        "assistant_mode": mode,
        "suggestions": suggestions[:4] or ["Search machine", "Contact support"],
        "handover": None,
        "keep_last_machines": True,
    }


async def build_multi_purpose_advisory(
    database,
    *,
    purposes: list[str],
    city: Optional[str],
    lang: str = "english",
    limit_per_purpose: int = 2,
) -> dict[str, Any]:
    """
    Answer multi-task / indirect queries like:
    'machines for road digging and compact concrete — suggest suitable ones'
    """
    if not purposes:
        purposes = ["digging"]

    lines: list[str] = []
    all_machines: list[dict] = []
    chips: list[str] = []

    for pk in purposes:
        label = _PURPOSE_LABELS.get(pk, pk)
        cats = all_categories_for_purpose(pk)
        cat_labels = [category_label(c) for c in cats[:4]]
        primary = primary_category_for_purpose(pk)

        lines.append(f"{label}: {', '.join(cat_labels)}")

        if primary and city:
            raw = await search_by_filters(
                database,
                category=primary,
                city=city,
                limit=limit_per_purpose,
                exact_category=True,
            )
            found = deduplicate_machines(without_embeddings(raw))
            all_machines.extend(found)
            chips.append(f"{category_label(primary)} in {city.title()}")

    city_note = f" in {city.title()}" if city else ""

    if lang == "hinglish":
        intro = f"Aapke kaam ke liye ye machines suitable hain{city_note}:\n\n"
        if not city:
            intro = "Aapke kaam ke liye ye machine types suitable hain:\n\n"
        msg = intro + "\n".join(f"• {line}" for line in lines)
        if all_machines:
            msg += f"\n\n{city.title() if city else 'City'} me kuch options:"
        elif city:
            msg += "\n\nExact match limited ho sakta hai — nearby city ya similar category try karein."
        else:
            msg += "\n\nKaunsi city me machine chahiye? City bataiye, main search kar dunga."
    else:
        intro = f"For your work, these machine types fit best{city_note}:\n\n"
        if not city:
            intro = "For your work, these machine types fit best:\n\n"
        msg = intro + "\n".join(f"• {line}" for line in lines)
        if all_machines:
            msg += f"\n\nHere are some listings{city_note}:"
        elif city:
            msg += "\n\nLimited exact matches — I can broaden to nearby cities or similar categories."
        else:
            msg += "\n\nWhich city should I search in? Share the city and I'll find listings."

    return {
        "message": msg,
        "assistant_mode": "recommendation",
        "machines": deduplicate_machines(all_machines)[:8],
        "suggestions": chips[:4] or ["Excavator in Jaipur", "Road roller in Jaipur", "Contact support"],
        "handover": None,
    }


def build_advisory_clarification(*, lang: str = "english") -> dict[str, Any]:
    """Never stuck — ask what work they need."""
    if lang == "hinglish":
        msg = (
            "Main help kar sakta hoon. Bataiye kaam kya hai — digging, road work, "
            "concrete, lifting, transport? Aur city kya hai?"
        )
    else:
        msg = (
            "I can suggest the right machines. What work do you need — digging, "
            "compaction, concrete, lifting, transport? And which city?"
        )
    return {
        "message": msg,
        "assistant_mode": "clarification",
        "machines": [],
        "suggestions": [
            "Excavator in Jaipur",
            "Road roller in Delhi",
            "Road project machines",
            "Contact support",
        ],
        "handover": None,
    }
