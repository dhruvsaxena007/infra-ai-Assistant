"""
Seed MongoDB with training machines for YOLO image classification.

Adds 3–4 machines per equipment type with Wikimedia image URLs.
Safe to re-run: upserts by _id (prefix seed_).

Usage:
    python scripts/seed_training_machines.py
    python scripts/seed_training_machines.py --dry-run
    python scripts/seed_training_machines.py --validate-images
    python scripts/seed_training_machines.py --purge   # remove prior seed_* docs only

Then export + train:
    python scripts/export_yolo_dataset.py
    python scripts/train_yolo_classifier.py --epochs 80
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime, timezone

PROJECT_ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.equipment_training_catalog import CITIES, EQUIPMENT_CATALOG
from data.verified_training_images import get_images_for_category
from app.database.persistent_store import _sync_db
from app.core.config import settings
from app.database.mongodb import database

SEED_PREFIX = "seed_"
BASE_PRICES = (8500, 12000, 18000, 24000, 32000, 45000)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


def _machine_id(canonical: str, idx: int) -> str:
    return f"{SEED_PREFIX}{_slug(canonical)}_{idx:02d}"


def _pick_images(pool: list[str], variant_idx: int) -> list[str]:
    """Two distinct images per machine from the 4-image pool."""
    if not pool:
        return []
    a = pool[variant_idx % len(pool)]
    b = pool[(variant_idx + 1) % len(pool)]
    if a == b and len(pool) > 1:
        b = pool[(variant_idx + 2) % len(pool)]
    return [u for u in (a, b) if u]


def _real_listing_images(canonical: str, limit: int = 4) -> list[str]:
    """Prefer real InfraForge listing photos over stock images."""
    urls: list[str] = []
    seen: set[str] = set()
    col = _sync_db()["machines"]
    query = {
        "category": canonical,
        "source": {"$nin": ["training_seed"]},
    }
    for doc in col.find(query).limit(20):
        for key in ("productImages", "images", "image_url"):
            val = doc.get(key)
            if isinstance(val, list):
                for u in val:
                    u = str(u).strip()
                    if u.startswith("http") and u not in seen:
                        seen.add(u)
                        urls.append(u)
            elif val:
                u = str(val).strip()
                if u.startswith("http") and u not in seen:
                    seen.add(u)
                    urls.append(u)
            if len(urls) >= limit:
                return urls[:limit]
    return urls[:limit]


def build_documents() -> list[dict]:
    docs: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for entry in EQUIPMENT_CATALOG:
        canonical = entry["canonical"]
        display = entry["display"]
        group = entry["group"]
        # Prefer catalog Wikimedia images; fall back to verified pool resolver.
        images = list(entry.get("images") or [])[:4] or get_images_for_category(canonical)[:4]
        variants = entry["variants"]

        for idx, (brand, model, city_off) in enumerate(variants, start=1):
            city = CITIES[(city_off + idx) % len(CITIES)]
            machine_id = _machine_id(canonical, idx)
            imgs = _pick_images(images, idx)
            price = BASE_PRICES[(idx + city_off) % len(BASE_PRICES)]

            docs.append({
                "_id": machine_id,
                "name": f"{brand} {model}",
                "brand": brand,
                "model": model,
                "category": canonical,
                "category_display": display,
                "equipment_group": group,
                "city": city,
                "price_per_day": price,
                "listing_type": "rent",
                "rent_type": "daily",
                "availability": True,
                "availability_status": "available",
                "status": "active",
                "visibility": "public",
                "rating": 4.0 + (idx % 2) * 0.5,
                "description": (
                    f"{brand} {model} {display.replace('_', ' ').title()} available for rent in {city}. "
                    f"Ideal for {group.lower()}. Training seed listing for image classification."
                ),
                "image_url": imgs[0] if imgs else "",
                "images": imgs,
                "productImages": imgs,
                "productThumbnails": imgs[:1],
                "specifications": {
                    "condition": "used" if idx % 2 else "new",
                    "manufacturing_year": 2016 + idx,
                    "fuel_type": "diesel",
                    "pincode": "302001",
                },
                "source": "training_seed",
                "seed_version": "1.0",
                "seeded_at": now,
            })

    return docs


def validate_image_urls(docs: list[dict], timeout: int = 20) -> dict:
    """GET-check unique image URLs (with User-Agent)."""
    import requests

    headers = {"User-Agent": "InfraForge-Seed/1.0 (training dataset)"}
    urls = set()
    for doc in docs:
        for u in doc.get("productImages") or []:
            urls.add(u)

    ok, bad = 0, []
    for url in sorted(urls):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
            if resp.status_code == 200 and int(resp.headers.get("content-length", 1)) != 0:
                ok += 1
            else:
                bad.append((url, resp.status_code))
            resp.close()
        except Exception as exc:
            bad.append((url, str(exc)))

    return {"total": len(urls), "ok": ok, "bad": bad}


async def purge_seed() -> int:
    result = await database.machines.delete_many({"_id": {"$regex": f"^{SEED_PREFIX}"}})
    alt = await database.machines.delete_many({"source": "training_seed"})
    return result.deleted_count + alt.deleted_count


async def upsert_seed(docs: list[dict], dry_run: bool) -> dict:
    inserted = updated = 0
    for doc in docs:
        if dry_run:
            continue
        existing = await database.machines.find_one({"_id": doc["_id"]})
        await database.machines.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        if existing:
            updated += 1
        else:
            inserted += 1

    total = await database.machines.count_documents({})
    seed_count = await database.machines.count_documents({"source": "training_seed"})
    by_cat = {}
    async for row in database.machines.aggregate([
        {"$match": {"source": "training_seed"}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]):
        by_cat[row["_id"]] = row["count"]

    return {
        "built": len(docs),
        "inserted": inserted,
        "updated": updated,
        "total_machines": total,
        "seed_machines": seed_count,
        "categories": len(by_cat),
        "per_category": by_cat,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-images", action="store_true")
    parser.add_argument("--purge", action="store_true")
    args = parser.parse_args()

    if not settings.MONGODB_URL:
        raise SystemExit("MONGODB_URL is not set in .env")

    docs = build_documents()
    print(f"Built {len(docs)} seed machines across {len(EQUIPMENT_CATALOG)} equipment types")

    if args.validate_images:
        report = validate_image_urls(docs)
        print(f"Image URLs: {report['ok']}/{report['total']} OK")
        for url, err in report["bad"][:20]:
            print(f"  BAD [{err}] {url[:90]}")
        if len(report["bad"]) > 20:
            print(f"  ... and {len(report['bad']) - 20} more")

    if args.purge and not args.dry_run:
        n = await purge_seed()
        print(f"Purged {n} prior seed documents")

    stats = await upsert_seed(docs, dry_run=args.dry_run)
    print("Seed stats:", stats)

    if args.dry_run:
        print("Dry run — no MongoDB writes")
    else:
        print("\nNext steps:")
        print("  python scripts/export_yolo_dataset.py")
        print("  python scripts/train_yolo_classifier.py --epochs 80")
        print("  uvicorn app.main:app --reload --host 127.0.0.1 --port 8001")


if __name__ == "__main__":
    asyncio.run(main())
