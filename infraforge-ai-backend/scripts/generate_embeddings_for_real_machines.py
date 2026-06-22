"""
Generate or refresh embeddings for machines missing them.

Usage:
    python scripts/generate_embeddings_for_real_machines.py
    python scripts/generate_embeddings_for_real_machines.py --force
    python scripts/generate_embeddings_for_real_machines.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.embedding_service import generate_embedding
from app.database.mongodb import database
from app.utils.machine_normalizer import build_machine_search_text, normalize_machine
from app.utils.reference_cache import get_reference_cache


async def run(*, force: bool = False, dry_run: bool = False) -> dict:
    cache = await get_reference_cache(database)
    updated = skipped = 0

    async for raw in database.machines.find({}):
        if raw.get("embedding") and not force:
            skipped += 1
            continue

        normalized = normalize_machine(raw, cache)
        text = build_machine_search_text(normalized)
        if not text.strip():
            skipped += 1
            continue

        if dry_run:
            print(f"would update: {normalized.get('id')} | {normalized.get('name')}")
            updated += 1
            continue

        embedding = generate_embedding(text)
        await database.machines.update_one(
            {"_id": raw["_id"]},
            {"$set": {"embedding": embedding}},
        )
        updated += 1
        print(f"updated: {normalized.get('id')} | {normalized.get('name')}")

    return {"updated": updated, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-embed even if embedding exists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = asyncio.run(run(force=args.force, dry_run=args.dry_run))
    print(stats)


if __name__ == "__main__":
    main()
