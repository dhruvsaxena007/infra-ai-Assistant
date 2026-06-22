"""
Verified category-appropriate image URLs for machine seeds and image resolution.

Sources images from data/equipment_training_catalog.py (Wikimedia Commons +
InfraForge S3 listing photos). Each canonical category gets 4 equipment photos
that match the machine type (roller, excavator, crane, etc.) — never generic
stock scenes unrelated to construction machinery.
"""

from __future__ import annotations

from data.equipment_training_catalog import EQUIPMENT_CATALOG

# Canonical aliases for categories used in seeds but named slightly differently.
_CATEGORY_ALIASES: dict[str, str] = {
    "concrete mixer": "concrete mixer truck",
}

# Build canonical -> images lookup from the training catalog.
_CATALOG_IMAGES: dict[str, list[str]] = {
    entry["canonical"]: list(entry["images"][:4])
    for entry in EQUIPMENT_CATALOG
    if entry.get("images")
}

# InfraForge S3 photos used as extras where catalog has fewer than 4 URLs.
_S3_EXTRAS: dict[str, list[str]] = {
    "motor grader": [
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779780612094_motor_grader_front.jpg",
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779860870640_motor_grader_side.jpg",
    ],
    "backhoe loader": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1776857303/productImages_1776857300241_backhoe_loader.png",
    ],
    "dump truck": [
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779942377195_press-13aug20-lowres.jpg",
    ],
    "air compressor": [
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779943190787_air-compressor-support-truck-1702019936-7199582.webp",
    ],
}


def _resolve_canonical(canonical: str) -> str:
    key = canonical.strip().lower()
    return _CATEGORY_ALIASES.get(key, key)


def get_images_for_category(canonical: str) -> list[str]:
    """Return up to 4 stable HTTPS image URLs for a canonical equipment category."""
    key = _resolve_canonical(canonical)
    images: list[str] = list(_CATALOG_IMAGES.get(key) or [])

    for extra in _S3_EXTRAS.get(key, []):
        if extra not in images:
            images.append(extra)

    if not images:
        # Last resort: use excavator pool so we never return empty or random URLs.
        images = list(_CATALOG_IMAGES.get("excavator") or [])

    return images[:4]


def get_image_for_variant(canonical: str, variant_idx: int) -> str:
    """Primary image for a brand/model variant (rotates through category pool)."""
    pool = get_images_for_category(canonical)
    if not pool:
        return ""
    return pool[(variant_idx - 1) % len(pool)]
