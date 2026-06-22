"""
List every machine in MongoDB (full dump / database — no active-only filter).

Writes:
  data/machines_catalog.json   — all normalized machines (no embeddings)
  data/machines_catalog_summary.txt — counts by category, status, image availability

Usage:
    python scripts/list_all_machines.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings
from app.database.mongodb import database
from app.utils.machine_normalizer import normalize_machine
from app.utils.reference_cache import get_reference_cache, reset_reference_cache
from app.utils.sanitize import without_embedding


async def run() -> None:
    if not settings.MONGODB_URL:
        raise RuntimeError("MONGODB_URL is not set in .env")

    reset_reference_cache()
    cache = await get_reference_cache(database)

    total_raw = await database.machines.count_documents({})
    print(f"Database: {settings.DATABASE_NAME}")
    print(f"Raw machines collection count: {total_raw}")

    machines = []
    status_counts: Counter = Counter()
    category_counts: Counter = Counter()
    with_images = 0

    async for raw in database.machines.find({}):
        normalized = normalize_machine(raw, cache)
        clean = without_embedding(normalized)
        machines.append(clean)

        status_counts[str(raw.get("status") or "unknown")] += 1
        cat = clean.get("category_display") or clean.get("category") or "unknown"
        category_counts[cat] += 1
        if clean.get("images") or clean.get("image_url"):
            with_images += 1

    out_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    catalog_path = os.path.join(out_dir, "machines_catalog.json")
    with open(catalog_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "database": settings.DATABASE_NAME,
                "total_machines": len(machines),
                "machines_with_images": with_images,
                "machines": machines,
            },
            fh,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    summary_path = os.path.join(out_dir, "machines_catalog_summary.txt")
    lines = [
        f"Total machines: {len(machines)}",
        f"With at least one image URL: {with_images}",
        "",
        "By status (raw):",
    ]
    for key, count in status_counts.most_common():
        lines.append(f"  {key}: {count}")
    lines.append("")
    lines.append("By category:")
    for key, count in category_counts.most_common():
        lines.append(f"  {key}: {count}")

    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Wrote {catalog_path}")
    print(f"Wrote {summary_path}")
    print(f"Listed {len(machines)} machines ({with_images} with images)")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
