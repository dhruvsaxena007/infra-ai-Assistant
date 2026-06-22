# InfraForge Real Data Migration — Test Checklist

Use this checklist after importing `marketplace_mongo_dump` and pointing `DATABASE_NAME` to the marketplace database.

---

## 1. Database & Import

- [ ] `marketplace_mongo_dump` restored successfully (`mongorestore`)
- [ ] `machines` collection has real listings (not seed data)
- [ ] `equipmentcategories` and `cities` collections present
- [ ] `python scripts/generate_marketplace_embeddings.py` completed without errors
- [ ] Sample machine document has `embedding` field after script run
- [ ] Backend `.env` `DATABASE_NAME` points to marketplace DB

---

## 2. API Validation

### Health
- [ ] `GET /health` returns `success: true`

### Machines list
- [ ] `GET /machines` returns normalized objects with `source: "infraforge_real_db"`
- [ ] Each machine has `name`, `city`, `price_per_day`, `images` or `image_url`
- [ ] No raw ObjectId strings in `category`, `brand`, `city` fields

### Search
- [ ] `GET /machines/ai-search?query=excavator in jaipur` returns relevant results
- [ ] `GET /machines/filter?category=excavator&city=jaipur` works
- [ ] No duplicate machines in search results (same `_id` or same name+city+price)

### Chat
- [ ] `POST /chat` with `"JCB in Jaipur"` returns backhoe loaders, NOT excavators
- [ ] `POST /chat` follow-up `"what about Delhi"` keeps JCB category from memory
- [ ] `POST /chat` with no match returns honest fallback message + alternatives labelled

### Voice
- [ ] `POST /voice/chat` Hindi/Hinglish query transcribed and searched correctly
- [ ] `"sasta excavator chahiye jaipur me"` returns excavators in Jaipur

### Image
- [ ] `POST /image-search` with crane photo returns crane-related listings
- [ ] Response includes real Cloudinary image URLs

### Intelligence features
- [ ] `GET /price-insight/{id}` returns market comparison
- [ ] `GET /deal-score/{id}` returns deal score
- [ ] `GET /machines/{id}/recommendations` returns similar machines
- [ ] `GET /compare-machines?machine1_id=...&machine2_id=...` works

### RAG (unchanged)
- [ ] PDF upload + Q&A still works

---

## 3. Frontend Rendering

- [ ] Machine cards show real images (or graceful placeholder when missing)
- [ ] Prices display as ₹/day from `price_per_day`
- [ ] City, brand, seller name render correctly
- [ ] Availability badge shows for active listings
- [ ] Compare, Price Insight, Deal Score, Similar modals work with real IDs
- [ ] No console errors on machine card render

---

## 4. Memory Continuity Tests

### Text memory
- [ ] Turn 1: `"excavator in Jaipur"` → results in Jaipur
- [ ] Turn 2: `"show cheaper options"` → same category, lower budget
- [ ] Turn 3: `"instead of excavator, JCB"` → category switches to backhoe loader

### Image context memory (frontend + backend)
- [ ] Upload crane image → results shown
- [ ] Follow-up: `"Is this available in Jaipur?"` → searches crane in Jaipur
- [ ] Follow-up with explicit machine name is NOT overridden by image context

---

## 5. Multilingual Tests

| Query | Expected |
|-------|----------|
| `"mujhe jaipur me sasta jcb chahiye"` | Backhoe loaders in Jaipur, budget-aware |
| `"delhi me excavator dikhao"` | Excavators in Delhi |
| `"muft me machine"` | Honest "no free machines" + lowest priced alternatives |
| Urdu/Hinglish mixed voice query | Correct category, no random switching |

---

## 6. Edge Cases

- [ ] Machine with empty `description` does not crash API
- [ ] Machine with no `productImages` shows placeholder in UI
- [ ] Sell listing (`listingType: "sell"`) handled (price from `sellingPrice` if no rental)
- [ ] Missing reviews → rating shows as N/A, deal score still works
- [ ] Invalid machine ID returns clean error, not 500

---

## 7. Regression — Features Must Still Work

- [ ] Text AI chat
- [ ] Voice AI search
- [ ] Image search + classification
- [ ] Machine recommendations
- [ ] Deal score
- [ ] Price insights
- [ ] Advisor AI banner
- [ ] RAG PDF Q&A
- [ ] Session memory
- [ ] Search logging
- [ ] Image upload + camera
- [ ] Voice recording + upload
