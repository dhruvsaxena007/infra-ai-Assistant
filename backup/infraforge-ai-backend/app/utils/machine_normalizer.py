"""
Public normalization API for InfraForge marketplace machine listings.

All API responses and AI services should use machines passed through
normalize_machine() / normalize_machines() so the output shape is stable
regardless of raw MongoDB schema (seed sample vs real marketplace).
"""

from __future__ import annotations

from typing import Any, Optional

from app.utils.machine_mapper import (
    embedding_text_from_normalized as _legacy_embedding_text,
    is_marketplace_document,
    normalize_machine as _normalize_raw,
    normalize_machines as _normalize_raw_list,
)
from app.utils.machine_image_resolver import resolve_machine_images

if False:  # TYPE_CHECKING only — avoid circular import at runtime
    from app.utils.reference_cache import ReferenceCache


def _coerce_id(value) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_images(image_url: Any, images: Any) -> tuple[list, str]:
    out: list[str] = []

    if isinstance(images, list):
        out = [str(u).strip() for u in images if u]
    elif isinstance(images, str) and images.strip():
        out = [images.strip()]

    url = str(image_url or "").strip()
    if url and url not in out:
        out.insert(0, url)
    if not url and out:
        url = out[0]

    return out, url


def _coerce_specifications(specs: Any) -> dict:
    if isinstance(specs, dict):
        return {k: v for k, v in specs.items() if v is not None and v != ""}
    return {}


def _resolve_availability(raw: dict) -> tuple[bool, str]:
    if "availability" in raw and raw.get("availability_status"):
        status = str(raw.get("availability_status") or "").lower()
        available = bool(raw.get("availability"))
        if status:
            return available, status

    status = str(raw.get("availability_status") or raw.get("status") or "").lower()
    if status in ("active", "available"):
        return True, "available"
    if status in ("rented", "booked"):
        return False, "rented"
    if status in ("pending", "draft", "inactive", "maintenance"):
        return False, status or "unavailable"
    if status:
        return status == "available", status
    return True, "available"


def _resolve_price_fields(raw: dict) -> tuple[Any, Any, Any]:
    listing_type = str(raw.get("listing_type") or raw.get("listingType") or "rent").lower()
    price = raw.get("price_per_day")
    if price is None and listing_type == "sell":
        price = raw.get("selling_price") or raw.get("sellingPrice")
    if price is None and listing_type == "rent":
        price = raw.get("rentalPrice")
    selling = raw.get("selling_price") or raw.get("sellingPrice")
    return price, selling, listing_type


def finalize_normalized_machine(raw: dict) -> dict:
    """
    Ensure any machine dict (already normalized or partially mapped) matches
    the canonical API shape. Safe to call multiple times.
    """
    if not raw:
        return {}

    machine_id = _coerce_id(raw.get("id") or raw.get("_id"))
    images, image_url = _coerce_images(raw.get("image_url"), raw.get("images"))
    category_for_images = str(raw.get("category") or "").strip().lower()
    images, image_url = resolve_machine_images(
        category_for_images,
        images,
        machine_id=machine_id,
        image_url=image_url,
    )
    available, availability_status = _resolve_availability(raw)
    price, selling_price, listing_type = _resolve_price_fields(raw)

    category = str(raw.get("category") or "").strip().lower()
    category_display = str(
        raw.get("category_display") or raw.get("category") or ""
    ).strip()

    rating = raw.get("rating")
    if rating is not None:
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            rating = None

    seller = raw.get("seller_name") or raw.get("owner_name") or ""
    owner = raw.get("owner_name") or seller

    normalized = {
        "id": machine_id,
        "_id": machine_id,
        "name": str(raw.get("name") or "Equipment Listing"),
        "category": category,
        "category_display": category_display or category,
        "city": str(raw.get("city") or ""),
        "price_per_day": price,
        "rating": rating,
        "images": images,
        "image_url": image_url or None,
        "description": str(raw.get("description") or ""),
        "seller_name": str(seller) if seller else None,
        "owner_name": str(owner) if owner else None,
        "availability": available,
        "availability_status": availability_status,
        "specifications": _coerce_specifications(raw.get("specifications")),
        "brand": str(raw.get("brand") or "") or None,
        "model": str(raw.get("model") or "") or None,
        "listing_type": listing_type or None,
        "rent_type": raw.get("rent_type") or raw.get("rentType"),
        "security_deposit": raw.get("security_deposit") or raw.get("securityDeposit"),
        "selling_price": selling_price,
        "slug": raw.get("slug"),
        "source": raw.get("source") or (
            "infraforge_real_db" if is_marketplace_document(raw) else "seed_sample"
        ),
    }

    if raw.get("embedding") is not None:
        normalized["embedding"] = raw["embedding"]
    for key in ("similarity_score", "final_score", "recommendation_score"):
        if key in raw:
            normalized[key] = raw[key]

    return normalized


def normalize_machine(raw: dict, cache=None) -> dict:
    """Normalize a raw or partial machine document to the standard API shape."""
    if not raw:
        return {}
    if is_marketplace_document(raw) or (
        not raw.get("source") and raw.get("equipmentCategory")
    ):
        result = _normalize_raw(raw, cache)
    elif raw.get("source") in ("infraforge_real_db", "seed_sample") and raw.get("name"):
        result = dict(raw)
    else:
        result = _normalize_raw(raw, cache)
    return finalize_normalized_machine(result)


def normalize_machines(raw_list: list, cache=None) -> list:
    return [normalize_machine(doc, cache) for doc in (raw_list or []) if doc]


def build_machine_search_text(machine: dict) -> str:
    """
    Rich searchable text for embeddings and semantic ranking.
    Works when description is empty (common in real marketplace data).
    """
    specs = _coerce_specifications(machine.get("specifications"))
    parts = [
        machine.get("name"),
        machine.get("brand"),
        machine.get("model"),
        machine.get("category"),
        machine.get("category_display"),
        machine.get("city"),
        machine.get("listing_type"),
        machine.get("rent_type"),
        machine.get("availability_status"),
        machine.get("description"),
        machine.get("seller_name"),
    ]

    for key in ("variant", "manufacturing_year", "condition", "pincode", "capacity"):
        value = specs.get(key)
        if value is not None and value != "":
            parts.append(str(value))

    text = " ".join(str(p).strip() for p in parts if p)
    if text.strip():
        return text
    return _legacy_embedding_text(machine)


def effective_price(machine: dict):
    """Return comparable price for rent or sell listings."""
    listing_type = str(machine.get("listing_type") or "rent").lower()
    if listing_type == "sell":
        return machine.get("selling_price") or machine.get("price_per_day")
    return machine.get("price_per_day")


def rating_score_neutral(machine: dict) -> float:
    """Return 0.0–1.0 rating score; neutral 0.5 when rating is null."""
    rating = machine.get("rating")
    if rating is None:
        return 0.5
    try:
        return min(1.0, max(0.0, float(rating) / 5.0))
    except (TypeError, ValueError):
        return 0.5


def format_price_label(machine: dict) -> str:
    """Human-readable price with rent/sell context."""
    listing_type = str(machine.get("listing_type") or "rent").lower()
    rent_type = machine.get("rent_type")

    if listing_type == "sell":
        price = machine.get("selling_price") or machine.get("price_per_day")
        if price is None:
            return "price not available"
        return f"₹{price:,} (sell)"

    price = machine.get("price_per_day")
    if price is None:
        return "price not available"
    suffix = f"/{rent_type}" if rent_type else "/day"
    return f"₹{price:,}{suffix}"
