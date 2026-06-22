#!/usr/bin/env python3
"""
Patch demo/seed machines: fix images + mix rent/buy listing types.

Usage:
    python scripts/patch_demo_catalog.py --dry-run
    python scripts/patch_demo_catalog.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.mongodb import database
from app.utils.machine_image_metadata import resolve_machine_image_metadata


def _is_patchable(doc: dict) -> bool:
    if doc.get("user_uploaded_image"):
        return False
    if doc.get("equipmentCategory") and doc.get("productImages"):
        return False
    mid = str(doc.get("_id", ""))
    src = str(doc.get("source") or "")
    return (
        mid.startswith(("seed_", "demo_v2_"))
        or doc.get("is_demo")
        or src in ("training_seed", "seed_sample")
    )


def _listing_type_for_doc(doc: dict) -> str:
    key = str(doc.get("_id") or doc.get("name") or "")
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return "sell" if h % 5 == 0 else "rent"


async def collect_patches() -> list[dict]:
    patches: list[dict] = []
    async for doc in database.machines.find({}):
        if not _is_patchable(doc):
            continue
        category = str(doc.get("category") or "")
        machine_id = str(doc.get("_id") or "")
        meta = resolve_machine_image_metadata(
            category=category,
            machine_id=machine_id,
            existing_images=doc.get("images") or [],
            image_url=str(doc.get("image_url") or ""),
        )
        listing_type = _listing_type_for_doc(doc)
        price = doc.get("price_per_day") or 12000
        update: dict = {
            "image_url": meta.image_url,
            "images": meta.images,
            "image_match_level": meta.image_match_level,
            "image_source": meta.image_source,
            "listing_type": listing_type,
        }
        if listing_type == "sell":
            update["selling_price"] = int(price * 180)
        patches.append({"_id": doc["_id"], "update": update})
    return patches


async def main(apply: bool) -> None:
    patches = await collect_patches()
    rent = sum(1 for p in patches if p["update"]["listing_type"] == "rent")
    sell = len(patches) - rent
    print(f"Patchable demo/seed machines: {len(patches)} (rent={rent}, sell={sell})")
    if not apply:
        for row in patches[:8]:
            print(f"  {row['_id']} -> {row['update']['listing_type']} | {row['update']['image_url'][:72]}...")
        print("Dry run only. Pass --apply to write changes.")
        return
    updated = 0
    for row in patches:
        result = await database.machines.update_one(
            {"_id": row["_id"]},
            {"$set": row["update"]},
        )
        if result.modified_count:
            updated += 1
    print(f"Updated {updated} machine documents.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
