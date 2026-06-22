"""
Structured machine image resolution — single source for API, migration, and seeds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from app.utils.machine_image_resolver import (
    is_plausible_equipment_image,
    resolve_machine_images,
    _normalize_category,
    _pick_from_pool,
)
from data.verified_training_images import get_images_for_category


@dataclass
class ImageResolution:
    image_url: str
    images: list[str]
    image_source: str
    image_match_level: str
    image_alt: str
    is_representative_image: bool
    image_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _alt_text(category: str, brand: str = "", model: str = "") -> str:
    cat = _normalize_category(category) or "heavy equipment"
    label = cat.title()
    if brand and model:
        return f"{brand} {model} — {label}"
    if brand:
        return f"{brand} {label}"
    return f"{label} construction equipment"


def classify_listing_image(
    url: str,
    *,
    category: str,
    brand: str = "",
    model: str = "",
) -> str:
    """Classify a raw stored image URL."""
    u = str(url or "").strip()
    if not u:
        return "missing"
    if not u.startswith("http"):
        return "unsupported_format"
    if not is_plausible_equipment_image(u, category):
        pool = get_images_for_category(_normalize_category(category))
        if u in pool:
            return "category_representative"
        return "unrelated" if u else "broken"
    hints = (brand or "").lower(), (model or "").lower()
    lower = u.lower()
    if any(h and h in lower for h in hints if h):
        return "brand_model"
    pool = get_images_for_category(_normalize_category(category))
    if u in pool:
        return "category_representative"
    return "exact_listing"


def resolve_machine_image_metadata(
    *,
    category: str,
    existing_images: Optional[list[str]] = None,
    machine_id: str = "",
    image_url: str = "",
    brand: str = "",
    model: str = "",
    user_uploaded: bool = False,
) -> ImageResolution:
    """
    Hierarchy:
    verified listing-specific → brand/model → category pool → industry fallback
    """
    incoming: list[str] = []
    for src in [image_url, *(existing_images or [])]:
        u = str(src or "").strip()
        if u and u not in incoming:
            incoming.append(u)

    cat = _normalize_category(category)
    kept = [u for u in incoming if is_plausible_equipment_image(u, cat)]
    fallback = _pick_from_pool(cat or "support", machine_id or "default")

    if kept and user_uploaded:
        primary = kept[0]
        level = "exact_listing"
        source = "listing"
        representative = False
        verified = True
        images = (kept + [u for u in fallback if u not in kept])[:4]
    elif kept:
        primary = kept[0]
        cls = classify_listing_image(primary, category=cat, brand=brand, model=model)
        if cls == "brand_model":
            level, source, representative = "brand_model", "brand_model", False
        elif cls == "category_representative":
            level, source, representative = "category_representative", "category", True
        else:
            level, source, representative = "exact_listing", "listing", False
        verified = True
        images = (kept + [u for u in fallback if u not in kept])[:4]
    elif fallback:
        primary = fallback[0]
        level = "category_representative"
        source = "category"
        representative = True
        verified = True
        images = fallback
    else:
        primary = incoming[0] if incoming else ""
        level = "generic_industry"
        source = "fallback"
        representative = True
        verified = False
        images = incoming[:4]

    return ImageResolution(
        image_url=primary,
        images=images,
        image_source=source,
        image_match_level=level,
        image_alt=_alt_text(cat, brand, model),
        is_representative_image=representative,
        image_verified=verified and bool(primary),
    )


def apply_image_metadata_to_machine(machine: dict) -> dict:
    """Attach resolved image fields to a machine dict (non-breaking extras)."""
    meta = resolve_machine_image_metadata(
        category=str(machine.get("category") or ""),
        existing_images=machine.get("images") if isinstance(machine.get("images"), list) else [],
        machine_id=str(machine.get("id") or machine.get("_id") or ""),
        image_url=str(machine.get("image_url") or ""),
        brand=str(machine.get("brand") or ""),
        model=str(machine.get("model") or ""),
        user_uploaded=bool(machine.get("user_uploaded_image")),
    )
    out = dict(machine)
    out["images"] = meta.images
    out["image_url"] = meta.image_url or None
    out["image_alt"] = meta.image_alt
    out["image_source"] = meta.image_source
    out["image_match_level"] = meta.image_match_level
    out["is_representative_image"] = meta.is_representative_image
    out["image_verified"] = meta.image_verified
    return out
