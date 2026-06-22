#!/usr/bin/env python3
"""
Replace missing or implausible machine hero images with category placeholders.

Usage (from infraforge-ai-backend):
    python scripts/fix_machine_images.py
    python scripts/fix_machine_images.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.mongodb import database
from app.utils.machine_image_resolver import (
    is_plausible_equipment_image,
    resolve_machine_images,
)


async def main(dry_run: bool) -> None:
    coll = database.machines
    updated = 0
    scanned = 0

    async for doc in coll.find({}):
        scanned += 1
        mid = str(doc.get("_id", ""))
        category = doc.get("category") or "support"
        image_url = (doc.get("image_url") or "").strip()
        images = doc.get("images") or []
        if isinstance(images, str):
            images = [images]

        primary = image_url or (images[0] if images else "")
        if primary and is_plausible_equipment_image(primary, category):
            continue

        new_images, new_primary = resolve_machine_images(
            category,
            images if isinstance(images, list) else [],
            machine_id=mid,
            image_url=image_url,
        )
        if not new_primary:
            continue

        print(f"Fix: {doc.get('name')} ({category}) -> {new_primary[:80]}...")
        if not dry_run:
            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"image_url": new_primary, "images": new_images}},
            )
        updated += 1

    print(f"Scanned {scanned} | {'Would update' if dry_run else 'Updated'} {updated}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
