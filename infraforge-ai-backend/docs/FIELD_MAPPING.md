# InfraForge Marketplace — Field Mapping Report

This document maps the **current AI assistant (seed/sample) schema** to the **real InfraForge marketplace MongoDB schema** documented in `scripts/dump_report.txt` and the `marketplace_mongo_dump` collections.

> **Note:** The dump folder contains BSON exports for collections listed below. The authoritative field frequencies and sample documents were verified from `scripts/dump_report.txt` (19 machines, 70 equipment categories, 4231 cities).

---

## Collections in Real Marketplace DB

| Collection | Docs | Purpose |
|------------|------|---------|
| `machines` | 19 | Equipment listings (rent/sell) |
| `equipmentcategories` | 70 | Category taxonomy with nested brands/models |
| `cities` | 4231 | City lookup (ObjectId → name) |
| `states` | 36 | State lookup |
| `countries` | 243 | Country lookup |
| `users` | 17 | Seller accounts (`owner` ref on machines) |
| `reviews` | 3 | Product ratings (`product` → machine `_id`) |
| `payments`, `messages`, `wishlists`, `chats`, `blogs`, `contacts`, `faqs` | — | Not used by AI search |

---

## Primary Machine Field Mapping

| Normalized (AI/Frontend) | Sample/Seed Field | Real Marketplace Field | Notes |
|--------------------------|-------------------|------------------------|-------|
| `id` / `_id` | `_id` | `_id` | ObjectId → string |
| `name` | `name` | **computed** | Built from resolved `brand` + `modelName` + `variant` |
| `category` | `category` (string) | `equipmentCategory` (ObjectId) | Resolved via `equipmentcategories.category`, then mapped to canonical |
| `category_display` | — | `equipmentcategories.category` | Original marketplace label, e.g. `"AIR COMPRESSOR"` |
| `city` | `city` (string) | `equipmentLocation` + `city` (ObjectId) | Prefer `equipmentLocation` string; fallback to `cities.name` |
| `price_per_day` | `price_per_day` | `rentalPrice` | Only on rent listings (`listingType: "rent"`) |
| `rating` | `rating` | **computed** | Average from `reviews` where `product == _id`; default `None` |
| `images` | — | `productImages[]` | Cloudinary URLs |
| `image_url` | `image_url` | `productImages[0]` or `productThumbnails[0]` | Backward-compat single image |
| `description` | `description` | `description` | Often empty in real data |
| `seller_name` / `owner_name` | `owner_name` | `sellerName` | Also `companyName` when present |
| `availability` | derived from `availability_status` | `status == "active"` | Boolean |
| `availability_status` | `"available"` / `"rented"` | `status` | `"active"` → `"available"` |
| `brand` | `brand` (string) | `brand` (ObjectId) | Resolved via nested `equipmentcategories.brands[].name` |
| `model` | `model` | `modelName` (ObjectId) | Resolved via nested `equipmentcategories.brands[].models[].name` |
| `specifications` | — | many optional fields | See spec mapping below |
| `listing_type` | — | `listingType` | `"rent"` or `"sell"` |
| `selling_price` | — | `sellingPrice` | Sell listings only |
| `security_deposit` | — | `securityDeposit` | Rent listings |
| `rent_type` | — | `rentType` | e.g. `"daily"` |
| `slug` | — | `slug` | Marketplace URL slug |
| `visibility` | — | `visibility` | Filter: `"public"` only |
| `embedding` | `embedding` | **generated** | Required for semantic search; added by `scripts/generate_marketplace_embeddings.py` |
| `source` | — | — | `"infraforge_real_db"` or `"seed_sample"` |

---

## Nested Reference Resolution

### `equipmentCategory` → category name

```
machines.equipmentCategory (ObjectId)
  → equipmentcategories._id
  → equipmentcategories.category  (e.g. "SENSOR PAVER 7 MTR")
  → canonical category via category_mapping.marketplace_category_to_canonical()
```

### `brand` → brand name

```
machines.brand (ObjectId)
  → equipmentcategories.brands[]._id
  → equipmentcategories.brands[].name  (e.g. "JCB", "CAT")
```

### `modelName` → model name

```
machines.modelName (ObjectId)
  → equipmentcategories.brands[].models[]._id
  → equipmentcategories.brands[].models[].name  (e.g. "3DX", "320D")
```

### `city` → city name

```
machines.city (ObjectId)
  → cities._id
  → cities.name

Fallback: machines.equipmentLocation (plain string, e.g. "Jaipur")
```

### `owner` → seller display

```
machines.owner (ObjectId)
  → users._id
  → users.name  (fallback when sellerName empty)
```

### `rating` → average review score

```
reviews.product (ObjectId) == machines._id
  → avg(reviews.rating)
```

---

## Specification Fields (Real DB → `specifications` object)

These optional machine fields are collected into `specifications` when non-empty:

| Spec key (normalized) | Real field |
|-----------------------|------------|
| `manufacturing_year` | `manufacturingYear` |
| `condition` | `equipmentCondition` |
| `fuel_type` | `fuelType` |
| `transmission` | `transmissionType` |
| `bucket_capacity` | `bucketCapacity` |
| `engine_power` | `enginePower` |
| `operating_weight` | `operatingWeight` |
| `lifting_capacity` | `liftingCapacity` |
| `max_digging_depth` | `maxDiggingDepth` |
| `working_hours` | `workingHours` |
| `drive_type` | `driveType` |
| `capacity` | `capacity` |
| `variant` | `variant` |
| `pincode` | `pincode` |

---

## Search Filter Mapping

| AI filter | Sample Mongo filter | Marketplace Mongo filter |
|-----------|---------------------|--------------------------|
| `category` | `{ category: { $regex: ... } }` | `{ equipmentCategory: { $in: [resolved ObjectIds] } }` |
| `city` | `{ city: { $regex: ... } }` | `{ $or: [ { equipmentLocation: regex }, { city: { $in: cityIds } } ] }` |
| `max_price` | `{ price_per_day: { $lte: N } }` | `{ rentalPrice: { $lte: N } }` |
| active only | — | `{ status: "active", visibility: "public" }` |

---

## Category Canonical Mapping (Marketplace → AI)

Real marketplace categories use UPPERCASE labels (70 types). The AI uses lowercase canonical categories:

| Canonical (AI) | Marketplace category patterns |
|----------------|------------------------------|
| `excavator` | EXCAVATOR, HYDRAULIC EXCAVATOR, POCLAIN |
| `backhoe loader` | BACKHOE, JCB, LOADER BACKHOE |
| `hydra crane` | HYDRA CRANE, HYDRA |
| `crane` | CRANE, MOBILE CRANE, TOWER CRANE |
| `bulldozer` | BULLDOZER, DOZER |
| `road roller` | ROLLER, COMPACTOR, PAVER |
| `dump truck` | DUMP, TIPPER, TRUCK |
| `concrete mixer` | MIXER, CONCRETE |
| `motor grader` | GRADER |
| `wheel loader` | WHEEL LOADER, FRONT LOADER |

Unmapped categories keep their lowercase marketplace name as `category`.

---

## Schema Detection

The data access layer auto-detects schema per document:

- **Seed schema:** has `price_per_day` + string `category`, no `equipmentCategory`
- **Marketplace schema:** has `equipmentCategory` or `rentalPrice`

Both schemas are normalized to the same output shape before reaching AI services or the frontend.

---

## Files Implementing This Mapping

| File | Role |
|------|------|
| `app/utils/machine_mapper.py` | Single-document normalization |
| `app/utils/reference_cache.py` | ObjectId resolution caches |
| `app/utils/machine_repository.py` | Centralized queries + normalization |
| `app/ai/category_mapping.py` | `marketplace_category_to_canonical()` |
| `scripts/import_marketplace_dump.py` | Restore BSON dump |
| `scripts/generate_marketplace_embeddings.py` | Add embeddings for semantic search |
