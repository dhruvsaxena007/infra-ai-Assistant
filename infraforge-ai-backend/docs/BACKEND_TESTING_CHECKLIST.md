# InfraForge AI Backend — Testing Checklist

Use this checklist to verify the backend end-to-end in Swagger before frontend
integration. All endpoints return the standardized shape:

```json
{ "success": true, "message": "string", "data": {}, "error": null }
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Seed the test machine dataset (safe to re-run; upserts by name)
python scripts/seed_machines.py

# 3. Start the backend
uvicorn app.main:app --reload

# 4. Open Swagger
# http://127.0.0.1:8000/docs
```

---

## Tests

### 1. `GET /health`
Expected: `data.status = "healthy"`, `data.database = "connected"`.

### 2. `GET /assistant/capabilities`
Expected: list of active capabilities (including **Seed Machine Dataset**) and future scope.

### 3. `GET /machines`
Expected: `data.count = 30` (after seeding), `data.machines` list with **no `embedding`** field.

### 4. `GET /machines/ai-search?query=excavator in jaipur under 8000`
Expected: ranked `data.machines` (top 5), embeddings hidden.

### 5. `POST /understand-text`
```json
{ "message": "mujhe jaipur me sasta excavator chahiye" }
```
Expected: `data.machine_type = "excavator"`, `data.city = "jaipur"`, intent detected.

### 6. `POST /chat`
```json
{ "session_id": "test_user_1", "message": "excavator in jaipur under 8000" }
```
Expected: `data.machines`, `data.filters`, `data.context`, `data.input`.

### 7. `POST /chat` (memory — city switch)
```json
{ "session_id": "test_user_1", "message": "same in delhi" }
```
Expected: `data.context.used_previous_context = true`, city now `delhi`.

### 8. `POST /chat` (memory — cheaper)
```json
{ "session_id": "test_user_1", "message": "show cheaper options" }
```
Expected: inherited filters with reduced `max_price`.

### 9. `POST /voice/transcribe`
Upload an audio file. Expected: `data.text` contains the transcription.

### 10. `POST /voice/chat`
Form field `session_id = voice_test_1`, upload audio saying *"mujhe jaipur me excavator chahiye"*.
Expected: `data.voice_input`, plus `machines`, `filters`, `context`.

### 11. `POST /image-search`
Upload an excavator/crane/JCB image (jpg/jpeg/png/webp).
Expected: `data.match_type`, `data.detected_machine_type`, `data.results`.

### 12. `POST /rag/upload-text`
```json
{ "text": "JCB 3DX is a backhoe loader used for excavation, loading and road construction." }
```
Expected: `data.chunks_added`, `data.total_chunks`.

### 13. `POST /rag/ask`
```json
{ "question": "Which machine is used for excavation?" }
```
Expected: `data.answer`, `data.answer_source`, `data.similarity_score`.

### 14. `GET /compare-machines?machine1_id=<ID>&machine2_id=<ID>`
Use two real `_id` values from `GET /machines`. Expected: comparison result.

### 15. `GET /price-insight/{machine_id}`
Expected: price position (below / fair / above market).

### 16. `GET /deal-score/{machine_id}`
Expected: deal score out of 100.

### 17. `GET /machines/{machine_id}/recommendations`
Expected: list of similar machines (embeddings hidden).

### 18. MongoDB `search_logs`
After running `/chat`, check the `search_logs` collection. Each chat should add one document with:
`session_id, user_message, search_query, filters, result_count, fallback_used, fallback_query, created_at`.

---

## Error-shape checks (standardized errors)

- `POST /chat` with empty `session_id` → `success: false`, `message: "session_id is required"`.
- `POST /chat` with empty `message` → `success: false`, `message: "message is required"`.
- `POST /voice/chat` with empty `session_id` → `success: false`, `message: "session_id is required"`.
- `POST /image-search` with a `.txt` file → `success: false`, invalid image format.
