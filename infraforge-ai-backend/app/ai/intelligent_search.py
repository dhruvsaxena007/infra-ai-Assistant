import logging
import re

from app.ai.embedding_service import generate_embedding
from app.ai.category_mapping import category_matches
from app.ai.openai_parser import extract_intent
from app.ai.query_parser import is_empty_filters, parse_query
from app.core.config import settings
from app.ai.search_service import semantic_search
from app.utils.machine_normalizer import build_machine_search_text, rating_score_neutral
from app.utils.machine_repository import (
    build_mongo_filter,
    load_machines_for_semantic_search,
    search_by_filters,
    _matches_post_filters,
)
from app.utils.sanitize import deduplicate_machines

logger = logging.getLogger(__name__)

__all__ = ["search_by_filters", "intelligent_machine_search"]


async def _get_search_filters(query: str) -> dict:
    """
    Rules-first filter extraction. OpenAI intent is used only when the deterministic
    parser cannot extract category, brand, model, city, or price.
    """
    manual = parse_query(query)

    if not is_empty_filters(manual):
        if manual.get("category") or manual.get("brand") or manual.get("model"):
            return manual
        if manual.get("city") and manual.get("max_price") is not None:
            return manual
        if manual.get("pincode") or manual.get("condition") or manual.get("listing_type"):
            return manual

    if not settings.openai_intent_enabled:
        return manual

    try:
        llm = await extract_intent(query)
    except ValueError:
        logger.warning("OpenAI parser unavailable — using manual query parser only")
        return manual

    if is_empty_filters(llm if llm else {}):
        return manual

    merged = dict(llm)
    for key, value in manual.items():
        if value is not None:
            merged[key] = value
    return merged


def _field_in_query(field_value, query: str) -> bool:
    if not field_value:
        return False
    return str(field_value).lower() in query.lower()


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _listing_quality_factor(machine: dict) -> float:
    """Penalize incomplete or low-quality marketplace listings."""
    factor = 1.0
    name = str(machine.get("name") or "").strip()
    category = str(machine.get("category") or "").strip()
    brand = str(machine.get("brand") or "").strip()

    if not category:
        factor *= 0.35
    if not brand and len(name.split()) <= 2:
        factor *= 0.5
    if len(name) <= 4 and name.isupper():
        factor *= 0.4
    generic_names = {"4wd", "diesel", "crawler", "tandem", "drive", "machine"}
    if name.lower() in generic_names:
        factor *= 0.2

    return factor


def _compute_hybrid_score(machine: dict, filters: dict, query: str, similarity: float) -> float:
    category_score = 0.0
    if filters.get("category"):
        if category_matches(machine.get("category"), filters["category"]):
            category_score = 1.0
        elif category_matches(machine.get("category_display"), filters["category"]):
            category_score = 0.85

    city_score = 0.0
    if filters.get("city"):
        mc = str(machine.get("city", "")).lower()
        sc = str(filters["city"]).lower()
        if sc in mc or mc.startswith(sc):
            city_score = 1.0

    brand_score = 0.0
    if filters.get("brand"):
        blob = f"{machine.get('brand', '')} {machine.get('name', '')}".lower()
        if filters["brand"].lower() in blob:
            brand_score = 1.0
    elif _field_in_query(machine.get("brand"), query):
        brand_score = 0.8

    model_score = 0.0
    if filters.get("model"):
        blob = f"{machine.get('model', '')} {machine.get('name', '')}"
        norm_blob = _normalize_token(blob)
        norm_model = _normalize_token(filters["model"])
        if norm_model and norm_model in norm_blob:
            model_score = 1.0
    elif _field_in_query(machine.get("model"), query):
        model_score = 0.9

    name_score = 0.0
    name = str(machine.get("name", "")).lower()
    if name and name in query.lower():
        name_score = 1.0

    price_score = 0.0
    if filters.get("max_price"):
        price = machine.get("price_per_day")
        max_price = filters["max_price"]
        if price is not None and price > 0 and price <= max_price:
            price_score = 1 - (price / max_price)

    availability_score = 1.0 if machine.get("availability") else 0.3

    listing_score = 0.0
    if filters.get("listing_type"):
        if str(machine.get("listing_type") or "").lower() == filters["listing_type"]:
            listing_score = 1.0
    else:
        listing_score = 0.5

    rating_score = rating_score_neutral(machine)

    final_score = (
        category_score * 0.22
        + city_score * 0.18
        + brand_score * 0.10
        + model_score * 0.10
        + name_score * 0.10
        + similarity * 0.12
        + price_score * 0.08
        + availability_score * 0.05
        + listing_score * 0.05
        + rating_score * 0.05
    )

    if filters.get("category") and category_score == 0:
        final_score *= 0.25
    if filters.get("city") and city_score == 0:
        final_score *= 0.5

    final_score *= _listing_quality_factor(machine)
    return round(final_score, 4)


async def intelligent_machine_search(query, database, limit=5):
    filters = await _get_search_filters(query)
    logger.info(f"Extracted filters: {filters}")

    search_text = query
    if filters.get("brand") or filters.get("model") or filters.get("category"):
        search_text = build_machine_search_text(
            {
                "name": query,
                "brand": filters.get("brand"),
                "model": filters.get("model"),
                "category": filters.get("category"),
                "city": filters.get("city"),
            }
        )

    query_embedding = generate_embedding(search_text or query)

    mongo_filter = await build_mongo_filter(database, filters)
    logger.info(f"Mongo filter: {mongo_filter}")

    machines = await load_machines_for_semantic_search(database, filters)

    if not machines and filters.get("category"):
        logger.warning("No MongoDB results — relaxing to category-only fallback")
        machines = await load_machines_for_semantic_search(
            database,
            {"category": filters["category"]},
        )

    if not machines and (filters.get("brand") or filters.get("model")):
        logger.warning("No MongoDB results — loading active listings for brand/model search")
        all_active = await load_machines_for_semantic_search(database, {})
        machines = [m for m in all_active if _matches_post_filters(m, filters)]

    if not machines and (filters.get("city") or filters.get("max_price")):
        machines = await load_machines_for_semantic_search(
            database,
            {"city": filters.get("city"), "max_price": filters.get("max_price")},
        )

    results = semantic_search(query_embedding, machines)

    # Seed/training listings often lack embeddings — rank by filters instead.
    if not results and machines:
        results = list(machines)
        for machine in results:
            machine["similarity_score"] = 0.0

    for machine in results:
        similarity = machine.get("similarity_score", 0)
        machine["final_score"] = _compute_hybrid_score(
            machine, filters, query, similarity
        )

    results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    results = _apply_primary_match_filter(results, filters, limit)
    return deduplicate_machines(results)[:limit]


def _city_matches(machine: dict, city: str) -> bool:
    if not city:
        return True
    mc = str(machine.get("city", "")).lower()
    sc = str(city).lower()
    return sc in mc or mc.startswith(sc)


def _apply_primary_match_filter(results: list, filters: dict, limit: int) -> list:
    """
    When the user asked for a category and/or city, prefer exact matches only
    if any exist — avoid showing unrelated machines as top results.
    """
    if not results:
        return results

    category = filters.get("category")
    city = filters.get("city")

    if category:
        category_hits = [
            m for m in results
            if category_matches(m.get("category"), category)
            or category_matches(m.get("category_display"), category)
        ]
        if category_hits:
            if city:
                city_hits = [m for m in category_hits if _city_matches(m, city)]
                if city_hits:
                    return city_hits[:limit]
            return category_hits[:limit]

    if city:
        city_hits = [m for m in results if _city_matches(m, city)]
        if city_hits:
            return city_hits[:limit]

    brand = filters.get("brand")
    model = filters.get("model")
    if brand or model:
        identity_hits = []
        for machine in results:
            brand_ok = not brand or brand.lower() in f"{machine.get('brand', '')} {machine.get('name', '')}".lower()
            if model:
                blob = _normalize_token(f"{machine.get('model', '')} {machine.get('name', '')}")
                model_ok = _normalize_token(model) in blob
            else:
                model_ok = True
            if brand_ok and model_ok:
                identity_hits.append(machine)
        if identity_hits:
            return identity_hits[:limit]

    return results
