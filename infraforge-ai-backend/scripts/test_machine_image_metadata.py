"""Tests for machine image metadata resolver."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_missing_gets_category_pool():
    from app.utils.machine_image_metadata import resolve_machine_image_metadata

    meta = resolve_machine_image_metadata(category="excavator", machine_id="test-1")
    _assert(bool(meta.image_url), "should resolve url")
    _assert(meta.image_match_level in ("category_representative", "exact_listing"), meta.image_match_level)
    _assert(bool(meta.image_alt), "alt text")
    print("PASS missing_gets_category_pool")


def test_keeps_plausible_listing():
    from app.utils.machine_image_metadata import resolve_machine_image_metadata
    from data.verified_training_images import get_images_for_category

    pool = get_images_for_category("excavator")
    if not pool:
        print("SKIP keeps_plausible_listing — no pool")
        return
    url = pool[0]
    meta = resolve_machine_image_metadata(
        category="excavator",
        image_url=url,
        machine_id="test-2",
    )
    _assert(meta.image_url == url, "should keep valid url")
    print("PASS keeps_plausible_listing")


def test_classify_unrelated():
    from app.utils.machine_image_metadata import classify_listing_image

    cls = classify_listing_image(
        "https://images.pexels.com/photos/276024/pexels-photo-276024.jpeg",
        category="excavator",
    )
    _assert(cls in ("unrelated", "broken"), cls)
    print("PASS classify_unrelated")


def main():
    test_missing_gets_category_pool()
    test_keeps_plausible_listing()
    test_classify_unrelated()
    print("\nALL IMAGE METADATA TESTS PASSED")


if __name__ == "__main__":
    main()
