"""
Debug MongoDB connectivity and machine collection shape.

Usage:
    python scripts/debug_database_status.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings
from app.database.mongodb import database
from app.utils.machine_mapper import is_marketplace_document
from app.utils.machine_repository import detect_schema_mode, search_by_filters


def _safe_keys(doc: dict) -> list[str]:
    return sorted(k for k in doc.keys() if k != "embedding")


async def main() -> None:
    print("=== InfraForge DB Debug ===")
    print(f"database_name: {settings.DATABASE_NAME}")
    print(f"mongodb_url_set: {bool(settings.MONGODB_URL)}")
    print(f"groq_key_set: {bool(settings.GROQ_API_KEY)}")

    await database.command("ping")
    print("ping: ok")

    collections = await database.list_collection_names()
    print(f"collections ({len(collections)}): {', '.join(sorted(collections)[:20])}")
    if len(collections) > 20:
        print(f"  ... and {len(collections) - 20} more")

    total = await database.machines.count_documents({})
    seed_count = await database.machines.count_documents({"source": "training_seed"})
    mp_count = await database.machines.count_documents(
        {
            "$or": [
                {"equipmentCategory": {"$exists": True, "$ne": None}},
                {"rentalPrice": {"$exists": True, "$ne": None}},
                {"listingType": {"$exists": True, "$ne": None}},
            ]
        }
    )
    with_embedding = await database.machines.count_documents({"embedding": {"$exists": True}})

    print(f"machines.total: {total}")
    print(f"machines.training_seed: {seed_count}")
    print(f"machines.marketplace_like: {mp_count}")
    print(f"machines.with_embedding: {with_embedding}")

    sample = await database.machines.find_one({})
    if sample:
        print(f"first_doc._id: {sample.get('_id')}")
        print(f"first_doc.is_marketplace: {is_marketplace_document(sample)}")
        print(f"first_doc.keys: {_safe_keys(sample)}")

    mode = await detect_schema_mode(database)
    print(f"detect_schema_mode: {mode}")

    print("\n--- sample machines (up to 3) ---")
    cursor = database.machines.find({}).limit(3)
    async for doc in cursor:
        slim = {k: doc[k] for k in _safe_keys(doc) if k in (
            "_id", "name", "category", "city", "price_per_day", "rentalPrice",
            "equipmentCategory", "source", "status", "visibility", "listingType",
        )}
        print(json.dumps(slim, default=str, indent=2))

    print("\n--- search smoke tests ---")
    for label, kwargs in (
        ("crawler drill jaipur", {"category": "crawler drill", "city": "jaipur"}),
        ("dump truck delhi", {"category": "dump truck", "city": "delhi"}),
        ("excavator jaipur", {"category": "excavator", "city": "jaipur"}),
    ):
        hits = await search_by_filters(database, **kwargs, limit=5)
        print(f"{label}: {len(hits)} results")
        if hits:
            print(f"  first: {hits[0].get('name')} | {hits[0].get('category')} | {hits[0].get('city')}")


if __name__ == "__main__":
    asyncio.run(main())
