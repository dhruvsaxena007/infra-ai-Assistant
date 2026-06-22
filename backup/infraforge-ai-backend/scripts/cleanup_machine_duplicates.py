"""
Standalone, SAFE cleanup for the MongoDB `machines` collection.

It removes two classes of bad data and keeps one valid record in every other
case:

1. WRONG records  — anything whose name contains "JCB" but is filed under the
   Excavator category (a JCB is a Backhoe Loader, never an excavator).
2. DUPLICATE records — same name + category + city + model + price_per_day.
   The first occurrence is kept, the rest are removed.

Connection details come from app.core.config.settings (MONGODB_URL /
DATABASE_NAME); nothing is hardcoded. Every removal is printed.

Run from the project root:
    python scripts/cleanup_machine_duplicates.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pymongo import MongoClient

from app.core.config import settings


def _dedupe_key(doc: dict):
    return (
        str(doc.get("name", "")).strip().lower(),
        str(doc.get("category", "")).strip().lower(),
        str(doc.get("city", "")).strip().lower(),
        str(doc.get("model", "")).strip().lower(),
        doc.get("price_per_day"),
    )


def remove_wrong_records(collection) -> int:
    """Delete JCB machines mis-categorized as Excavator."""
    wrong_filter = {
        "name": {"$regex": "jcb", "$options": "i"},
        "category": {"$regex": "^excavator$", "$options": "i"},
    }

    count = collection.count_documents(wrong_filter)
    if count:
        for doc in collection.find(wrong_filter, {"name": 1, "city": 1}):
            print(f"  - wrong record (JCB as Excavator): "
                  f"{doc.get('name')} [{doc.get('city')}]")
        collection.delete_many(wrong_filter)

    return count


def remove_duplicates(collection) -> int:
    """Delete exact duplicate listings, keeping the first occurrence."""
    seen: dict = {}
    duplicate_ids: list = []

    for doc in collection.find(
        {},
        {"name": 1, "category": 1, "city": 1, "model": 1, "price_per_day": 1},
    ):
        key = _dedupe_key(doc)
        if key in seen:
            duplicate_ids.append(doc["_id"])
            print(f"  - duplicate: {doc.get('name')} "
                  f"[{doc.get('city')}] ₹{doc.get('price_per_day')}")
        else:
            seen[key] = doc["_id"]

    if duplicate_ids:
        collection.delete_many({"_id": {"$in": duplicate_ids}})

    return len(duplicate_ids)


def cleanup():
    if not settings.MONGODB_URL or not settings.DATABASE_NAME:
        print(
            "ERROR: MONGODB_URL / DATABASE_NAME are not configured. "
            "Check your .env file."
        )
        sys.exit(1)

    print(f"Connecting to database: {settings.DATABASE_NAME}")

    client = MongoClient(settings.MONGODB_URL)
    database = client[settings.DATABASE_NAME]
    collection = database["machines"]

    total_before = collection.count_documents({})
    print(f"Machines before cleanup: {total_before}\n")

    print("Step 1 — removing wrong JCB-as-excavator records...")
    wrong_removed = remove_wrong_records(collection)
    print(f"  Wrong records removed: {wrong_removed}\n")

    print("Step 2 — removing exact duplicate records...")
    duplicates_removed = remove_duplicates(collection)
    print(f"  Duplicate records removed: {duplicates_removed}\n")

    total_after = collection.count_documents({})

    print("Cleanup complete.")
    print(f"  Wrong records removed     : {wrong_removed}")
    print(f"  Duplicate records removed : {duplicates_removed}")
    print(f"  Machines before           : {total_before}")
    print(f"  Machines after            : {total_after}")

    client.close()


if __name__ == "__main__":
    cleanup()
