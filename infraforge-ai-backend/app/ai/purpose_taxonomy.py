"""
Central purpose → category taxonomy for marketplace requirement collection.

Single catalog source — router branches must not hardcode purpose mappings.
"""

from __future__ import annotations

from typing import Optional

# Canonical purpose key → machine categories (ordered by preference)
PURPOSE_TO_CATEGORIES: dict[str, list[str]] = {
    "digging": ["excavator", "backhoe loader"],
    "loading": ["wheel loader", "backhoe loader", "forklift"],
    "lifting": ["crane", "hydra crane"],
    "compaction": ["road roller", "compactor"],
    "leveling": ["motor grader"],
    "transport": ["dump truck", "tipper"],
    "drilling": ["crawler drill"],
    "concrete": ["concrete mixer", "concrete pump", "concrete mixer truck"],
    "demolition": ["excavator", "mobile crusher", "backhoe loader"],
}


def categories_for_purpose(purpose_key: str) -> list[str]:
    """All categories suitable for a canonical purpose key."""
    from app.chatbot.assistant_intelligence import PURPOSE_ALIASES

    key = PURPOSE_ALIASES.get((purpose_key or "").lower(), purpose_key)
    return list(PURPOSE_TO_CATEGORIES.get(key or "", []))


def primary_category_for_purpose(purpose_key: str) -> Optional[str]:
    """Best default category — first catalog entry, not per-purpose hardcoding."""
    cats = categories_for_purpose(purpose_key)
    return cats[0] if cats else None


def purpose_category_ambiguous(purpose_key: str) -> bool:
    """True when purpose maps to multiple categories and needs disambiguation."""
    return len(categories_for_purpose(purpose_key)) > 1


def category_compatible_with_purpose(category: str, purpose_key: str) -> bool:
    cat = (category or "").lower().strip()
    return cat in categories_for_purpose(purpose_key)


def resolve_derived_category(
    purpose_key: str | None,
    *,
    explicit_category: str | None = None,
) -> dict:
    """
    Return derived category recommendation from purpose.
    Explicit category always wins; conflicts return needs_confirmation.
    """
    purpose_key = (purpose_key or "").strip().lower() or None
    explicit = (explicit_category or "").strip().lower() or None
    cats = categories_for_purpose(purpose_key) if purpose_key else []

    if explicit and purpose_key:
        if category_compatible_with_purpose(explicit, purpose_key):
            return {
                "category": explicit,
                "source": "explicit",
                "ambiguous": False,
                "needs_confirmation": False,
                "alternatives": [c for c in cats if c != explicit],
            }
        return {
            "category": explicit,
            "derived_recommendation": cats[0] if cats else None,
            "source": "explicit_conflict",
            "ambiguous": True,
            "needs_confirmation": True,
            "alternatives": cats,
        }

    if explicit:
        return {
            "category": explicit,
            "source": "explicit",
            "ambiguous": False,
            "needs_confirmation": False,
            "alternatives": [],
        }

    if not cats:
        return {
            "category": None,
            "source": None,
            "ambiguous": False,
            "needs_confirmation": False,
            "alternatives": [],
        }

    return {
        "category": cats[0],
        "source": "derived_from_purpose",
        "ambiguous": len(cats) > 1,
        "needs_confirmation": False,
        "alternatives": cats[1:],
    }
