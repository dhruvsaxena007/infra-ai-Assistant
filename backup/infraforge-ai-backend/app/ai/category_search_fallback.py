"""
Tiered category search with honest city fallback (used by image-search + chat).
"""

from __future__ import annotations

from app.ai.category_mapping import category_label
from app.utils.machine_repository import search_by_filters
from app.utils.sanitize import deduplicate_machines, without_embeddings


async def search_category_with_fallback(
    database,
    category: str,
    *,
    city: str | None = None,
    max_price: int | None = None,
    limit: int = 5,
) -> tuple[list, dict]:
    """
    Returns (machines, meta) where meta explains exact vs fallback.
    """
    label = category_label(category)
    meta = {
        "exact_match": False,
        "fallback_used": False,
        "fallback_reason": None,
        "matched_category": category,
    }

    exact = await search_by_filters(
        database,
        category=category,
        city=city,
        max_price=max_price,
        limit=limit,
        exact_category=True,
    )
    if exact:
        meta["exact_match"] = True
        return deduplicate_machines(without_embeddings(exact)), meta

    # Same category, other cities
    alt = await search_by_filters(
        database,
        category=category,
        city=None,
        max_price=max_price,
        limit=limit,
        exact_category=True,
    )
    if alt:
        meta["fallback_used"] = True
        cities = sorted({str(m.get("city") or "").title() for m in alt if m.get("city")})
        city_hint = ", ".join(cities[:3])
        if city:
            meta["fallback_reason"] = (
                f"No {label} in {city.title()}. "
                f"Showing available {label} in {city_hint or 'other cities'}."
            )
        else:
            meta["fallback_reason"] = f"Showing available {label} listings."
        return deduplicate_machines(without_embeddings(alt)), meta

    # Drop budget
    if max_price is not None:
        alt = await search_by_filters(
            database,
            category=category,
            city=city,
            max_price=None,
            limit=limit,
            exact_category=True,
        )
        if alt:
            meta["fallback_used"] = True
            meta["fallback_reason"] = (
                f"No {label} under ₹{max_price}. Showing options above your budget."
            )
            return deduplicate_machines(without_embeddings(alt)), meta

    meta["fallback_reason"] = f"No {label} listings found in the marketplace right now."
    return [], meta
