#!/usr/bin/env python3
"""
Idempotent machine image migration with backup and rollback.

Usage:
    python scripts/migrate_machine_images.py --audit
    python scripts/migrate_machine_images.py --dry-run
    python scripts/migrate_machine_images.py --apply
    python scripts/migrate_machine_images.py --rollback
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIGRATION_VERSION = "image_migration_v1"
BACKUP_DIR = ROOT / "data" / "backups"

from app.database.mongodb import database
from app.utils.machine_image_metadata import (
    classify_listing_image,
    resolve_machine_image_metadata,
)


def _is_genuine_user_upload(doc: dict) -> bool:
    """Never modify verified user-uploaded marketplace photos."""
    if doc.get("user_uploaded_image"):
        return True
    if doc.get("equipmentCategory") and doc.get("productImages"):
        src = str(doc.get("source") or "")
        if src not in ("training_seed", "seed_sample") and not doc.get("is_demo"):
            primary = doc.get("productImages") or []
            if isinstance(primary, list) and primary:
                cat = str(doc.get("category") or "")
                url = str(primary[0])
                if classify_listing_image(url, category=cat) == "exact_listing":
                    return True
    return False


def _is_demo_seed_owned(doc: dict) -> bool:
    if doc.get("is_demo") and doc.get("seed_version"):
        return True
    if str(doc.get("_id", "")).startswith(("seed_", "demo_v2_")):
        return True
    return doc.get("source") in ("training_seed", "seed_sample")


def _needs_repair(doc: dict) -> bool:
    if _is_genuine_user_upload(doc):
        return False
    category = str(doc.get("category") or "")
    primary = str(doc.get("image_url") or "").strip()
    images = doc.get("images") or []
    if not primary and images:
        primary = str(images[0])
    if not primary:
        return True
    cls = classify_listing_image(primary, category=category)
    return cls in ("missing", "unrelated", "broken", "unsupported_format", "generic_industry")


async def collect_changes() -> list[dict]:
    changes: list[dict] = []
    async for doc in database.machines.find({}):
        if _is_genuine_user_upload(doc):
            continue
        # Only repair demo/synthetic seed records — never marketplace listings
        if not _is_demo_seed_owned(doc):
            continue
        if not _needs_repair(doc):
            continue

        mid = str(doc.get("_id"))
        category = str(doc.get("category") or "")
        meta = resolve_machine_image_metadata(
            category=category,
            existing_images=doc.get("images") if isinstance(doc.get("images"), list) else [],
            machine_id=mid,
            image_url=str(doc.get("image_url") or ""),
            brand=str(doc.get("brand") or ""),
            model=str(doc.get("model") or ""),
        )
        if not meta.image_url:
            continue
        changes.append({
            "_id": doc["_id"],
            "name": doc.get("name"),
            "category": category,
            "before": {
                "image_url": doc.get("image_url"),
                "images": doc.get("images"),
            },
            "after": {
                "image_url": meta.image_url,
                "images": meta.images,
                "image_match_level": meta.image_match_level,
                "image_source": meta.image_source,
                "image_migration_version": MIGRATION_VERSION,
                "image_migrated_at": datetime.now(timezone.utc).isoformat(),
            },
        })
    return changes


def _backup_path() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR / f"{MIGRATION_VERSION}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"


async def dry_run() -> None:
    changes = await collect_changes()
    by_cat = Counter(c["category"] for c in changes)
    print(f"Would update {len(changes)} records")
    for cat, n in by_cat.most_common(20):
        print(f"  {cat}: {n}")
    for c in changes[:10]:
        print(f"  - {c['name']} ({c['category']})")


async def apply() -> None:
    changes = await collect_changes()
    backup = {
        "migration_version": MIGRATION_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "records": changes,
    }
    path = _backup_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2, default=str)
    print(f"Backup saved: {path}")

    updated = 0
    for c in changes:
        await database.machines.update_one(
            {"_id": c["_id"]},
            {"$set": c["after"]},
        )
        updated += 1
    print(f"Updated {updated} records")


async def rollback() -> None:
    files = sorted(BACKUP_DIR.glob(f"{MIGRATION_VERSION}_*.json"), reverse=True)
    if not files:
        print("No backup found for rollback")
        return
    path = files[0]
    with open(path, encoding="utf-8") as f:
        backup = json.load(f)
    restored = 0
    for rec in backup.get("records", []):
        before = rec.get("before") or {}
        await database.machines.update_one(
            {"_id": rec["_id"]},
            {"$set": {
                "image_url": before.get("image_url"),
                "images": before.get("images"),
            }, "$unset": {
                "image_migration_version": "",
                "image_migrated_at": "",
                "image_match_level": "",
                "image_source": "",
            }},
        )
        restored += 1
    print(f"Rolled back {restored} records from {path}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    if args.rollback:
        await rollback()
    elif args.apply:
        await apply()
    elif args.dry_run or args.audit:
        await dry_run()
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
