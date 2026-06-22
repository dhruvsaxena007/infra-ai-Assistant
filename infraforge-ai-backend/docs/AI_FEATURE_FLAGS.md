# AI Feature Flags (.env)

Local-first defaults (best performance, lowest API cost):

```env
AI_PROVIDER=groq
ENABLE_OPENAI=false
OPENAI_API_KEY=

USE_GROQ_TEXT_UNDERSTANDING=false
USE_GROQ_ADVISOR=false
USE_GROQ_RAG_ANSWER=false
USE_GROQ_INTENT_CLASSIFIER=false
USE_OPENAI_INTENT_PARSER=false
WARMUP_EMBEDDING_ON_STARTUP=true
```

| Flag | Default | Effect |
|------|---------|--------|
| `AI_PROVIDER` | **groq** | Primary AI backend (`groq` or `openai` when enabled) |
| `ENABLE_OPENAI` | **false** | Master switch — no OpenAI calls when false |
| `WARMUP_EMBEDDING_ON_STARTUP` | **true** | Loads SentenceTransformer in background after server start |
| `USE_GROQ_TEXT_UNDERSTANDING` | false | `/chat` debug understanding uses rules only |
| `USE_GROQ_ADVISOR` | false | Advisor uses price/availability/rating ranking, no Groq |
| `USE_GROQ_RAG_ANSWER` | false | RAG returns grounded extractive text from PDF chunks |
| `USE_GROQ_INTENT_CLASSIFIER` | false | Intent router uses rules only (no Groq fallback) |
| `USE_OPENAI_INTENT_PARSER` | false | Requires `ENABLE_OPENAI=true` + `AI_PROVIDER=openai` |

**Groq still used for:** `POST /voice/*` (Whisper transcription) when `GROQ_API_KEY` is set.

**OpenAI later:** see `docs/OPENAI_ENABLEMENT.md`.

**Central router:** `app/ai/assistant_intent_router.py` → `classify_assistant_intent()`

**Provider facade:** `app/ai/ai_provider.py`
