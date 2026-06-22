# AI Feature Flags (.env)

Local-first defaults (best performance, lowest API cost):

```env
# Optional — all default to false except warm-up
USE_GROQ_TEXT_UNDERSTANDING=false
USE_GROQ_ADVISOR=false
USE_GROQ_RAG_ANSWER=false
USE_OPENAI_INTENT_PARSER=false
WARMUP_EMBEDDING_ON_STARTUP=true
```

| Flag | Default | Effect |
|------|---------|--------|
| `WARMUP_EMBEDDING_ON_STARTUP` | **true** | Loads SentenceTransformer in background after server start — first search is fast, startup stays ~1–2s |
| `USE_GROQ_TEXT_UNDERSTANDING` | false | `/chat` debug understanding uses rules only |
| `USE_GROQ_ADVISOR` | false | Advisor uses price/availability/rating ranking, no Groq |
| `USE_GROQ_RAG_ANSWER` | false | RAG returns grounded extractive text from PDF chunks |
| `USE_OPENAI_INTENT_PARSER` | false | Never calls OpenAI for intent; rules parser only |

**Groq still used for:** `POST /voice/*` (Whisper transcription).

**TensorFlow:** loads only on first image classify (unchanged).

Enable flags only for edge cases (very ambiguous Hindi, long multi-machine advisor prose, polished RAG paraphrase).
