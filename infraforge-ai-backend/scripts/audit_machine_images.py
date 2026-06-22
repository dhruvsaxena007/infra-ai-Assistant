#!/usr/bin/env python3
"""
Comprehensive machine image audit with classification and JSON report.

Usage (from infraforge-ai-backend):
    python scripts/audit_machine_images.py --audit
    python scripts/audit_machine_images.py --report
    python scripts/audit_machine_images.py --report --output data/reports/image_audit.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.mongodb import database
from app.utils.machine_image_metadata import classify_listing_image


def _is_demo(doc: dict) -> bool:
    if doc.get("is_demo") is True:
        return True
    if doc.get("source") in ("training_seed", "seed_sample"):
        return True
    sid = str(doc.get("_id", ""))
    return sid.startswith("seed_") or sid.startswith("demo_v2_")


def _is_genuine(doc: dict) -> bool:
    if _is_demo(doc):
        return False
    if doc.get("equipmentCategory") or doc.get("rentalPrice") or doc.get("listingType"):
        return True
    if doc.get("source") in ("infraforge_real_db", None) and not doc.get("seed_version"):
        return bool(doc.get("mobileNumber") or doc.get("slug"))
    return False


def _primary_image(doc: dict) -> str:
    url = str(doc.get("image_url") or "").strip()
    if url:
        return url
    images = doc.get("images") or doc.get("productImages") or []
    if isinstance(images, str):
        return images.strip()
    if images:
        return str(images[0] or "").strip()
    if doc.get("productThumbnails"):
        thumbs = doc.get("productThumbnails")
        if isinstance(thumbs, list) and thumbs:
            return str(thumbs[0] or "").strip()
    return ""


async def run_audit() -> dict:
    coll = database.machines
    classification = Counter()
    by_category = Counter()
    duplicates = Counter()
    records_requiring_repair: list[dict] = []

    total = genuine = demo = 0
    with_images = missing = broken = unrelated = unstable = 0

    async for doc in coll.find({}):
        total += 1
        if _is_genuine(doc):
            genuine += 1
        elif _is_demo(doc):
            demo += 1

        category = str(doc.get("category") or "").strip().lower()
        primary = _primary_image(doc)
        brand = str(doc.get("brand") or "")
        model = str(doc.get("model") or doc.get("modelName") or "")

        if not primary:
            classification["missing"] += 1
            missing += 1
            cls = "missing"
        else:
            with_images += 1
            cls = classify_listing_image(primary, category=category, brand=brand, model=model)
            classification[cls] += 1
            if cls in ("unrelated", "broken"):
                unrelated += 1 if cls == "unrelated" else 0
                broken += 1 if cls == "broken" else 0
            if "picsum" in primary.lower() or "random" in primary.lower():
                unstable += 1
                classification["unstable_remote_url"] += 1

        duplicates[primary] += 1 if primary else 0

        if cls in ("missing", "unrelated", "broken", "unsupported_format"):
            records_requiring_repair.append({
                "id": str(doc.get("_id")),
                "name": doc.get("name"),
                "category": category,
                "classification": cls,
                "image_url": primary,
                "is_demo": _is_demo(doc),
                "is_genuine": _is_genuine(doc),
            })
            by_category[category or "(none)"] += 1

    dup_urls = sum(1 for url, c in duplicates.items() if url and c > 1)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_listings": total,
        "genuine_listings": genuine,
        "demo_listings": demo,
        "listings_with_images": with_images,
        "missing_images": missing,
        "broken_urls": broken,
        "unrelated_images": unrelated,
        "duplicate_urls": dup_urls,
        "unstable_remote_urls": unstable,
        "classification": dict(classification),
        "exact_model_images": classification.get("exact_listing", 0) + classification.get("brand_model", 0),
        "category_representative_images": classification.get("category_representative", 0),
        "generic_fallback_images": classification.get("generic_industry", 0),
        "records_requiring_repair": len(records_requiring_repair),
        "repair_by_category": dict(by_category),
        "repair_samples": records_requiring_repair[:50],
    }


def print_report(report: dict) -> None:
    print("Machine Image Audit Report")
    print("=" * 72)
    for key in (
        "total_listings",
        "genuine_listings",
        "demo_listings",
        "listings_with_images",
        "missing_images",
        "broken_urls",
        "unrelated_images",
        "duplicate_urls",
        "unstable_remote_urls",
        "exact_model_images",
        "category_representative_images",
        "generic_fallback_images",
        "records_requiring_repair",
    ):
        print(f"  {key}: {report.get(key)}")
    print("\nClassification breakdown:")
    for k, v in sorted((report.get("classification") or {}).items()):
        print(f"  {k}: {v}")
    print("\nTop categories needing repair:")
    for cat, n in sorted((report.get("repair_by_category") or {}).items(), key=lambda x: -x[1])[:15]:
        print(f"  {cat}: {n}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit machine listing images")
    parser.add_argument("--audit", action="store_true", help="Run audit to stdout")
    parser.add_argument("--report", action="store_true", help="Generate detailed report")
    parser.add_argument("--output", type=str, default="", help="JSON output path")
    args = parser.parse_args()

    if not args.audit and not args.report:
        args.audit = True
        args.report = True

    report = await run_audit()
    if args.audit or args.report:
        print_report(report)

    if args.report:
        out = args.output or str(
            ROOT / "data" / "reports" / f"image_audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        )
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReport saved: {out}")


if __name__ == "__main__":
    asyncio.run(main())
