# Backend Optimization Roadmap — InfraForge AI Marketplace Assistant

## NOW (implemented)

- [x] Remove LangChain → lightweight in-memory chat memory
- [x] Remove scikit-learn → NumPy `vector_math`
- [x] Single SentenceTransformer via `embedding_service` (lazy singleton)
- [x] **Background embedding warm-up** on startup (`WARMUP_EMBEDDING_ON_STARTUP=true` default)
- [x] Lazy-load TensorFlow / MobileNet on first image request
- [x] Rules-first parsing (`query_parser`, `category_mapping`)
- [x] OpenAI `extract_intent` **off by default** (`USE_OPENAI_INTENT_PARSER=false`)
- [x] Groq text understanding **off by default** (`USE_GROQ_TEXT_UNDERSTANDING=false`)
- [x] Groq advisor **off by default** — deterministic ranking (`USE_GROQ_ADVISOR=false`)
- [x] RAG answers **extractive by default** — no Groq (`USE_GROQ_RAG_ANSWER=false`)
- [x] Voice uses rules understanding (Whisper only from Groq)
- [x] RAG top-K + shared embeddings
- [x] Image confidence threshold
- [x] Category synonyms (crawler drill, JCB/backhoe, EPIROC models)
- [x] `insight_helpers` for price peer averaging
- [x] Rating null → neutral score in recommendations
- [x] `/health` reports AI mode and feature flags

## NEXT (approval required)

- [ ] YOLOv8n / YOLOv11n image classifier — see `IMAGE_MODEL_ROADMAP.md`
- [ ] ONNX runtime for lighter inference
- [ ] MongoDB Atlas Vector Search for machines + RAG
- [ ] Mongo-backed session memory (replace in-process dict)
- [ ] Mongo-backed RAG chunk store
- [ ] Redis session/cache layer
- [ ] Analytics dashboard (persistent)
- [ ] Model performance monitoring (latency, confidence histograms)

## LATER

- [ ] Custom YOLO training on InfraForge listing images
- [ ] Learning-to-rank from search clicks
- [ ] Personalization per user/session
- [ ] Production deployment tuning (workers, GPU node for image only)

## Architecture target (local-first)

```text
TEXT:   Rules → category/city/brand → OpenAI only if ambiguous
VOICE:  Whisper → normalize → rules → chatbot
IMAGE:  Lazy MobileNet → confidence → search → clarify if low
SEARCH: Mongo filters → embeddings → hybrid rank → exact vs alternatives
RAG:    PDF → local embeddings → top-K → Groq grounded answer
```

## Rollback

- Restore `requirements.txt` with `langchain`, `langchain-core`, `scikit-learn`
- Restore previous `memory.py`, `rag_service.py`, `embedding_service.py` from git
- Set `USE_GROQ_TEXT_UNDERSTANDING=true` if you relied on Groq parsing for edge cases
