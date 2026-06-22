"""
Generate semantic-search embeddings for marketplace machine listings.

Reads raw machines from MongoDB, normalizes each document, builds embedding
text, and stores the vector on the raw document as `embedding`.

Run after importing the marketplace dump:
    python scripts/generate_marketplace_embeddings.py

Safe to re-run — updates embeddings in place.
"""

from __future__ import annotations

import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.embedding_service import generate_embedding
from app.core.config import settings
from app.database.mongodb import database
from app.utils.machine_normalizer import build_machine_search_text, normalize_machine
from app.utils.reference_cache import get_reference_cache, reset_reference_cache


async def generate_all() -> None:
    if not settings.MONGODB_URL:
        raise RuntimeError("MONGODB_URL is not set")

    reset_reference_cache()
    cache = await get_reference_cache(database)

    updated = 0
    skipped = 0

    async for raw in database.machines.find({}):
        machine_id = raw["_id"]
        normalized = normalize_machine(raw, cache)
        text = build_machine_search_text(normalized)

        if not text.strip():
            skipped += 1
            continue

        embedding = generate_embedding(text)
        await database.machines.update_one(
            {"_id": machine_id},
            {"$set": {"embedding": embedding}},
        )
        updated += 1
        print(f"  embedded: {normalized.get('name')} ({machine_id})")

    print(f"\nDone. Updated={updated}, skipped={skipped}")


def main() -> None:
    print(f"Database: {settings.DATABASE_NAME}")
    asyncio.run(generate_all())


if __name__ == "__main__":
    main()
