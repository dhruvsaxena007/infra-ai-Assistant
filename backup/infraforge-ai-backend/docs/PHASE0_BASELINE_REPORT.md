# Phase 0 — Backend Baseline Report (InfraForge AI Backend)

**Project path:** `infraforge-ai-backend`  
**Audit date:** 2026-06-04  
**Status:** Pre-optimization snapshot (no code changes in this document)

---

## 1. Folder structure (backend)

```
infraforge-ai-backend/
├── app/
│   ├── main.py                 # FastAPI app, CORS, routers
│   ├── api/routes/             # health, machines, chatbot, voice, image_search, rag, assistant
│   ├── ai/                     # search, RAG, embeddings, image ML, insights, voice
│   ├── chatbot/                # chatbot_service, memory (LangChain), image_context_memory
│   ├── core/                   # config, groq_client
│   ├── database/               # mongodb (Motor)
│   ├── analytics/              # search_logger
│   ├── models/                 # pydantic MachineModel
│   └── utils/                  # normalizer, repository, sanitize, response
├── scripts/                    # seed, import, validation, embeddings
├── docs/                       # testing checklists, field mapping
├── requirements.txt
└── uploads/                    # audio, image_search, rag_pdfs
```

---

## 2. Tech stack (current)

| Layer | Technology |
|-------|------------|
| API | FastAPI + Uvicorn |
| DB | MongoDB via Motor + PyMongo |
| LLM (primary) | Groq (`llama-3.3-70b-versatile`, Whisper) |
| LLM (optional) | OpenAI (`gpt-4o-mini`) for `extract_intent` |
| Embeddings | SentenceTransformer `all-MiniLM-L6-v2` |
| Image | TensorFlow/Keras MobileNetV2 (ImageNet), OpenCV |
| RAG | pypdf + in-memory chunks |
| Memory | LangChain `ConversationBufferMemory` (in-process) |
| Similarity | NumPy (search_service) + **scikit-learn** (rag_service only) |

---

## 3. AI features (current)

- **Text chat** (`POST /chat`) — Groq text understanding + chatbot (rules + OpenAI intent + hybrid search)
- **Voice** (`POST /voice/chat`, `/voice/transcribe`) — Groq Whisper + normalization + Groq understanding + chatbot
- **Image search** (`POST /image-search`) — MobileNet classify → category intent → intelligent search
- **Image context** — session image context for follow-up chat
- **AI search** (`GET /machines/ai-search`) — hybrid Mongo + embeddings + Groq/OpenAI filters
- **Semantic search** (`GET /machines/semantic-search`)
- **Recommendations** (`GET /machines/{id}/recommendations`)
- **RAG** (`POST /rag/upload-text`, PDF upload, `POST /rag/ask`)
- **Price insight / deal score / compare** — rule-based on normalized machines
- **AI advisor** — Groq with deterministic fallback
- **Search analytics** — Mongo `search_logs`
- **Real data** — `machine_repository` + `machine_normalizer` for InfraForge marketplace schema

---

## 4. Dependencies (`requirements.txt`)

**Kept (required):** fastapi, uvicorn, python-multipart, motor, pymongo, python-dotenv, pydantic, groq, openai, sentence-transformers, numpy, opencv-python, tensorflow, pypdf

**Candidates for removal (after refactor):**
- `langchain`, `langchain-core` — only `app/chatbot/memory.py`
- `scikit-learn` — only `app/ai/rag_service.py` (`cosine_similarity`)

---

## 5. Heavy libraries & startup risks

| Library | Load behavior (baseline) | Risk |
|---------|-------------------------|------|
| SentenceTransformer | **Twice** — `embedding_service.py` + `rag_service.py` at import | High RAM, slow cold start |
| TensorFlow/MobileNetV2 | **Eager** — `image_classification_service.py` module import | Very slow startup, large RAM |
| LangChain | Imported with chatbot memory module | Extra deps, not essential |
| scikit-learn | RAG only | Avoidable via NumPy |
| OpenCV | On demand (image quality/hash) | Moderate |
| Groq client | Single client at import | Low |

**Import chain at startup:** `main.py` → all routers → `machines.py` imports `image_classification_service` → **TensorFlow loads even for `/health`**.

---

## 6. Duplicated logic

1. **SentenceTransformer** — duplicate model in `embedding_service.py` and `rag_service.py`
2. **Cosine similarity** — `search_service.cosine_similarity` (NumPy) vs `sklearn.metrics.pairwise.cosine_similarity` in RAG
3. **Intent extraction** — `query_parser` / `category_mapping` (rules) vs `openai_parser.extract_intent` vs `text_understanding_service` (Groq) — triple path
4. **Filter merge** — `intelligent_search._get_search_filters` prefers LLM before manual merge

---

## 7. Groq / OpenAI call hotspots (baseline)

| Call site | When |
|-----------|------|
| `text_understanding_service.understand_user_text` | Every `POST /chat` and voice `build_enhanced_query` |
| `openai_parser.extract_intent` | Chatbot `_extract_new_filters`, `intelligent_search._get_search_filters` (if API key set) |
| `advisor_service.generate_machine_advice` | Every successful chat search with results |
| `rag_service.generate_answer_from_context` | Every RAG question |
| `voice_service.transcribe_audio` | Voice endpoints |

---

## 8. Runtime risks

- Wrong category if semantic search overrides strict category (mitigated in chatbot for explicit category)
- Rating `null` treated as `2.5` in **recommendation_service** (should use neutral helper)
- Image "loader" label may map to backhoe — acceptable; low confidence not gated
- RAG single-chunk retrieval — weak grounding on long PDFs
- In-memory RAG + session memory — lost on restart (documented as future work)

---

## 9. API contract (preserved)

Standard envelope via `success_response` / `error_response`:

```json
{ "success": true, "message": "...", "data": {}, "error": null }
```

Normalized machine fields include: `id`, `name`, `category_display`, `city`, `price_per_day`, `listing_type`, `brand`, `model`, `specifications`, `rating`, etc.

---

## 10. Optimization plan (Phases 1–11)

See `docs/BACKEND_OPTIMIZATION_ROADMAP.md` (created in Phase 11).

**Immediate low-risk targets:** custom memory, remove sklearn, single embedding service, lazy TensorFlow, rules-first parsing, reduce redundant Groq on chat/voice, strengthen category synonyms, RAG top-k + shared embeddings, insight helpers, roadmap docs.
