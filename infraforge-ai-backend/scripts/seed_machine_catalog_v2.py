#!/usr/bin/env python3
"""
Deterministic demo catalog seed v2 — ~300-400 additional high-quality listings.

Usage:
    python scripts/seed_machine_catalog_v2.py --plan
    python scripts/seed_machine_catalog_v2.py --dry-run
    python scripts/seed_machine_catalog_v2.py --apply
    python scripts/seed_machine_catalog_v2.py --validate
    python scripts/seed_machine_catalog_v2.py --rollback-seed-version
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from catalog_coverage import CITIES, format_coverage_report, plan_coverage

SEED_VERSION = "machine_catalog_v2"
DATASET_SOURCE = "infraforge_demo_seed"
DEMO_ID_PREFIX = "demo_v2_"
TARGET_ADDITIONS = 350
RNG_SEED = 42

from data.equipment_training_catalog import EQUIPMENT_CATALOG
from app.database.mongodb import database
from app.utils.machine_image_metadata import resolve_machine_image_metadata


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


def _demo_key(category: str, city: str, idx: int) -> str:
    return f"{_slug(category)}_{_slug(city)}_{idx:02d}"


def _demo_id(demo_key: str) -> str:
    return f"{DEMO_ID_PREFIX}{demo_key}"


def _variants_for_category(category: str) -> list[tuple[str, str]]:
    for entry in EQUIPMENT_CATALOG:
        if entry["canonical"] == category:
            return [(b, m) for b, m, _ in entry["variants"]]
    # Generic fallback variants
    return [
        ("JCB", "3DX"),
        ("Tata Hitachi", "ZAXIS 140"),
        ("CAT", "320D"),
        ("Komatsu", "PC210"),
    ]


def _price_for_band(rng: random.Random, band: str) -> int:
    if band == "low":
        return rng.choice([4500, 5500, 6500, 7500, 8500])
    if band == "high":
        return rng.choice([28000, 32000, 38000, 45000, 52000])
    return rng.choice([12000, 15000, 18000, 20000, 24000])


def build_document(
    *,
    category: str,
    city: str,
    idx: int,
    rng: random.Random,
) -> dict:
    demo_key = _demo_key(category, city, idx)
    brands = _variants_for_category(category)
    brand, model = brands[idx % len(brands)]
    band = ["low", "mid", "mid", "high"][idx % 4]
    price = _price_for_band(rng, band)
    year = 2018 + (idx % 7)
    conditions = ["excellent", "good", "good", "fair"]
    condition = conditions[idx % len(conditions)]
    avail = idx % 5 != 0

    meta = resolve_machine_image_metadata(
        category=category,
        machine_id=_demo_id(demo_key),
    )

    display = category.title()
    for entry in EQUIPMENT_CATALOG:
        if entry["canonical"] == category:
            display = entry["display"]
            break

    now = datetime.now(timezone.utc).isoformat()
    listing_type = "rent" if idx % 6 != 0 else "sell"
    selling_price = price * 180 if listing_type == "sell" else None

    return {
        "_id": _demo_id(demo_key),
        "demo_key": demo_key,
        "is_demo": True,
        "dataset_source": DATASET_SOURCE,
        "seed_version": SEED_VERSION,
        "name": f"{brand} {model}",
        "brand": brand,
        "model": model,
        "category": category,
        "category_display": display,
        "city": city,
        "price_per_day": price if listing_type == "rent" else price,
        "selling_price": selling_price,
        "listing_type": listing_type,
        "rent_type": "daily",
        "rating": round(3.8 + (idx % 12) * 0.1, 1),
        "description": (
            f"Demo {display.lower()} available in {city}. "
            f"Suitable for construction and infrastructure projects. "
            f"Condition: {condition}."
        ),
        "availability": avail,
        "availability_status": "available" if avail else "rented",
        "owner_name": f"Demo Owner {city[:3].upper()}{idx}",
        "image_url": meta.image_url,
        "images": meta.images,
        "image_match_level": meta.image_match_level,
        "image_source": meta.image_source,
        "specifications": {
            "condition": condition,
            "manufacturing_year": year,
            "fuel_type": "diesel",
            "pincode": "",
        },
        "source": "training_seed",
        "status": "active",
        "visibility": "public",
        "seeded_at": now,
        "updated_at": now,
    }


async def load_existing_demo_docs() -> list[dict]:
    docs: list[dict] = []
    async for doc in database.machines.find({
        "$or": [
            {"seed_version": SEED_VERSION},
            {"is_demo": True, "dataset_source": DATASET_SOURCE},
            {"_id": {"$regex": f"^{DEMO_ID_PREFIX}"}},
            {"source": "training_seed"},
        ]
    }):
        docs.append(doc)
    return docs


def build_all_documents(plan: list[dict], rng: random.Random) -> list[dict]:
    docs: list[dict] = []
    for row in plan:
        cat, city, count = row["category"], row["city"], row["count"]
        start_idx = row["existing"] + 1
        for i in range(count):
            idx = start_idx + i
            docs.append(build_document(category=cat, city=city, idx=idx, rng=rng))
    return docs


async def cmd_plan() -> None:
    existing = await load_existing_demo_docs()
    total = await database.machines.count_documents({})
    plan = plan_coverage(existing, target_additions=TARGET_ADDITIONS)
    planned = sum(r["count"] for r in plan)
    print(f"Total DB listings: {total}")
    print(f"Existing demo/training docs scanned: {len(existing)}")
    print(f"Planned additions: {planned}")
    print(format_coverage_report(plan))


async def cmd_dry_run() -> None:
    existing = await load_existing_demo_docs()
    plan = plan_coverage(existing, target_additions=TARGET_ADDITIONS)
    rng = random.Random(RNG_SEED)
    docs = build_all_documents(plan, rng)
    print(f"Would upsert {len(docs)} demo_v2 documents")
    for d in docs[:5]:
        print(f"  {d['_id']} | {d['category']} | {d['city']} | ₹{d['price_per_day']}")


async def cmd_apply() -> None:
    existing = await load_existing_demo_docs()
    plan = plan_coverage(existing, target_additions=TARGET_ADDITIONS)
    rng = random.Random(RNG_SEED)
    docs = build_all_documents(plan, rng)
    inserted = updated = skipped = 0
    for doc in docs:
        result = await database.machines.replace_one(
            {"_id": doc["_id"]},
            doc,
            upsert=True,
        )
        if result.upserted_id:
            inserted += 1
        elif result.modified_count:
            updated += 1
        else:
            skipped += 1
    total = await database.machines.count_documents({})
    print(f"Seed {SEED_VERSION}: inserted={inserted} updated={updated} skipped={skipped} total_db={total}")
    print(format_coverage_report(plan))


async def cmd_validate() -> None:
    count = await database.machines.count_documents({"seed_version": SEED_VERSION})
    missing_img = 0
    async for doc in database.machines.find({"seed_version": SEED_VERSION}):
        if not doc.get("image_url"):
            missing_img += 1
    print(f"demo_v2 count: {count}")
    print(f"missing images: {missing_img}")
    genuine_modified = await database.machines.count_documents({
        "seed_version": SEED_VERSION,
        "equipmentCategory": {"$exists": True},
    })
    print(f"genuine records with demo seed_version (should be 0): {genuine_modified}")


async def cmd_rollback() -> None:
    result = await database.machines.delete_many({
        "$or": [
            {"seed_version": SEED_VERSION},
            {"_id": {"$regex": f"^{DEMO_ID_PREFIX}"}},
        ]
    })
    print(f"Removed {result.deleted_count} demo_v2 records")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--rollback-seed-version", action="store_true")
    args = parser.parse_args()

    if args.plan:
        await cmd_plan()
    elif args.dry_run:
        await cmd_dry_run()
    elif args.apply:
        await cmd_apply()
    elif args.validate:
        await cmd_validate()
    elif args.rollback_seed_version:
        await cmd_rollback()
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
