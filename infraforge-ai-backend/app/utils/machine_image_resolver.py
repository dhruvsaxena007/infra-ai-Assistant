"""
Resolve machine listing images to category-appropriate equipment photographs.

Replaces irrelevant uploads (screenshots, wrong stock photos, detail shots)
with curated URLs from data/verified_training_images.py so demo listings
always show the correct machine type.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from data.verified_training_images import get_images_for_category

# URLs or path fragments that are never suitable as hero listing photos.
_BAD_URL_FRAGMENTS = (
    "screenshot",
    "_serial.",
    "serial.jpg",
    "_engine.",
    "engine.jpg",
    "eicher-pro",
    "pexels-photo-276024",
    "pexels-photo-16105409",
    "pexels-photo-1090638",
    "pexels-photo-276724",
    "pexels-photo-256424",
    "unsplash.com/photo",
    "/book",
    "books",
    "mountain",
    "home-decor",
    "interior-design",
    "placeholder.com",
)

# Category keyword hints used to accept an existing marketplace photo.
_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "motor grader": ("motor_grader", "motorgrader", "motor-grader", "grader"),
    "excavator": ("excavator", "digger", "poclain"),
    "backhoe loader": ("backhoe", "jcb", "loader"),
    "wheel loader": ("wheel_loader", "loader", "backhoe"),
    "bulldozer": ("bulldozer", "dozer"),
    "crane": ("crane", "hydra"),
    "hydra crane": ("crane", "hydra"),
    "road roller": ("roller", "compactor"),
    "dump truck": ("truck", "tipper", "dumper", "signa", "prima"),
    "concrete mixer": ("mixer", "concrete"),
    "mobile crusher": ("crusher", "screen"),
    "forklift": ("forklift", "stacker", "walkie"),
    "walkie stacker": ("forklift", "stacker", "walkie"),
    "boom lift": ("boom", "lift", "aerial"),
    "scissor lift": ("scissor", "lift"),
}


def _normalize_category(category: str) -> str:
    return re.sub(r"\s+", " ", str(category or "").strip().lower())


def _is_bad_url(url: str) -> bool:
    lower = url.lower()
    return any(fragment in lower for fragment in _BAD_URL_FRAGMENTS)


def _matches_category(url: str, category: str) -> bool:
    hints = _CATEGORY_HINTS.get(_normalize_category(category))
    if not hints:
        return False
    lower = url.lower()
    return any(h in lower for h in hints)


def _pick_from_pool(category: str, machine_id: str) -> list[str]:
    pool = get_images_for_category(_normalize_category(category))
    if not pool:
        pool = get_images_for_category("support")
    if not pool:
        return []

    digest = hashlib.md5(f"{machine_id}:{category}".encode()).hexdigest()
    start = int(digest[:8], 16) % len(pool)
    ordered = pool[start:] + pool[:start]
    return list(ordered[:4])


def _is_wikimedia_equipment(url: str) -> bool:
    """Accept Wikimedia Commons construction-equipment photographs."""
    lower = url.lower()
    if "upload.wikimedia.org" not in lower:
        return False
    equipment_terms = (
        "excavator", "loader", "backhoe", "bulldozer", "dozer", "grader",
        "roller", "compactor", "paver", "crane", "forklift", "lift", "truck",
        "mixer", "drill", "crusher", "compressor", "harvester", "skidder",
        "telehandler", "trencher", "paver", "boom", "scissor", "haul",
    )
    return any(term in lower for term in equipment_terms)


def is_plausible_equipment_image(url: str, category: str = "") -> bool:
    """True when a URL looks like a real equipment hero photo for the category."""
    u = str(url or "").strip()
    if not u.startswith("http"):
        return False
    if _is_bad_url(u):
        return False
    cat = _normalize_category(category)
    if cat and _matches_category(u, cat):
        return True
    if _is_wikimedia_equipment(u):
        return True
    # Accept any curated training-pool URL (known-good equipment stock).
    if cat:
        pool = get_images_for_category(cat)
        if u in pool:
            return True
    return False


def resolve_machine_images(
    category: str,
    existing_images: Optional[list[str]],
    machine_id: str = "",
    image_url: str = "",
) -> tuple[list[str], str]:
    """
    Return (images[], primary image_url) using category-appropriate photographs.

    Keeps valid existing URLs; replaces missing or implausible ones from the
    verified category pool (stable per machine_id).
    """
    incoming: list[str] = []
    for src in [image_url, *(existing_images or [])]:
        u = str(src or "").strip()
        if u and u not in incoming:
            incoming.append(u)

    cat = _normalize_category(category)
    kept = [u for u in incoming if is_plausible_equipment_image(u, cat)]
    fallback = _pick_from_pool(cat or "support", machine_id or "default")

    if kept:
        primary = kept[0]
        extras = [u for u in fallback if u not in kept]
        images = (kept + extras)[:4]
        return images, primary

    if fallback:
        return fallback, fallback[0]

    return incoming[:4], (incoming[0] if incoming else "")
