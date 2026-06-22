# Backend Optimization — Before vs After

## 1. Dependencies

| Package | Before | After |
|---------|--------|-------|
| langchain + langchain-core | Required | **Removed** |
| scikit-learn (direct import) | Used in `rag_service` | **Removed from app code** (may remain as ST transitive dep) |
| sentence-transformers | Yes (×2 loads) | Yes (**×1** singleton) |
| tensorflow | Yes (eager at import) | Yes (**lazy** on first image call) |
| numpy, fastapi, groq, opencv, pypdf | Yes | Yes |

**Approx. package reduction:** ~50–120 MB installed size if you `pip uninstall langchain langchain-core scikit-learn` from the venv (orphan packages may remain until uninstalled).

## 2. Startup behavior

| Metric | Before | After (measured) |
|--------|--------|------------------|
| `from app.main import app` | Often 15–45s+ (TF + 2× ST) | **~1.5s**, `tensorflow` not in `sys.modules` |
| First `/image-search` | Same as startup | **+10–30s** one-time TF/MobileNet download/load |
| First embedding call | At import | **~2–5s** one-time ST load |

## 3. Heavy imports at startup

| Library | Before | After |
|---------|--------|-------|
| TensorFlow | Loaded via `machines` router import chain | **Not loaded** until classify |
| SentenceTransformer | 2 instances possible | **1** shared |
| LangChain | Loaded with chatbot | **None** |

## 4. Search accuracy

| Query | Before (typical) | After (tested) |
|-------|------------------|----------------|
| crawler drill in jaipur | Variable | **EPIROC AIR ROC D-35** in Jaipur |
| EPIROC AIR ROC D-35 | Variable | **Exact model** first |
| machine in jaipur under 500 | Variable | **4** listings ≤ ₹500/day |
| jcb vs excavator | Rules existed | **Strengthened** synonyms (unchanged strict chat path) |

## 5. Image search flow

| Step | Before | After |
|------|--------|-------|
| Model load | Server start | **First image request** |
| Low confidence | Still searched | **Clarification error** if top &lt; 0.35 |
| Wrong category | Possible | Same MobileNet limits; roadmap for YOLO |

## 6. Voice flow

| Step | Before | After |
|------|--------|-------|
| Whisper | Groq | Groq (unchanged) |
| Understanding | Groq every `/voice/chat` | **Rules** (`understand_user_text_rules`) |
| Search | `normalized_text` → chatbot | Same |

## 7. RAG flow

| Step | Before | After |
|------|--------|-------|
| Embeddings | Separate ST in `rag_service` | **Shared** `embedding_service` |
| Similarity | sklearn | **NumPy** `vector_math` |
| Retrieval | Top-1 chunk | **Top-3** chunks |
| Groq answer | Yes | Yes (grounded) |

## 8. Memory system

| Aspect | Before | After |
|--------|--------|-------|
| Implementation | LangChain `ConversationBufferMemory` | **Plain dict** per session |
| Public API | Same functions | **Unchanged** |
| Persistence | In-memory | In-memory (Mongo roadmap) |

## 9. Groq / OpenAI calls

| Path | Before | After |
|------|--------|-------|
| POST /chat text understanding | Groq every request | **Rules** (Groq optional via env) |
| Voice enhanced query | Groq | **Rules** |
| Chatbot filter extract | OpenAI if key set, often | **Only if rules empty** |
| AI search filters | OpenAI first | **Rules first** |
| Advisor | Groq | Groq (unchanged; has deterministic fallback) |
| RAG answer | Groq | Groq |

## 10. Code complexity

- **Removed:** LangChain abstraction, duplicate ST, sklearn in RAG
- **Added:** `vector_math.py`, `rules_understanding.py`, `insight_helpers.py`, lazy loaders
- **Net:** Slightly more files, **less** third-party magic, easier debugging

## 11. Risk

| Risk | Level | Mitigation |
|------|-------|------------|
| Breaking API envelope | Low | Same `success_response` shape |
| Breaking frontend fields | Low | Normalizer unchanged |
| Worse Hindi edge cases | Medium | Set `USE_GROQ_TEXT_UNDERSTANDING=true` |
| First image request slow | Low | Documented; expected |
| pip check orphans | Low | Uninstall old langchain packages from venv |

## 12. Features preserved

All endpoints retained: `/health`, `/chat`, `/voice/*`, `/image-search`, `/rag/*`, `/machines/*`, insights, compare, recommendations, advisor, analytics.

## 13. Features improved

- Faster API cold start without TensorFlow
- Lower RAM (one embedding model)
- Fewer LLM calls on chat/voice
- RAG top-K + no sklearn
- Image low-confidence guard
- Crawler drill / EPIROC model synonyms
- Neutral rating in recommendations
