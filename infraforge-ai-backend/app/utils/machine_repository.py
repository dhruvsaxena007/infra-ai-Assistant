"""
Centralized machine data access for the AI assistant.

All MongoDB reads for listings go through this module. Raw documents are
normalized before being returned — AI services and API routes should never
query field names like rentalPrice or equipmentCategory directly.
"""

from __future__ import annotations

import re
from typing import Optional

from bson import ObjectId

from app.utils.machine_mapper import is_marketplace_document
from app.utils.machine_normalizer import finalize_normalized_machine, normalize_machine
from app.utils.reference_cache import get_reference_cache


def _database_unavailable(database) -> bool:
    return database is None


async def detect_schema_mode(database) -> str:
    """
    Detect how machines are stored. Returns 'mixed' when both marketplace
    listings and seed/training documents coexist (common after seed_training_machines).
    """
    if _database_unavailable(database):
        return "seed"
    marketplace_count = await database.machines.count_documents(
        {
            "$or": [
                {"equipmentCategory": {"$exists": True, "$ne": None}},
                {"rentalPrice": {"$exists": True, "$ne": None}},
                {"listingType": {"$exists": True, "$ne": None}},
            ]
        }
    )
    seed_count = await database.machines.count_documents(
        {
            "$or": [
                {"source": {"$in": ["training_seed", "seed_sample"]}},
                {
                    "category": {"$exists": True, "$ne": ""},
                    "equipmentCategory": {"$exists": False},
                },
            ]
        }
    )
    if marketplace_count > 0 and seed_count > 0:
        return "mixed"
    if marketplace_count > 0:
        return "marketplace"
    return "seed"


def _seed_document_clause() -> dict:
    """Match seed / training documents (plain category field, no equipmentCategory)."""
    return {
        "$or": [
            {"source": {"$in": ["training_seed", "seed_sample"]}},
            {
                "category": {"$exists": True, "$ne": ""},
                "equipmentCategory": {"$exists": False},
            },
        ]
    }


async def fetch_raw_machine_by_id(database, machine_id: str) -> Optional[dict]:
    if not machine_id:
        return None
    if ObjectId.is_valid(machine_id):
        doc = await database.machines.find_one({"_id": ObjectId(machine_id)})
        if doc:
            return doc
    doc = await database.machines.find_one({"_id": machine_id})
    if doc:
        return doc
    doc = await database.machines.find_one({"id": machine_id})
    if doc:
        return doc
    return await database.machines.find_one({"slug": machine_id})


async def fetch_machine_by_id(database, machine_id: str) -> Optional[dict]:
    raw = await fetch_raw_machine_by_id(database, machine_id)
    if not raw:
        return None
    cache = await get_reference_cache(database)
    return normalize_machine(raw, cache)


async def fetch_all_raw_machines(database, query: dict | None = None) -> list:
    docs = []
    cursor = database.machines.find(query or {})
    async for doc in cursor:
        docs.append(doc)
    return docs


async def fetch_machines(
    database,
    query: dict | None = None,
    *,
    limit: int | None = None,
) -> list:
    cache = await get_reference_cache(database)
    docs = await fetch_all_raw_machines(database, query)
    normalized = [normalize_machine(doc, cache) for doc in docs if doc]
    if limit is not None:
        return normalized[:limit]
    return normalized


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _matches_post_filters(machine: dict, filters: dict) -> bool:
    """In-memory refinement for brand/model/condition/pincode/listing_type."""
    brand = filters.get("brand")
    if brand:
        mb = str(machine.get("brand") or "").lower()
        name_blob = str(machine.get("name", "")).lower()
        brand_token = brand.lower()
        if (
            brand_token not in mb
            and brand_token not in name_blob
            and _normalize_token(brand) not in _normalize_token(f"{mb} {name_blob}")
        ):
            return False

    model = filters.get("model")
    if model:
        text = " ".join(
            [
                str(machine.get("model") or ""),
                str(machine.get("name") or ""),
            ]
        ).lower()
        norm_text = _normalize_token(text)
        norm_model = _normalize_token(model)
        if norm_model and norm_model not in norm_text:
            return False

    condition = filters.get("condition")
    if condition:
        specs = machine.get("specifications") or {}
        mc = str(specs.get("condition") or "").lower()
        if condition.lower() not in mc:
            return False

    pincode = filters.get("pincode")
    if pincode:
        specs = machine.get("specifications") or {}
        mp = str(specs.get("pincode") or "")
        if pincode not in mp:
            return False

    listing_type = filters.get("listing_type")
    if listing_type:
        from app.utils.machine_normalizer import normalize_listing_type_filter, normalize_listing_type_stored
        want = normalize_listing_type_filter(listing_type) or str(listing_type).lower()
        have = normalize_listing_type_stored(machine.get("listing_type"))
        if have != want:
            return False

    rent_type = filters.get("rent_type")
    if rent_type:
        if str(machine.get("rent_type") or "").lower() != rent_type.lower():
            return False

    max_price = filters.get("max_price")
    if max_price is not None:
        price = machine.get("price_per_day")
        if price is None or price > max_price:
            return False

    return True


def _seed_mongo_filter(filters: dict) -> dict:
    mongo_filter = {}

    category = filters.get("category")
    if category:
        mongo_filter["category"] = {
            "$regex": f"^{re.escape(category)}$",
            "$options": "i",
        }

    city = filters.get("city")
    if city:
        mongo_filter["city"] = {
            "$regex": re.escape(city),
            "$options": "i",
        }

    max_price = filters.get("max_price")
    if max_price is not None:
        mongo_filter["price_per_day"] = {"$lte": max_price}

    return mongo_filter


def _flex_ref_ids(values) -> list:
    """Match Mongo refs stored as either string or ObjectId."""
    out = []
    seen = set()
    for value in values or []:
        for candidate in (value, str(value)):
            if candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
            if ObjectId.is_valid(str(value)):
                oid = ObjectId(str(value))
                if oid not in seen:
                    seen.add(oid)
                    out.append(oid)
    return out


def _mixed_mongo_filter(filters: dict, cache) -> dict:
    """Query both seed (plain fields) and marketplace (refs) documents."""
    seed_branch = _seed_mongo_filter(filters)
    seed_clause = _seed_document_clause()
    if seed_branch:
        seed_query: dict = {"$and": [seed_clause, seed_branch]}
    else:
        seed_query = seed_clause

    marketplace_query = _marketplace_mongo_filter(filters, cache)
    return {"$or": [seed_query, marketplace_query]}


def _marketplace_mongo_filter(filters: dict, cache) -> dict:
    clauses = [
        {"status": "active"},
        {"visibility": "public"},
    ]

    category = filters.get("category")
    if category:
        cat_ids = cache.category_ids_for_query(category)
        if cat_ids:
            clauses.append({"equipmentCategory": {"$in": _flex_ref_ids(cat_ids)}})

    city = filters.get("city")
    if city:
        city_ids = cache.city_ids_for_name(city)
        city_clauses = [
            {"equipmentLocation": {"$regex": re.escape(city), "$options": "i"}},
        ]
        if city_ids:
            city_clauses.append({"city": {"$in": _flex_ref_ids(city_ids)}})
        clauses.append({"$or": city_clauses})

    listing_type = filters.get("listing_type")
    if listing_type:
        from app.utils.machine_normalizer import normalize_listing_type_filter
        lt = normalize_listing_type_filter(listing_type) or str(listing_type).lower()
        clauses.append({"listingType": lt})

    max_price = filters.get("max_price")
    if max_price is not None:
        clauses.append(
            {
                "$or": [
                    {"rentalPrice": {"$lte": max_price}},
                    {"sellingPrice": {"$lte": max_price}},
                ]
            }
        )

    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


async def build_mongo_filter(database, filters: dict, *, exact_category: bool = True) -> dict:
    cache = await get_reference_cache(database)
    mode = await detect_schema_mode(database)

    if mode == "mixed":
        return _mixed_mongo_filter(filters, cache)

    if mode == "marketplace":
        return _marketplace_mongo_filter(filters, cache)

    mongo_filter = _seed_mongo_filter(filters)
    if not exact_category and filters.get("category"):
        mongo_filter["category"] = {
            "$regex": re.escape(filters["category"]),
            "$options": "i",
        }
    return mongo_filter


async def search_by_filters(
    database,
    *,
    category=None,
    city=None,
    max_price=None,
    brand=None,
    model=None,
    condition=None,
    pincode=None,
    listing_type=None,
    rent_type=None,
    limit=5,
    exact_category=True,
    sort_by="rating",
    filters: dict | None = None,
) -> list:
    """Deterministic filter search returning normalized machines."""
    if _database_unavailable(database):
        print("[machine_repository] search skipped — database unavailable")
        return []

    merged = dict(filters or {})
    merged.update(
        {
            k: v
            for k, v in {
                "category": category,
                "city": city,
                "max_price": max_price,
                "brand": brand,
                "model": model,
                "condition": condition,
                "pincode": pincode,
                "listing_type": listing_type,
                "rent_type": rent_type,
            }.items()
            if v is not None
        }
    )

    mongo_filter = await build_mongo_filter(
        database,
        merged,
        exact_category=exact_category,
    )

    cache = await get_reference_cache(database)
    docs = []

    cursor = database.machines.find(mongo_filter)
    async for machine in cursor:
        normalized = normalize_machine(machine, cache)
        if _matches_post_filters(normalized, merged):
            docs.append(normalized)

    def _price(m):
        value = m.get("price_per_day")
        return value if value is not None else float("inf")

    if sort_by == "price":
        docs.sort(key=_price)
    else:
        docs.sort(key=lambda m: (-(m.get("rating") or 0), _price(m)))

    return docs[:limit]


async def nearby_cities_with_listings(
    database,
    city: str,
    *,
    limit: int = 3,
) -> list[str]:
    """Cities in the same region (then nationally) that have at least one listing."""
    from app.ai.category_mapping import KNOWN_CITIES, REGION_MAP

    city = (city or "").strip().lower()
    if not city:
        return []

    candidates: list[str] = []
    for cities in REGION_MAP.values():
        if city in cities:
            candidates = [c for c in cities if c != city]
            break
    if not candidates:
        candidates = [c for c in KNOWN_CITIES if c != city]

    found: list[str] = []
    for candidate in candidates:
        batch = await search_by_filters(
            database,
            city=candidate,
            limit=1,
            exact_category=False,
        )
        if batch:
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


async def available_categories_in_city(
    database,
    city: str,
    *,
    limit: int = 150,
) -> list[str]:
    """
    Return canonical categories that have at least one listing in the given city.
    Sorted by listing count (most available first).
    """
    city = (city or "").strip().lower()
    if not city:
        return []

    machines = await search_by_filters(
        database,
        city=city,
        limit=limit,
        exact_category=False,
    )
    counts: dict[str, int] = {}
    for machine in machines:
        cat = str(machine.get("category") or "").strip().lower()
        if cat:
            counts[cat] = counts.get(cat, 0) + 1

    return [
        cat for cat, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


async def search_by_region(
    database,
    *,
    region_cities: list[str],
    category=None,
    max_price=None,
    limit=5,
    filters: dict | None = None,
) -> list:
    """Search machines across multiple cities in a region."""
    if not region_cities:
        return []

    seen_ids: set[str] = set()
    combined: list = []
    per_city = max(2, limit // max(len(region_cities), 1) + 1)

    for city_name in region_cities:
        batch = await search_by_filters(
            database,
            category=category,
            city=city_name,
            max_price=max_price,
            limit=per_city,
            exact_category=True,
            filters={**(filters or {}), "city": city_name},
        )
        for machine in batch:
            mid = str(machine.get("id") or machine.get("_id") or "")
            if mid and mid in seen_ids:
                continue
            if mid:
                seen_ids.add(mid)
            combined.append(machine)
        if len(combined) >= limit:
            break

    return combined[:limit]


async def load_machines_for_semantic_search(
    database,
    filters: dict | None = None,
    *,
    include_pending: bool = False,
) -> list:
    """
    Load normalized machines for hybrid ranking.

    When include_pending is False (default), marketplace mode still loads active
    public listings from Mongo; post-filters refine brand/model/etc.
    """
    filters = filters or {}
    cache = await get_reference_cache(database)
    mode = await detect_schema_mode(database)

    if mode == "marketplace" and include_pending:
        query = {"visibility": "public"}
    else:
        query = await build_mongo_filter(database, filters)

    docs = []
    cursor = database.machines.find(query)
    async for raw in cursor:
        normalized = normalize_machine(raw, cache)
        if _matches_post_filters(normalized, filters):
            docs.append(normalized)
    return docs


async def find_similar_raw_for_insights(
    database,
    machine: dict,
    *,
    exclude_id: str,
    limit: int = 100,
) -> list:
    cache = await get_reference_cache(database)
    mode = await detect_schema_mode(database)
    category = machine.get("category")
    city = machine.get("city")
    listing_type = machine.get("listing_type")

    exclude_clauses = []
    if ObjectId.is_valid(exclude_id):
        exclude_clauses.append({"_id": {"$ne": ObjectId(exclude_id)}})
    exclude_clauses.append({"_id": {"$ne": exclude_id}})

    if mode == "mixed":
        query: dict = {"$and": exclude_clauses}
        cat_ids = cache.category_ids_for_query(category)
        seed_part: dict = {"category": category}
        if city:
            seed_part["city"] = {"$regex": re.escape(city), "$options": "i"}
        mp_part: dict = {"status": "active", "visibility": "public"}
        if cat_ids:
            mp_part["equipmentCategory"] = {"$in": _flex_ref_ids(cat_ids)}
        if listing_type:
            mp_part["listingType"] = listing_type
        if city:
            city_ids = cache.city_ids_for_name(city)
            mp_part["$or"] = [
                {"equipmentLocation": {"$regex": re.escape(city), "$options": "i"}},
            ]
            if city_ids:
                mp_part["$or"].append({"city": {"$in": _flex_ref_ids(city_ids)}})
        query["$or"] = [
            {"$and": [_seed_document_clause(), seed_part]},
            mp_part,
        ]
    elif mode == "marketplace":
        query = {
            "status": "active",
            "visibility": "public",
        }
        if exclude_clauses:
            query = {"$and": [query, *exclude_clauses]}
        cat_ids = cache.category_ids_for_query(category)
        if cat_ids:
            query["equipmentCategory"] = {"$in": _flex_ref_ids(cat_ids)}
        if listing_type:
            query["listingType"] = listing_type
        city_ids = cache.city_ids_for_name(city)
        if city:
            query["$or"] = [
                {"equipmentLocation": {"$regex": re.escape(city), "$options": "i"}},
            ]
            if city_ids:
                query["$or"].append({"city": {"$in": _flex_ref_ids(city_ids)}})
    else:
        query = {
            "$and": [
                *exclude_clauses,
                {"category": machine.get("category")},
                {"city": machine.get("city")},
            ]
        }

    cursor = database.machines.find(query).limit(limit)
    results = []
    async for doc in cursor:
        results.append(normalize_machine(doc, cache))
    return results


async def nearby_cities_with_category_listings(
    database,
    *,
    category: str,
    city: str,
    limit: int = 3,
) -> list[str]:
    """Cities with listings for the same category (region map, then national)."""
    from app.ai.category_mapping import KNOWN_CITIES, REGION_MAP

    city = (city or "").strip().lower()
    category = (category or "").strip().lower()
    if not city or not category:
        return []

    candidates: list[str] = []
    for cities in REGION_MAP.values():
        if city in cities:
            candidates = [c for c in cities if c != city]
            break
    if not candidates:
        candidates = [c for c in KNOWN_CITIES if c != city]

    found: list[str] = []
    for candidate in candidates:
        batch = await search_by_filters(
            database,
            category=category,
            city=candidate,
            limit=1,
            exact_category=True,
        )
        if batch:
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


async def available_brands_for_category_city(
    database,
    *,
    category: str,
    city: str | None = None,
    limit: int = 20,
) -> list[str]:
    """Distinct brands with listings for category (optional city)."""
    category = (category or "").strip().lower()
    if not category:
        return []

    machines = await search_by_filters(
        database,
        category=category,
        city=city,
        limit=limit * 5,
        exact_category=True,
    )
    brands: set[str] = set()
    for machine in machines:
        name = str(machine.get("brand") or "").strip()
        if name:
            brands.add(name)
    return sorted(brands, key=str.lower)[:limit]


async def available_cities_for_category(
    database,
    *,
    category: str,
    limit: int = 5,
) -> list[str]:
    """Cities that have at least one listing for the category."""
    category = (category or "").strip().lower()
    if not category:
        return []

    machines = await search_by_filters(
        database,
        category=category,
        limit=limit * 30,
        exact_category=True,
    )
    counts: dict[str, int] = {}
    for machine in machines:
        c = str(machine.get("city") or "").strip().lower()
        if c:
            counts[c] = counts.get(c, 0) + 1
    return [
        c for c, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ][:limit]


def _machine_price_value(machine: dict) -> float:
    listing_type = (machine.get("listing_type") or "").lower()
    if listing_type in ("sell", "buy"):
        val = machine.get("selling_price") or machine.get("price_per_day")
    else:
        val = machine.get("price_per_day") or machine.get("rental_price")
    try:
        return float(val) if val is not None else float("inf")
    except (TypeError, ValueError):
        return float("inf")


async def min_price_for_category_city(
    database,
    *,
    category: str,
    city: str | None = None,
    listing_type: str | None = None,
    sample_limit: int = 50,
) -> float | None:
    """Lowest factual price for category/city from DB listings."""
    category = (category or "").strip().lower()
    if not category:
        return None

    machines = await search_by_filters(
        database,
        category=category,
        city=city,
        listing_type=listing_type,
        limit=sample_limit,
        exact_category=True,
        sort_by="price",
    )
    prices = [_machine_price_value(m) for m in machines]
    prices = [p for p in prices if p != float("inf")]
    return min(prices) if prices else None
