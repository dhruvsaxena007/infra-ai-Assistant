# Production Readiness

## Run backend

```bash
cd infraforge-ai-backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
# Configure .env (see below)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run frontend

```bash
cd infraforge-ai-frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` if needed.

## Environment variables (defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AI_PROVIDER` | `groq` | Primary AI provider |
| `ENABLE_OPENAI` | `false` | OpenAI disabled |
| `GROQ_API_KEY` | — | Groq API (semantic fallback when enabled) |
| `USE_GROQ_UNIVERSAL_CLASSIFIER` | `auto` | Semantic turn classifier |
| `USE_GROQ_RAG_ANSWER` | `false` | RAG uses extractive/local answer |
| `USE_GROQ_ADVISOR` | `false` | Rules advisor only |
| `DISABLE_GROQ_SEMANTIC` | `false` | Force rules-only universal classifier |
| `GROQ_TIMEOUT_SECONDS` | `20` | Groq call timeout |
| `IMAGE_CLASSIFIER` | `auto` | Image pipeline mode |
| `YOLO_MODEL_PATH` | `models/.../best.pt` | Optional YOLO weights |
| `MONGODB_URL` | — | MongoDB connection |

## Groq/local default mode

- Rules-first for intent, normalization, advisor, RAG answers
- Groq semantic layer optional (`auto` when key present)
- On Groq failure/rate limit: rules fallback, `context.ai_fallback_used=true` when applicable

## OpenAI disabled mode

Keep `ENABLE_OPENAI=false` and `AI_PROVIDER=groq`. OpenAI intent parser off: `USE_OPENAI_INTENT_PARSER=false`.

## Enable OpenAI later

See `docs/OPENAI_ENABLEMENT.md`. Requires explicit `ENABLE_OPENAI=true`, `AI_PROVIDER=openai`, and `OPENAI_API_KEY`.

## YOLO later

See `docs/IMAGE_MODEL_UPGRADE.md`. Training not required for production safe mode.

## Test suites

```bash
python scripts/run_phase_ab_tests.py   # 14 core routing tests
python scripts/run_phase_c_tests.py    # 9 experience tests
python scripts/run_phase_d_tests.py    # 10 hardening tests
python scripts/run_stabilization_tests.py
python scripts/run_fuzz_paraphrase_tests.py
```

## Known limitations

- Session RAG is in-memory + Mongo; no document delete per session yet
- Groq daily token limits may trigger semantic fallback under heavy test load
- YOLO optional; CLIP/OpenCV safe mode always available
- Voice transcription requires local Whisper/Groq per `voice_service` config

## Rollback notes

- Remove `YOLO_MODEL_PATH` to disable YOLO
- Set `DISABLE_GROQ_SEMANTIC=true` for rules-only chat
- Phase A+B routing unchanged in assistant_router — revert individual commits if needed
