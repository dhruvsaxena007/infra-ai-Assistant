"""
Seed the MongoDB `machines` collection with realistic construction-equipment
test data for the InfraForge AI assistant.

Design / safety notes:
- Connection comes from app.core.config.settings (MONGODB_URL / DATABASE_NAME).
  No credentials are hardcoded here.
- Embeddings are generated with app.ai.embedding_service.generate_embedding,
  so the seeded records work with semantic and hybrid AI search.
- Records are UPSERTED by the composite key name + category + city + model, so
  running this script multiple times updates the same listing instead of
  creating duplicates.
- Before seeding, a SAFE cleanup runs: it removes wrong records (any JCB named
  as an Excavator) and exact duplicates (same name+category+city+model+price),
  keeping one. Every removal is printed. No other data is deleted.

Run from the project root:
    python scripts/seed_machines.py
"""

import os
import sys

# Make the project root importable so `import app...` works when this file is
# executed directly as `python scripts/seed_machines.py`.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pymongo import MongoClient

from app.core.config import settings
from app.ai.embedding_service import generate_embedding
from data.verified_training_images import get_images_for_category


# ---------------------------------------------------------------------------
# Test machine dataset: 30 machines.
# 10 categories x 3 machines each, spread across 10 cities (3 machines/city).
# Prices follow the agreed per-category ranges.
# ---------------------------------------------------------------------------

MACHINES = [
    # ----------------------------- EXCAVATOR (real excavators only) -----------------------------
    # Strictly genuine excavators. JCB / backhoe machines must NEVER appear here.
    {
        "name": "CAT 320D Excavator",
        "category": "excavator", "brand": "Caterpillar", "model": "320D",
        "city": "Jaipur", "price_per_day": 9500, "rating": 4.8,
        "description": "Reliable crawler excavator for excavation, trenching and material loading on commercial site development.",
        "availability_status": "available", "owner_name": "Marwar Heavy Equipments",
        "image_url": "",
    },
    {
        "name": "Tata Hitachi EX 200 Excavator",
        "category": "excavator", "brand": "Tata Hitachi", "model": "EX 200",
        "city": "Jaipur", "price_per_day": 9500, "rating": 4.6,
        "description": "Heavy-duty excavator ideal for excavation, earthmoving and site development on large construction projects.",
        "availability_status": "available", "owner_name": "Rajesh Construction Co",
        "image_url": "",
    },
    {
        "name": "Komatsu PC210 Excavator",
        "category": "excavator", "brand": "Komatsu", "model": "PC210",
        "city": "Delhi", "price_per_day": 11000, "rating": 4.7,
        "description": "Powerful crawler excavator used for deep excavation, foundation digging and earthmoving in highway work.",
        "availability_status": "available", "owner_name": "Sharma Earthmovers",
        "image_url": "",
    },
    {
        "name": "Hyundai R215 Excavator",
        "category": "excavator", "brand": "Hyundai", "model": "R215",
        "city": "Mumbai", "price_per_day": 12000, "rating": 4.7,
        "description": "Hydraulic crawler excavator for deep excavation, trenching and bulk earthmoving on large commercial projects.",
        "availability_status": "available", "owner_name": "Coastal Infra Rentals",
        "image_url": "",
    },
    {
        "name": "Volvo EC210 Excavator",
        "category": "excavator", "brand": "Volvo", "model": "EC210",
        "city": "Pune", "price_per_day": 12500, "rating": 4.8,
        "description": "Fuel-efficient excavator for excavation, foundation digging and material handling on site development work.",
        "availability_status": "available", "owner_name": "Sahyadri Earthworks",
        "image_url": "",
    },

    # ------------------------- BACKHOE LOADER / JCB (3500-7000) -------------------------
    {
        "name": "JCB 3DX Backhoe Loader",
        "category": "backhoe loader", "brand": "JCB", "model": "3DX",
        "city": "Pune", "price_per_day": 4500, "rating": 4.5,
        "description": "Versatile backhoe loader for excavation, loading and road construction on small to medium sites.",
        "availability_status": "available", "owner_name": "Pune Site Services",
        "image_url": "",
    },
    {
        "name": "CASE 770 Backhoe Loader",
        "category": "backhoe loader", "brand": "CASE", "model": "770",
        "city": "Ahmedabad", "price_per_day": 5200, "rating": 4.3,
        "description": "Dependable backhoe loader for digging, loading and material handling in site development work.",
        "availability_status": "available", "owner_name": "Patel Equipments",
        "image_url": "",
    },
    {
        "name": "Mahindra EarthMaster Backhoe Loader",
        "category": "backhoe loader", "brand": "Mahindra", "model": "EarthMaster",
        "city": "Gurgaon", "price_per_day": 4000, "rating": 4.2,
        "description": "Fuel-efficient backhoe loader suited for excavation, loading and light road construction.",
        "availability_status": "available", "owner_name": "NCR Machine Hub",
        "image_url": "",
    },

    # ------------------------------ HYDRA CRANE (5000-10000) ------------------------------
    {
        "name": "ACE 14XW Hydra Crane",
        "category": "hydra crane", "brand": "ACE", "model": "14XW",
        "city": "Noida", "price_per_day": 7000, "rating": 4.4,
        "description": "Mobile hydra crane for lifting and shifting heavy loads at construction and material transport sites.",
        "availability_status": "available", "owner_name": "Noida Lifters",
        "image_url": "",
    },
    {
        "name": "Escorts Hydra 12T Crane",
        "category": "hydra crane", "brand": "Escorts", "model": "Hydra 12T",
        "city": "Bangalore", "price_per_day": 6500, "rating": 4.1,
        "description": "Compact hydra crane for lifting precast elements and loading material on tight urban sites.",
        "availability_status": "maintenance", "owner_name": "Bengaluru Crane Rentals",
        "image_url": "",
    },
    {
        "name": "ACE NX150 Hydra Crane",
        "category": "hydra crane", "brand": "ACE", "model": "NX150",
        "city": "Hyderabad", "price_per_day": 9000, "rating": 4.6,
        "description": "High-capacity hydra crane for heavy lifting and material transport on highway and bridge work.",
        "availability_status": "available", "owner_name": "Deccan Heavy Lifts",
        "image_url": "",
    },

    # --------------------------------- CRANE (9000-20000) ---------------------------------
    {
        "name": "Kobelco RK250 Mobile Crane",
        "category": "crane", "brand": "Kobelco", "model": "RK250",
        "city": "Chennai", "price_per_day": 16000, "rating": 4.7,
        "description": "Rough-terrain mobile crane for heavy lifting on industrial and large site development projects.",
        "availability_status": "available", "owner_name": "Chennai Crane Works",
        "image_url": "",
    },
    {
        "name": "Grove RT540E Crane",
        "category": "crane", "brand": "Grove", "model": "RT540E",
        "city": "Jaipur", "price_per_day": 18000, "rating": 4.8,
        "description": "Powerful rough-terrain crane for lifting structural steel and heavy components in highway work.",
        "availability_status": "rented", "owner_name": "Marwar Heavy Equipments",
        "image_url": "",
    },
    {
        "name": "TIL 3013 Truck Crane",
        "category": "crane", "brand": "TIL", "model": "3013",
        "city": "Delhi", "price_per_day": 13000, "rating": 4.3,
        "description": "Truck-mounted crane for lifting and material transport across multiple construction sites.",
        "availability_status": "available", "owner_name": "Capital Crane Services",
        "image_url": "",
    },

    # ------------------------------- BULLDOZER (8000-16000) -------------------------------
    {
        "name": "Caterpillar D6 Bulldozer",
        "category": "bulldozer", "brand": "Caterpillar", "model": "D6",
        "city": "Mumbai", "price_per_day": 14000, "rating": 4.7,
        "description": "Track-type bulldozer for earthmoving, grading and site development on large projects.",
        "availability_status": "available", "owner_name": "Coastal Infra Rentals",
        "image_url": "",
    },
    {
        "name": "Komatsu D65 Bulldozer",
        "category": "bulldozer", "brand": "Komatsu", "model": "D65",
        "city": "Pune", "price_per_day": 15000, "rating": 4.6,
        "description": "Heavy bulldozer for earthmoving, land clearing and highway embankment construction.",
        "availability_status": "available", "owner_name": "Sahyadri Earthworks",
        "image_url": "",
    },
    {
        "name": "BEML BD80 Bulldozer",
        "category": "bulldozer", "brand": "BEML", "model": "BD80",
        "city": "Ahmedabad", "price_per_day": 11000, "rating": 4.2,
        "description": "Rugged bulldozer for earthmoving, pushing and grading during site development.",
        "availability_status": "rented", "owner_name": "Gujarat Heavy Machines",
        "image_url": "",
    },

    # ------------------------------- ROAD ROLLER (4000-9000) -------------------------------
    {
        "name": "JCB VMT 330 Road Roller",
        "category": "road roller", "brand": "JCB", "model": "VMT 330",
        "city": "Gurgaon", "price_per_day": 6000, "rating": 4.4,
        "description": "Vibratory road roller for soil and asphalt compaction in road construction and highway work.",
        "availability_status": "available", "owner_name": "NCR Machine Hub",
        "image_url": "",
    },
    {
        "name": "Caterpillar CB7 Road Roller",
        "category": "road roller", "brand": "Caterpillar", "model": "CB7",
        "city": "Noida", "price_per_day": 7500, "rating": 4.5,
        "description": "Tandem vibratory roller for high-quality asphalt compaction on highway and road projects.",
        "availability_status": "available", "owner_name": "Noida Lifters",
        "image_url": "",
    },
    {
        "name": "CASE 1107 Road Roller",
        "category": "road roller", "brand": "CASE", "model": "1107",
        "city": "Bangalore", "price_per_day": 5000, "rating": 4.1,
        "description": "Single-drum compactor for soil compaction during road construction and site development.",
        "availability_status": "available", "owner_name": "Bengaluru Crane Rentals",
        "image_url": "",
    },

    # -------------------------------- DUMP TRUCK (3500-8000) --------------------------------
    {
        "name": "Tata Prima 2528 Dump Truck",
        "category": "dump truck", "brand": "Tata", "model": "Prima 2528",
        "city": "Hyderabad", "price_per_day": 6000, "rating": 4.3,
        "description": "Tipper dump truck for material transport of sand, aggregate and debris on construction sites.",
        "availability_status": "available", "owner_name": "Deccan Heavy Lifts",
        "image_url": "",
    },
    {
        "name": "Ashok Leyland 2518 Dump Truck",
        "category": "dump truck", "brand": "Ashok Leyland", "model": "2518",
        "city": "Chennai", "price_per_day": 5500, "rating": 4.2,
        "description": "Reliable dump truck for material transport and earthmoving haulage in highway work.",
        "availability_status": "available", "owner_name": "Chennai Crane Works",
        "image_url": "",
    },
    {
        "name": "BharatBenz 2823 Dump Truck",
        "category": "dump truck", "brand": "BharatBenz", "model": "2823",
        "city": "Jaipur", "price_per_day": 7000, "rating": 4.5,
        "description": "Heavy-duty tipper for transporting excavated material and aggregate during site development.",
        "availability_status": "rented", "owner_name": "Marwar Heavy Equipments",
        "image_url": "",
    },

    # ------------------------------ CONCRETE MIXER (2500-6000) ------------------------------
    {
        "name": "Schwing Stetter AM Concrete Mixer",
        "category": "concrete mixer", "brand": "Schwing Stetter", "model": "AM Series",
        "city": "Delhi", "price_per_day": 4500, "rating": 4.4,
        "description": "Transit concrete mixer for mixing and material transport of ready-mix concrete to site.",
        "availability_status": "available", "owner_name": "Capital Crane Services",
        "image_url": "",
    },
    {
        "name": "Ajax ARGO 4000 Concrete Mixer",
        "category": "concrete mixer", "brand": "Ajax", "model": "ARGO 4000",
        "city": "Mumbai", "price_per_day": 5000, "rating": 4.3,
        "description": "Self-loading concrete mixer for on-site concrete production during road construction.",
        "availability_status": "available", "owner_name": "Coastal Infra Rentals",
        "image_url": "",
    },
    {
        "name": "Greaves 5/3.5 Concrete Mixer",
        "category": "concrete mixer", "brand": "Greaves", "model": "5/3.5",
        "city": "Pune", "price_per_day": 3000, "rating": 4.0,
        "description": "Compact concrete mixer for small-scale mixing and loading on building construction sites.",
        "availability_status": "available", "owner_name": "Sahyadri Earthworks",
        "image_url": "",
    },

    # ------------------------------- MOTOR GRADER (9000-18000) -------------------------------
    {
        "name": "Caterpillar 120K Motor Grader",
        "category": "motor grader", "brand": "Caterpillar", "model": "120K",
        "city": "Ahmedabad", "price_per_day": 14000, "rating": 4.6,
        "description": "Motor grader for fine grading, leveling and surface preparation in highway work.",
        "availability_status": "available", "owner_name": "Gujarat Heavy Machines",
        "image_url": "",
    },
    {
        "name": "Komatsu GD535 Motor Grader",
        "category": "motor grader", "brand": "Komatsu", "model": "GD535",
        "city": "Gurgaon", "price_per_day": 16000, "rating": 4.7,
        "description": "Precision motor grader for road construction, grading and large site development.",
        "availability_status": "rented", "owner_name": "NCR Machine Hub",
        "image_url": "",
    },
    {
        "name": "BEML BG605 Motor Grader",
        "category": "motor grader", "brand": "BEML", "model": "BG605",
        "city": "Noida", "price_per_day": 12000, "rating": 4.2,
        "description": "Robust motor grader for earthmoving, leveling and highway embankment finishing.",
        "availability_status": "available", "owner_name": "Noida Lifters",
        "image_url": "",
    },

    # ------------------------------- WHEEL LOADER (6000-13000) -------------------------------
    {
        "name": "Caterpillar 950GC Wheel Loader",
        "category": "wheel loader", "brand": "Caterpillar", "model": "950GC",
        "city": "Bangalore", "price_per_day": 10000, "rating": 4.6,
        "description": "Wheel loader for loading, material handling and stockpiling on site development projects.",
        "availability_status": "available", "owner_name": "Bengaluru Crane Rentals",
        "image_url": "",
    },
    {
        "name": "Komatsu WA380 Wheel Loader",
        "category": "wheel loader", "brand": "Komatsu", "model": "WA380",
        "city": "Hyderabad", "price_per_day": 12000, "rating": 4.7,
        "description": "High-capacity wheel loader for loading aggregate and earthmoving in quarry and highway work.",
        "availability_status": "available", "owner_name": "Deccan Heavy Lifts",
        "image_url": "",
    },
    {
        "name": "JCB 433 Wheel Loader",
        "category": "wheel loader", "brand": "JCB", "model": "433",
        "city": "Chennai", "price_per_day": 8000, "rating": 4.3,
        "description": "Efficient wheel loader for loading, material transport and site development tasks.",
        "availability_status": "available", "owner_name": "Chennai Crane Works",
        "image_url": "",
    },

    # ----------------- EXTRA BACKHOE LOADER / JCB INVENTORY (3500-9000) -----------------
    # Added so JCB / Backhoe Loader queries return strong exact matches,
    # especially in Jaipur and Delhi. Category is exactly "backhoe loader".
    {
        "name": "JCB 3DX Backhoe Loader - Jaipur",
        "category": "backhoe loader", "brand": "JCB", "model": "3DX",
        "city": "Jaipur", "price_per_day": 6500, "rating": 4.6,
        "description": "JCB 3DX backhoe loader for excavation, loading and road construction; ideal all-round digging and loading machine.",
        "availability_status": "available", "owner_name": "Marwar Heavy Equipments",
        "image_url": "",
    },
    {
        "name": "JCB 3DX Super Backhoe Loader",
        "category": "backhoe loader", "brand": "JCB", "model": "3DX Super",
        "city": "Delhi", "price_per_day": 7000, "rating": 4.7,
        "description": "JCB 3DX Super backhoe loader built for heavy excavation, loading and road construction work on busy urban sites.",
        "availability_status": "available", "owner_name": "Capital Crane Services",
        "image_url": "",
    },
    {
        "name": "CASE 770EX Backhoe Loader",
        "category": "backhoe loader", "brand": "CASE", "model": "770EX",
        "city": "Jaipur", "price_per_day": 6000, "rating": 4.4,
        "description": "CASE 770EX backhoe loader for excavation, loading and material handling during site development and road construction.",
        "availability_status": "available", "owner_name": "Rajasthan Earthmovers",
        "image_url": "",
    },
    {
        "name": "JCB 4DX Backhoe Loader",
        "category": "backhoe loader", "brand": "JCB", "model": "4DX",
        "city": "Mumbai", "price_per_day": 8500, "rating": 4.7,
        "description": "JCB 4DX backhoe loader offering higher backhoe digging depth for excavation, loading and road construction projects.",
        "availability_status": "available", "owner_name": "Coastal Infra Rentals",
        "image_url": "",
    },
    {
        "name": "CAT 424 Backhoe Loader",
        "category": "backhoe loader", "brand": "Caterpillar", "model": "424",
        "city": "Pune", "price_per_day": 7500, "rating": 4.5,
        "description": "CAT 424 backhoe loader for excavation, loading and trenching; a versatile JCB-style backhoe loader for road construction.",
        "availability_status": "available", "owner_name": "Sahyadri Earthworks",
        "image_url": "",
    },
]


def cleanup_collection(collection) -> None:
    """
    Safe, clearly-printed cleanup run before seeding.

    1. Remove WRONG records: anything whose name contains "JCB" but is filed
       under the Excavator category (a JCB is a Backhoe Loader, never an
       excavator).
    2. Remove EXACT duplicates: same name + category + city + model +
       price_per_day, keeping the first occurrence.
    """
    print("\nCleanup: scanning for wrong / duplicate records...")

    # --- 1) wrong JCB-as-excavator records -------------------------------
    wrong_filter = {
        "name": {"$regex": "jcb", "$options": "i"},
        "category": {"$regex": "^excavator$", "$options": "i"},
    }
    wrong_count = collection.count_documents(wrong_filter)
    if wrong_count:
        for doc in collection.find(wrong_filter, {"name": 1, "city": 1}):
            print(f"  - removing wrong record (JCB as Excavator): "
                  f"{doc.get('name')} [{doc.get('city')}]")
        collection.delete_many(wrong_filter)
    print(f"  Wrong JCB-as-excavator records removed: {wrong_count}")

    # --- 2) exact duplicates ---------------------------------------------
    seen: dict = {}
    duplicate_ids: list = []
    for doc in collection.find(
        {},
        {"name": 1, "category": 1, "city": 1, "model": 1, "price_per_day": 1},
    ):
        key = (
            str(doc.get("name", "")).strip().lower(),
            str(doc.get("category", "")).strip().lower(),
            str(doc.get("city", "")).strip().lower(),
            str(doc.get("model", "")).strip().lower(),
            doc.get("price_per_day"),
        )
        if key in seen:
            duplicate_ids.append(doc["_id"])
            print(f"  - removing duplicate: {doc.get('name')} "
                  f"[{doc.get('city')}] ₹{doc.get('price_per_day')}")
        else:
            seen[key] = doc["_id"]

    if duplicate_ids:
        collection.delete_many({"_id": {"$in": duplicate_ids}})
    print(f"  Exact duplicate records removed: {len(duplicate_ids)}")


def build_embedding_text(machine: dict) -> str:
    """Text used to generate the semantic embedding for a machine."""
    return (
        f"{machine['name']} "
        f"{machine['category']} "
        f"{machine['brand']} "
        f"{machine['model']} "
        f"{machine['description']}"
    )


def seed():
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

    # Remove wrong / duplicate records before (re)seeding.
    cleanup_collection(collection)

    inserted = 0
    updated = 0

    for index, machine in enumerate(MACHINES, start=1):

        record = dict(machine)

        print(f"[{index}/{len(MACHINES)}] Embedding: {record['name']}")

        category = str(record.get("category") or "").strip().lower()
        stock_images = get_images_for_category(category)
        if stock_images:
            record["images"] = stock_images[:3]
            record["image_url"] = stock_images[0]

        record["embedding"] = generate_embedding(
            build_embedding_text(record)
        )

        result = collection.update_one(
            {
                "name": record["name"],
                "category": record["category"],
                "city": record["city"],
                "model": record["model"],
            },
            {"$set": record},
            upsert=True,
        )

        if result.upserted_id is not None:
            inserted += 1
        elif result.modified_count > 0:
            updated += 1

    total = collection.count_documents({})

    print("\nSeeding complete.")
    print(f"  New machines inserted : {inserted}")
    print(f"  Existing updated      : {updated}")
    print(f"  Total machines in DB  : {total}")

    client.close()


if __name__ == "__main__":
    seed()
