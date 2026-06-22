"""
Domain Recommendation Engine — generalized task→machine mapping.

Maps work_purpose, material, project_type to suitable machines using
structural signals + purpose taxonomy catalog. NOT phrase-specific.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.purpose_taxonomy import (
    categories_for_purpose,
    primary_category_for_purpose,
    purpose_category_ambiguous,
)
from app.ai.query_parser import parse_query

# Work-type / project structural signals
_WORK_PURPOSE_RE = re.compile(
    r"\b(?:digging|excavat(?:e|ion)|trenching|earth(?:mov|work)|loading|lifting|"
    r"compaction|leveling|grading|transport|hauling|drilling|concrete|piling)\b",
    re.I,
)

_PROJECT_TYPE_RE = re.compile(
    r"\b(?:road\s+project|highway|building\s+construction|foundation|"
    r"demolition|mining|quarry|pipeline|bridge|metro|site\s+work)\b",
    re.I,
)

_MATERIAL_RE = re.compile(
    r"\b(?:heavy\s+rocks?|rock|boulder|soil|sand|gravel|aggregate|concrete|"
    r"asphalt|hard\s+ground|soft\s+soil)\b",
    re.I,
)

_RECOMMENDATION_SIGNAL_RE = re.compile(
    r"\b(?:best|recommend|suggest|suitable|ideal|which\s+machine|what\s+machine|"
    r"kaunsi|konsi|chahiye\s+kaunsi)\b",
    re.I,
)

# Project → purpose mapping (structural, not phrase hacks)
_PROJECT_TO_PURPOSE: dict[str, str] = {
    "road": "compaction",
    "highway": "compaction",
    "foundation": "digging",
    "building": "digging",
    "demolition": "digging",
    "mining": "digging",
    "quarry": "digging",
    "pipeline": "digging",
    "bridge": "lifting",
    "metro": "digging",
}

_MATERIAL_TO_PURPOSE: dict[str, str] = {
    "rock": "digging",
    "boulder": "digging",
    "heavy rock": "digging",
    "soil": "digging",
    "sand": "loading",
    "gravel": "loading",
    "aggregate": "loading",
    "concrete": "concrete",
    "asphalt": "compaction",
}


def detect_work_signals(message: str) -> dict[str, Any]:
    """Extract structural work/purpose/project signals from message."""
    text = (message or "").strip()
    lower = text.lower()
    signals: dict[str, Any] = {
        "work_purpose": None,
        "project_type": None,
        "material": None,
        "is_recommendation_request": bool(_RECOMMENDATION_SIGNAL_RE.search(text)),
    }

    from app.chatbot.assistant_intelligence import resolve_purpose_key

    pk = resolve_purpose_key(text)
    if pk:
        signals["work_purpose"] = pk

    if _WORK_PURPOSE_RE.search(text) and not pk:
        for purpose in ("digging", "loading", "lifting", "compaction", "leveling", "transport", "drilling", "concrete"):
            if purpose in lower or purpose.replace("ing", "") in lower:
                signals["work_purpose"] = purpose
                break

    m = _PROJECT_TYPE_RE.search(text)
    if m:
        proj = m.group(0).lower()
        signals["project_type"] = proj
        for key, purpose in _PROJECT_TO_PURPOSE.items():
            if key in proj and not signals["work_purpose"]:
                signals["work_purpose"] = purpose

    m = _MATERIAL_RE.search(text)
    if m:
        mat = m.group(0).lower()
        signals["material"] = mat
        for key, purpose in _MATERIAL_TO_PURPOSE.items():
            if key in mat and not signals["work_purpose"]:
                signals["work_purpose"] = purpose

    return signals


def recommend_machine_categories(
    message: str,
    *,
    parsed: dict | None = None,
    city: str | None = None,
) -> dict[str, Any]:
    """
    Return recommendation plan: purpose, categories, primary category, ambiguity.
    """
    parsed = dict(parsed or parse_query(message or ""))
    signals = detect_work_signals(message)
    purpose = signals.get("work_purpose") or parsed.get("purpose_key")
    explicit_cat = parsed.get("category")

    if explicit_cat:
        categories = [explicit_cat]
        primary = explicit_cat
        ambiguous = False
    elif purpose:
        categories = categories_for_purpose(purpose)
        primary = primary_category_for_purpose(purpose)
        ambiguous = purpose_category_ambiguous(purpose)
    else:
        categories = []
        primary = None
        ambiguous = False

    return {
        "purpose_key": purpose,
        "categories": categories,
        "primary_category": primary,
        "ambiguous": ambiguous,
        "project_type": signals.get("project_type"),
        "material": signals.get("material"),
        "is_recommendation_request": signals.get("is_recommendation_request"),
        "city": city or parsed.get("city"),
        "needs_city": not bool(city or parsed.get("city")),
        "needs_clarification": not primary and signals.get("is_recommendation_request"),
        "signals": signals,
    }


def build_recommendation_context(
    message: str,
    *,
    parsed: dict | None = None,
    conv_state: dict | None = None,
) -> dict[str, Any]:
    """Build recommendation context for session state tracking."""
    state = conv_state or {}
    collected = state.get("collected_fields") or {}
    plan = recommend_machine_categories(
        message,
        parsed=parsed,
        city=collected.get("city"),
    )
    return {
        "purpose_key": plan.get("purpose_key"),
        "primary_category": plan.get("primary_category"),
        "categories": plan.get("categories"),
        "project_type": plan.get("project_type"),
        "material": plan.get("material"),
        "city": plan.get("city"),
        "ambiguous": plan.get("ambiguous"),
    }


def is_domain_recommendation_query(message: str, *, parsed: dict | None = None) -> bool:
    """True when message is an in-domain advisory/recommendation request."""
    parsed = parsed or parse_query(message or "")
    signals = detect_work_signals(message)

    # Complete search (category + city) without explicit recommend → machine search
    if parsed.get("category") and parsed.get("city") and not signals.get("is_recommendation_request"):
        return False

    if signals.get("is_recommendation_request"):
        return True
    if (signals.get("work_purpose") or signals.get("project_type") or signals.get("material")) and not (
        parsed.get("category") and parsed.get("city")
    ):
        return True
    from app.chatbot.assistant_intelligence import is_recommendation_query

    return bool(is_recommendation_query(message) or parsed.get("purpose_key"))


def build_recommendation_advisory_draft(plan: dict[str, Any], *, lang: str = "english") -> dict[str, Any]:
    """Practical recommendation advisory — no stale search dump."""
    from app.ai.category_mapping import category_label
    from app.chatbot.language import pick_lang

    purpose = plan.get("purpose_key")
    primary = plan.get("primary_category")
    cats = plan.get("categories") or []
    material = plan.get("material")
    project = plan.get("project_type")

    if primary:
        labels = [category_label(c) or c for c in cats[:4]]
        cat_text = ", ".join(labels) if labels else category_label(primary) or primary
        if lang == "hindi":
            msg = (
                f"Aapke kaam ke liye **{category_label(primary) or primary}** sabse suitable category hai. "
                f"Related options: {cat_text}. "
                f"City aur budget bata dein to main available listings shortlist kar dunga."
            )
        elif lang == "hinglish":
            msg = (
                f"Is task ke liye **{category_label(primary) or primary}** best category hai. "
                f"Similar options: {cat_text}. "
                f"Agar city aur budget bata do to main available machines dikha dunga."
            )
        else:
            msg = (
                f"For this job, **{category_label(primary) or primary}** is the most suitable machine category. "
                f"Related options include {cat_text}. "
                f"Share your city and budget if you want me to show available listings."
            )
    elif purpose:
        if lang == "hinglish":
            msg = (
                f"**{purpose.replace('_', ' ').title()}** ke liye main suitable machine categories suggest kar sakta hoon. "
                f"City bata dein to listings dikha dunga."
            )
        else:
            msg = (
                f"For **{purpose.replace('_', ' ')}** work, I can recommend suitable machine categories. "
                f"Tell me your city if you want available listings."
            )
    else:
        msg = pick_lang(
            lang,
            english="Tell me what work you need the machine for (digging, road work, lifting, transport) and your city — I'll recommend the best options.",
            hindi="Bataiye kaunsa kaam hai (khudai, road, lifting, transport) aur city — main best machine suggest karunga.",
            hinglish="Kaunsa kaam hai (digging, road, lifting) aur city batao — main best machine recommend karunga.",
        )

    if material and primary:
        msg += pick_lang(
            lang,
            english=f" For carrying {material}, loaders or dump trucks may also help depending on distance.",
            hindi=f" {material} ke liye loader ya dump truck bhi useful ho sakte hain.",
            hinglish=f" {material} ke liye loader/dump truck bhi option ho sakta hai.",
        )

    return {
        "message": msg,
        "response_goal": "recommendation_advisory",
        "assistant_mode": "recommendation",
        "suggestions": ["Search Machine", "Compare brands", "Tell city for listings"],
    }
