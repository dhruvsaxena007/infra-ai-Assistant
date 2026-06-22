"""
Debug a natural-language search query end-to-end.

Usage:
    python scripts/debug_search_query.py "crawler drill in jaipur"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.intelligent_search import intelligent_machine_search
from app.ai.query_parser import parse_query
from app.database.mongodb import database
from app.utils.machine_repository import build_mongo_filter, detect_schema_mode, search_by_filters


async def main(query: str) -> None:
    print(f"query: {query}")
    print(f"schema_mode: {await detect_schema_mode(database)}")
    filters = parse_query(query)
    print(f"parsed_filters: {json.dumps(filters, indent=2)}")
    mongo_filter = await build_mongo_filter(database, filters)
    print(f"mongo_filter: {json.dumps(mongo_filter, default=str, indent=2)}")

    strict = await search_by_filters(
        database,
        category=filters.get("category"),
        city=filters.get("city"),
        max_price=filters.get("max_price"),
        limit=5,
    )
    print(f"search_by_filters: {len(strict)} hits")
    for m in strict[:3]:
        print(f"  - {m.get('name')} | {m.get('category')} | {m.get('city')}")

    intel = await intelligent_machine_search(query, database, limit=5)
    print(f"intelligent_machine_search: {len(intel)} hits")
    for m in intel[:3]:
        print(f"  - {m.get('name')} | score={m.get('final_score')}")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "crawler drill in jaipur"
    asyncio.run(main(q))
