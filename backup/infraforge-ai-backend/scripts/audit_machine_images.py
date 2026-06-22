#!/usr/bin/env python3
"""
Scan machine listings for missing or suspicious hero images.

Usage (from infraforge-ai-backend):
    python scripts/audit_machine_images.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.mongodb import database
from app.utils.machine_image_resolver import is_plausible_equipment_image


async def main() -> None:
    coll = database.machines
    total = 0
    missing = 0
    suspicious = 0

    print("Machine image audit")
    print("-" * 72)

    async for doc in coll.find({}):
        total += 1
        name = doc.get("name") or doc.get("title") or doc.get("_id")
        category = doc.get("category") or ""
        image_url = (doc.get("image_url") or "").strip()
        images = doc.get("images") or []
        if isinstance(images, str):
            images = [images]

        primary = image_url or (images[0] if images else "")
        if not primary:
            missing += 1
            print(f"[MISSING] {name} | {category} | (no image)")
            continue

        if not is_plausible_equipment_image(primary, category):
            suspicious += 1
            print(f"[SUSPICIOUS] {name} | {category} | {primary}")

    print("-" * 72)
    print(f"Total: {total} | Missing: {missing} | Suspicious: {suspicious}")


if __name__ == "__main__":
    asyncio.run(main())
