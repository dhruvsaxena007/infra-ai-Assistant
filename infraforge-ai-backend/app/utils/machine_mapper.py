"""
Central machine normalization — single source of truth for API + AI output shape.

All services must receive machines through normalize_machine() or
normalize_machines() so missing/null nested fields never crash callers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.utils.reference_cache import ReferenceCache

# Fields copied into specifications when present on marketplace documents.
_SPEC_FIELD_MAP = {
    "manufacturing_year": "manufacturingYear",
    "condition": "equipmentCondition",
    "fuel_type": "fuelType",
    "transmission": "transmissionType",
    "bucket_capacity": "bucketCapacity",
    "engine_power": "enginePower",
    "operating_weight": "operatingWeight",
    "lifting_capacity": "liftingCapacity",
    "max_digging_depth": "maxDiggingDepth",
    "working_hours": "workingHours",
    "drive_type": "driveType",
    "capacity": "capacity",
    "pincode": "pincode",
}


def is_marketplace_document(raw: dict) -> bool:
    """True when the document follows the real InfraForge marketplace schema."""
    if not raw:
        return False
    return bool(
        raw.get("equipmentCategory") is not None
        or raw.get("rentalPrice") is not None
        or raw.get("listingType") is not None
    )


def is_seed_document(raw: dict) -> bool:
    """True when the document follows the sample/seed schema."""
    if not raw:
        return False
    return not is_marketplace_document(raw)


def _build_display_name(brand: str, model: str, variant: str, fallback: str = "") -> str:
    parts = [p for p in (brand, model, variant) if p]
    if parts:
        return " ".join(parts).strip()
    return fallback or "Equipment Listing"


def _extract_specifications(raw: dict) -> dict:
    specs: dict[str, Any] = {}
    variant = raw.get("variant")
    if variant:
        specs["variant"] = variant

    for out_key, src_key in _SPEC_FIELD_MAP.items():
        value = raw.get(src_key)
        if value is not None and value != "":
            specs[out_key] = value

    return specs


def _availability_from_status(status: str) -> tuple[bool, str]:
    normalized = str(status or "").lower()
    if normalized == "active":
        return True, "available"
    if normalized in ("rented", "booked"):
        return False, "rented"
    if normalized in ("maintenance", "inactive", "draft"):
        return False, normalized or "unavailable"
    return normalized == "available", normalized or "unknown"


def normalize_seed_machine(raw: dict) -> dict:
    """Normalize a sample/seed machine document (existing schema)."""
    machine_id = str(raw.get("_id", ""))
    status = raw.get("availability_status") or "available"
    available, availability_status = _availability_from_status(status)

    images = []
    if isinstance(raw.get("images"), list) and raw.get("images"):
        images = [str(u).strip() for u in raw["images"] if u]
    image_url = raw.get("image_url") or ""
    if image_url and image_url not in images:
        images.insert(0, image_url)
    elif not image_url and images:
        image_url = images[0]

    price = raw.get("price_per_day")
    name = str(raw.get("name") or "Unknown Machine")
    listing_type = str(raw.get("listing_type") or raw.get("listingType") or "rent").lower()
    if listing_type in ("buy", "purchase"):
        listing_type = "sell"
    selling_price = raw.get("selling_price") or raw.get("sellingPrice")

    normalized = {
        "id": machine_id,
        "_id": machine_id,
        "name": name,
        "category": str(raw.get("category") or "").lower(),
        "category_display": str(raw.get("category") or ""),
        "city": str(raw.get("city") or ""),
        "price_per_day": price,
        "rating": raw.get("rating"),
        "images": images,
        "image_url": image_url or (images[0] if images else ""),
        "description": str(raw.get("description") or ""),
        "seller_name": str(raw.get("owner_name") or ""),
        "owner_name": str(raw.get("owner_name") or ""),
        "availability": available,
        "availability_status": availability_status,
        "specifications": {},
        "brand": str(raw.get("brand") or ""),
        "model": str(raw.get("model") or ""),
        "listing_type": listing_type,
        "selling_price": selling_price,
        "source": raw.get("source") or "seed_sample",
        "mobile_number": None,
        "contact_number": None,
        "seller_phone": None,
        "whatsapp_number": None,
    }

    if raw.get("embedding") is not None:
        normalized["embedding"] = raw["embedding"]
    for score_key in ("similarity_score", "final_score", "recommendation_score"):
        if score_key in raw:
            normalized[score_key] = raw[score_key]

    return normalized


def normalize_marketplace_machine(raw: dict, cache: ReferenceCache) -> dict:
    """Normalize a real InfraForge marketplace machine document."""
    machine_id = str(raw.get("_id", ""))

    brand = cache.resolve_brand_name(raw.get("brand"))
    model = cache.resolve_model_name(raw.get("modelName"))
    variant = str(raw.get("variant") or "").strip()
    category_display = cache.resolve_category_name(raw.get("equipmentCategory"))
    category = cache.resolve_category_canonical(raw.get("equipmentCategory"))
    if not category and category_display:
        category = category_display.lower()

    city = cache.resolve_city_name(raw.get("city"), raw.get("equipmentLocation"))
    seller = cache.resolve_seller_name(raw)

    product_images = raw.get("productImages") or []
    thumbnails = raw.get("productThumbnails") or []
    images = [u for u in product_images if u]
    if not images:
        images = [u for u in thumbnails if u]
    image_url = images[0] if images else ""

    listing_type = str(raw.get("listingType") or "rent").lower()
    if listing_type == "sell":
        price = raw.get("sellingPrice")
    else:
        price = raw.get("rentalPrice")

    status = raw.get("status") or ""
    available, availability_status = _availability_from_status(status)
    rating = cache.resolve_rating(machine_id)

    name = _build_display_name(
        brand,
        model,
        variant,
        fallback=category_display or raw.get("slug") or machine_id,
    )

    normalized = {
        "id": machine_id,
        "_id": machine_id,
        "name": name,
        "category": category,
        "category_display": category_display,
        "city": city,
        "price_per_day": price,
        "rating": rating,
        "images": images,
        "image_url": image_url,
        "description": str(raw.get("description") or ""),
        "seller_name": seller,
        "owner_name": seller,
        "availability": available,
        "availability_status": availability_status,
        "specifications": _extract_specifications(raw),
        "brand": brand,
        "model": model,
        "listing_type": listing_type,
        "rent_type": raw.get("rentType"),
        "security_deposit": raw.get("securityDeposit"),
        "selling_price": raw.get("sellingPrice"),
        "slug": raw.get("slug"),
        "source": "infraforge_real_db",
        "mobile_number": str(raw.get("mobileNumber") or "").strip() or None,
        "contact_number": str(raw.get("mobileNumber") or "").strip() or None,
        "seller_phone": str(raw.get("mobileNumber") or "").strip() or None,
        "whatsapp_number": None,
    }

    if raw.get("embedding") is not None:
        normalized["embedding"] = raw["embedding"]
    for score_key in ("similarity_score", "final_score", "recommendation_score"):
        if score_key in raw:
            normalized[score_key] = raw[score_key]

    return normalized


def normalize_machine(
    raw: dict,
    cache: Optional[ReferenceCache] = None,
) -> dict:
    """
    Normalize any machine document (seed or marketplace) to the standard shape.
    """
    if not raw:
        return {}

    if raw.get("source") == "training_seed":
        return normalize_seed_machine(raw)

    if is_marketplace_document(raw):
        if cache is None:
            raise ValueError(
                "ReferenceCache is required to normalize marketplace documents"
            )
        return normalize_marketplace_machine(raw, cache)

    return normalize_seed_machine(raw)


def normalize_machines(
    raw_list: list,
    cache: Optional[ReferenceCache] = None,
) -> list:
    return [normalize_machine(doc, cache) for doc in (raw_list or []) if doc]


def embedding_text_from_normalized(machine: dict) -> str:
    """Build text used for semantic embedding generation."""
    specs = machine.get("specifications") or {}
    spec_text = " ".join(f"{k} {v}" for k, v in specs.items())
    return " ".join(
        filter(
            None,
            [
                machine.get("name"),
                machine.get("category_display") or machine.get("category"),
                machine.get("brand"),
                machine.get("model"),
                machine.get("description"),
                machine.get("city"),
                spec_text,
            ],
        )
    )
