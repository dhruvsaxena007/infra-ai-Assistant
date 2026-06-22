"""
Cached lookups for marketplace ObjectId references.

Loads equipmentcategories, cities, and review aggregates once per process
and reuses them for every machine normalization / filter build.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Optional

from bson import ObjectId

from app.ai.category_mapping import marketplace_category_to_canonical

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class ReferenceCache:
    """In-memory resolver for marketplace foreign keys."""

    def __init__(self) -> None:
        self.loaded = False
        self.category_id_to_name: dict[str, str] = {}
        self.category_id_to_canonical: dict[str, str] = {}
        self.canonical_to_category_ids: dict[str, list] = defaultdict(list)
        self.category_id_to_brand_names: dict[str, list[str]] = defaultdict(list)
        self.brand_id_to_name: dict[str, str] = {}
        self.model_id_to_name: dict[str, str] = {}
        self.city_id_to_name: dict[str, str] = {}
        self.city_name_to_ids: dict[str, list] = defaultdict(list)
        self.user_id_to_name: dict[str, str] = {}
        self.rating_by_product_id: dict[str, float] = {}

    async def load(self, database: AsyncIOMotorDatabase) -> None:
        if self.loaded:
            return

        async for doc in database.equipmentcategories.find({}):
            cat_id = str(doc["_id"])
            cat_name = str(doc.get("category") or "").strip()
            canonical = marketplace_category_to_canonical(cat_name)

            self.category_id_to_name[cat_id] = cat_name
            self.category_id_to_canonical[cat_id] = canonical
            self.canonical_to_category_ids[canonical].append(ObjectId(cat_id))

            for brand in doc.get("brands") or []:
                brand_id = str(brand.get("_id", ""))
                brand_name = str(brand.get("name") or "").strip()
                if brand_id:
                    self.brand_id_to_name[brand_id] = brand_name
                if brand_name:
                    self.category_id_to_brand_names[cat_id].append(brand_name)

                for model in brand.get("models") or []:
                    model_id = str(model.get("_id", ""))
                    if model_id:
                        self.model_id_to_name[model_id] = str(
                            model.get("name") or ""
                        ).strip()

        async for doc in database.cities.find({}):
            city_id = str(doc["_id"])
            city_name = str(doc.get("name") or "").strip()
            self.city_id_to_name[city_id] = city_name
            if city_name:
                self.city_name_to_ids[city_name.lower()].append(ObjectId(city_id))

        async for doc in database.users.find({}, {"name": 1}):
            self.user_id_to_name[str(doc["_id"])] = str(doc.get("name") or "").strip()

        rating_sums: dict[str, float] = defaultdict(float)
        rating_counts: dict[str, int] = defaultdict(int)

        async for doc in database.reviews.find({}, {"product": 1, "rating": 1}):
            product_id = str(doc.get("product", ""))
            rating = doc.get("rating")
            if product_id and rating is not None:
                rating_sums[product_id] += float(rating)
                rating_counts[product_id] += 1

        for product_id, total in rating_sums.items():
            count = rating_counts[product_id]
            if count:
                self.rating_by_product_id[product_id] = round(total / count, 2)

        self.loaded = True

        try:
            from app.ai.brand_catalog import register_brand_names
            register_brand_names(list(self.brand_id_to_name.values()))
        except Exception:
            pass

    def resolve_category_name(self, ref) -> str:
        if ref is None:
            return ""
        return self.category_id_to_name.get(str(ref), "")

    def resolve_category_canonical(self, ref) -> str:
        if ref is None:
            return ""
        ref_str = str(ref)
        if ref_str in self.category_id_to_canonical:
            return self.category_id_to_canonical[ref_str]
        name = self.resolve_category_name(ref)
        return marketplace_category_to_canonical(name)

    def resolve_brand_name(self, ref) -> str:
        if ref is None:
            return ""
        return self.brand_id_to_name.get(str(ref), "")

    def resolve_model_name(self, ref) -> str:
        if ref is None:
            return ""
        return self.model_id_to_name.get(str(ref), "")

    def resolve_city_name(self, ref, equipment_location: str = "") -> str:
        location = str(equipment_location or "").strip()
        if location:
            return location
        if ref is None:
            return ""
        return self.city_id_to_name.get(str(ref), "")

    def resolve_seller_name(self, raw: dict) -> str:
        seller = str(raw.get("sellerName") or raw.get("companyName") or "").strip()
        if seller:
            return seller
        owner = raw.get("owner")
        if owner:
            return self.user_id_to_name.get(str(owner), "")
        return ""

    def resolve_rating(self, machine_id: str) -> Optional[float]:
        return self.rating_by_product_id.get(machine_id)

    def category_ids_for_canonical(self, canonical: str) -> list:
        if not canonical:
            return []
        return list(self.canonical_to_category_ids.get(canonical.lower(), []))

    def category_ids_for_query(self, category: str) -> list:
        """
        Resolve equipmentCategory ObjectIds for a search category string.

        Matches exact canonical keys first, then partial matches on marketplace
        category labels (e.g. "drill" -> CRAWLER DRILL).
        """
        if not category:
            return []

        key = category.lower().strip()
        exact = self.category_ids_for_canonical(key)
        if exact:
            return exact

        matched = []
        for cat_id, name in self.category_id_to_name.items():
            canonical = self.category_id_to_canonical.get(cat_id, "").lower()
            name_lower = name.lower()
            if key in name_lower or key in canonical or canonical in key:
                matched.append(ObjectId(cat_id))
        return matched

    def city_ids_for_name(self, city: str) -> list:
        if not city:
            return []
        return list(self.city_name_to_ids.get(city.lower(), []))

    def brands_for_category(self, category: str) -> list[str]:
        """Distinct brand names from equipment category metadata for a search category."""
        if not category:
            return []
        cat_ids = self.category_ids_for_query(category)
        brands: set[str] = set()
        for cat_id in cat_ids:
            for name in self.category_id_to_brand_names.get(str(cat_id), []):
                if name:
                    brands.add(name)
        return sorted(brands, key=str.lower)


_cache: Optional[ReferenceCache] = None


async def get_reference_cache(database: AsyncIOMotorDatabase) -> ReferenceCache:
    global _cache
    if _cache is None:
        _cache = ReferenceCache()
    if not _cache.loaded:
        await _cache.load(database)
    return _cache


def reset_reference_cache() -> None:
    """Clear cache (useful in tests after DB reload)."""
    global _cache
    _cache = None
