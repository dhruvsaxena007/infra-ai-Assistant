"""
Brand inventory queries — list brands/categories from catalog + live listings.

No hardcoded brands; uses ReferenceCache equipment metadata and Mongo listings.
"""

from __future__ import annotations

from typing import Any

from app.utils.machine_repository import load_machines_for_semantic_search
from app.utils.reference_cache import get_reference_cache


async def _brands_from_listings(
    database,
    *,
    category: str | None = None,
    brand: str | None = None,
    city: str | None = None,
    limit: int = 200,
) -> list[str]:
    filters: dict[str, Any] = {}
    if category:
        filters["category"] = category
    if brand:
        filters["brand"] = brand
    if city:
        filters["city"] = city

    machines = await load_machines_for_semantic_search(database, filters)
    brands: set[str] = set()
    for machine in machines[:limit]:
        name = str(machine.get("brand") or "").strip()
        if name:
            brands.add(name)
    return sorted(brands, key=str.lower)


async def _categories_from_listings(
    database,
    *,
    brand: str,
    city: str | None = None,
    limit: int = 200,
) -> list[str]:
    filters: dict[str, Any] = {"brand": brand}
    if city:
        filters["city"] = city
    machines = await load_machines_for_semantic_search(database, filters)
    categories: set[str] = set()
    for machine in machines[:limit]:
        cat = str(machine.get("category") or "").strip()
        if cat:
            categories.add(cat)
    return sorted(categories, key=str.lower)


async def list_brands_for_category(
    database,
    category: str,
    *,
    city: str | None = None,
) -> list[str]:
    cache = await get_reference_cache(database)
    catalog_brands = cache.brands_for_category(category)
    listing_brands = await _brands_from_listings(database, category=category, city=city)
    merged = sorted(set(catalog_brands) | set(listing_brands), key=str.lower)
    return merged


async def list_categories_for_brand(
    database,
    brand: str,
    *,
    city: str | None = None,
) -> list[str]:
    return await _categories_from_listings(database, brand=brand, city=city)


def _format_brand_list(brands: list[str], *, lang: str) -> str:
    if not brands:
        if lang == "english":
            return "I could not find listed brands for that category yet."
        return "Is category ke liye abhi koi brand listing nahi mili."
    preview = ", ".join(brands[:12])
    more = len(brands) - 12
    suffix = f" and {more} more" if more > 0 else ""
    if lang == "english":
        return f"Available brands include: {preview}{suffix}."
    return f"Available brands: {preview}{suffix}."


def _format_category_list(categories: list[str], brand: str, *, lang: str) -> str:
    if not categories:
        if lang == "english":
            return f"Which machine category should I check for {brand} — excavator, road roller, crane, or another type?"
        return f"{brand} ke liye kaunsi machine category check karun — excavator, road roller, crane?"
    preview = ", ".join(categories[:8])
    if lang == "english":
        return f"{brand} appears in these categories: {preview}."
    return f"{brand} in categories me available hai: {preview}."


async def build_brand_inventory_reply(
    database,
    *,
    selected_action: str,
    category: str | None,
    brand: str | None,
    city: str | None,
    lang: str = "english",
) -> dict[str, Any]:
    """
    Build reply payload for brand inventory actions.
    Returns dict with message, suggestions, brands/categories lists, assistant_mode.
    """
    if selected_action == "query_brands_by_category" and category:
        brands = await list_brands_for_category(database, category, city=city)
        loc = f" in {city}" if city else ""
        if lang == "english":
            intro = f"For {category}{loc}, "
        else:
            intro = f"{category}{loc} ke liye, "
        if brands:
            message = intro + _format_brand_list(brands, lang=lang).lower()
            if message and message[0].islower():
                message = message[0].upper() + message[1:]
            return {
                "message": message,
                "brands": brands,
                "assistant_mode": "brand_inventory",
                "suggestions": brands[:6],
                "should_search_machines": False,
            }

        from app.ai.no_result_recovery import run_brand_inventory_recovery

        recovery = await run_brand_inventory_recovery(
            database,
            category=category,
            brand=brand,
            city=city,
            brands_found=[],
            lang=lang,
        )
        facts = recovery.get("message_facts")
        if isinstance(facts, str):
            body = facts
        else:
            body = _format_brand_list([], lang=lang)
        message = intro + body.lower()
        if message and message[0].islower():
            message = message[0].upper() + message[1:]
        return {
            "message": message,
            "brands": [],
            "assistant_mode": "brand_inventory",
            "suggestions": recovery.get("suggestions") or ["Search machines directly", "Contact support"],
            "should_search_machines": False,
            "recovery_type": recovery.get("recovery_type"),
            "no_result_recovery": {
                "recovery_type": recovery.get("recovery_type"),
                "safe_alternatives": recovery.get("safe_alternatives"),
                "suggestions": recovery.get("suggestions"),
                "next_best_action": recovery.get("next_best_action"),
            },
        }

    if selected_action == "list_categories_for_brand" and brand:
        categories = await list_categories_for_brand(database, brand, city=city)
        message = _format_category_list(categories, brand, lang=lang)
        mode = "brand_inventory" if categories else "clarification"
        return {
            "message": message,
            "categories": categories,
            "assistant_mode": mode,
            "suggestions": categories[:6] or ["Excavator", "Road Roller", "Crane", "Backhoe Loader"],
            "should_search_machines": False,
        }

    if lang == "english":
        message = "Which machine category should I check brands for — excavator, road roller, crane, or another type?"
    else:
        message = "Kaunsi machine category ke brands chahiye — excavator, road roller, crane?"
    return {
        "message": message,
        "assistant_mode": "clarification",
        "suggestions": ["Road Roller", "Excavator", "Crane", "Backhoe Loader"],
        "should_search_machines": False,
    }
