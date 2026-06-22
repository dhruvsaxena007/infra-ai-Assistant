"""
Validate real InfraForge marketplace search against normalized machine data.

Run from infraforge-ai-backend:
    python scripts/validate_real_data_search.py
"""

from __future__ import annotations

import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.intelligent_search import intelligent_machine_search
from app.database.mongodb import database
from app.utils.machine_normalizer import normalize_machine
from app.utils.machine_repository import detect_schema_mode, fetch_machines
from app.utils.reference_cache import get_reference_cache


QUERIES = [
    "crawler drill in jaipur",
    "EPIROC AIR ROC D-35",
    "machine in jaipur under 500",
    "used machine in 302026",
    "rent machine in jaipur",
    "is crawler drill available in jaipur",
]


def _print_machine(prefix: str, machine: dict) -> None:
    specs = machine.get("specifications") or {}
    print(
        f"{prefix} name={machine.get('name')} | category={machine.get('category')} | "
        f"city={machine.get('city')} | price={machine.get('price_per_day')} | "
        f"brand={machine.get('brand')} | model={machine.get('model')} | "
        f"condition={specs.get('condition')} | pincode={specs.get('pincode')}"
    )


async def main() -> None:
    mode = await detect_schema_mode(database)
    print(f"schema_mode={mode}")

    cache = await get_reference_cache(database)
    machines = await fetch_machines(database, limit=5)
    print(f"total_machines_listed={len(await fetch_machines(database))}")
    print("\n--- Normalized sample (first 5) ---")
    for index, machine in enumerate(machines[:5], start=1):
        _print_machine(f"{index}.", machine)

    print("\n--- Intelligent search tests ---")
    for query in QUERIES:
        print(f"\nQuery: {query}")
        try:
            results = await intelligent_machine_search(query, database, limit=3)
            if not results:
                print("  No results")
                continue
            for idx, machine in enumerate(results, start=1):
                _print_machine(f"  {idx}.", machine)
        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")

    print("\nValidation complete — no crashes.")


if __name__ == "__main__":
    asyncio.run(main())
