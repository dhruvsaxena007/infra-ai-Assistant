"""
Coverage planning for demo machine catalog seeding.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.ai.category_mapping import CANONICAL_CATEGORIES

TARGET_PER_COMBO = 5
MIN_BEFORE_PRIORITIZE = 4

CITIES = [
    "Jaipur", "Delhi", "Mumbai", "Pune", "Ahmedabad",
    "Gurgaon", "Hyderabad", "Chennai", "Kota", "Bangalore",
]

# Priority categories for search testing (subset of canonical — not exhaustive hardcode)
PRIORITY_CATEGORIES = [
    "excavator", "backhoe loader", "crane", "road roller", "dump truck",
    "wheel loader", "motor grader", "concrete mixer", "crawler drill",
    "mobile crusher", "forklift", "bulldozer", "compactor", "hydra crane",
    "concrete pump", "asphalt paver",
]


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


def count_existing_by_combo(docs: list[dict]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for doc in docs:
        cat = str(doc.get("category") or "").strip().lower()
        city = str(doc.get("city") or "").strip().title()
        if cat and city:
            counts[(cat, city)] += 1
    return counts


def plan_coverage(
    existing_docs: list[dict],
    *,
    target_additions: int = 350,
    categories: list[str] | None = None,
    cities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Return a list of planned additions: {category, city, count, priority}.
    """
    categories = categories or list(CANONICAL_CATEGORIES)
    cities = cities or CITIES
    counts = count_existing_by_combo(existing_docs)
    plan: list[dict[str, Any]] = []
    remaining = target_additions

    def add_slot(cat: str, city: str, n: int, priority: int) -> int:
        nonlocal remaining
        if remaining <= 0 or n <= 0:
            return 0
        take = min(n, remaining)
        plan.append({
            "category": cat,
            "city": city,
            "count": take,
            "existing": counts.get((cat, city), 0),
            "priority": priority,
        })
        remaining -= take
        return take

    # Phase 1: priority category × city gaps
    for cat in PRIORITY_CATEGORIES:
        if cat not in categories:
            continue
        for city in cities:
            existing = counts.get((cat, city), 0)
            if existing < TARGET_PER_COMBO:
                need = TARGET_PER_COMBO - existing
                add_slot(cat, city, need, priority=1)

    # Phase 2: other canonical categories
    for cat in categories:
        if cat in PRIORITY_CATEGORIES:
            continue
        for city in cities:
            existing = counts.get((cat, city), 0)
            if existing < MIN_BEFORE_PRIORITIZE:
                need = MIN_BEFORE_PRIORITIZE - existing
                add_slot(cat, city, need, priority=2)
            if remaining <= 0:
                break
        if remaining <= 0:
            break

    # Phase 3: fill remaining budget across priority combos
    if remaining > 0:
        for cat in PRIORITY_CATEGORIES:
            for city in cities:
                add_slot(cat, city, 1, priority=3)
                if remaining <= 0:
                    break
            if remaining <= 0:
                break

    return plan


def format_coverage_report(
    plan: list[dict],
    *,
    inserted_by_combo: dict[tuple[str, str], int] | None = None,
) -> str:
    lines = ["Category | City | Existing | Planned | Final | Target met"]
    inserted_by_combo = inserted_by_combo or {}
    for row in sorted(plan, key=lambda r: (r["priority"], r["category"], r["city"])):
        cat, city = row["category"], row["city"]
        existing = row["existing"]
        planned = row["count"]
        added = inserted_by_combo.get((cat, city), planned)
        final = existing + added
        met = "yes" if final >= MIN_BEFORE_PRIORITIZE else "partial"
        lines.append(f"{cat} | {city} | {existing} | {planned} | {final} | {met}")
    return "\n".join(lines)
