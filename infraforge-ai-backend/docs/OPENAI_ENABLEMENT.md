# OpenAI Enablement (Final Polish Only)

**Default:** OpenAI is disabled. No credits are spent during development.

```env
AI_PROVIDER=groq
ENABLE_OPENAI=false
OPENAI_API_KEY=
USE_OPENAI_INTENT_PARSER=false
```

## When to enable (after stabilization tests pass)

1. Set in `.env`:

```env
AI_PROVIDER=openai
ENABLE_OPENAI=true
OPENAI_API_KEY=sk-your-company-key
USE_OPENAI_INTENT_PARSER=true   # optional — ambiguous Hindi intent
```

2. Optional polish flags:

```env
USE_GROQ_ADVISOR=true           # or keep rules advisor (free)
USE_GROQ_RAG_ANSWER=true        # polished RAG paraphrase
USE_GROQ_TEXT_UNDERSTANDING=true
```

3. Restart backend:

```powershell
python -m uvicorn app.main:app --reload
```

4. Verify `/health`:

```json
"openai_enabled": true,
"provider": "openai"
```

## What OpenAI can be used for (later)

| Feature | Flag | Default |
|---------|------|---------|
| Search filter extraction | `USE_OPENAI_INTENT_PARSER` | off |
| Intent polish | `AI_PROVIDER=openai` + router | off |
| Vision image understanding | `ai_provider.analyze_image` | blocked until enabled |
| RAG answer polish | prefer Groq flag first | off |

## Safety gates

- `app/ai/openai_parser.py` — lazy-imports OpenAI; returns empty intent when disabled
- `app/ai/ai_provider.py` — returns `"OpenAI provider disabled"` if called when off
- `settings.openai_usable` — requires `ENABLE_OPENAI=true`, `AI_PROVIDER=openai`, and key

## Rollback

Set `ENABLE_OPENAI=false` and restart — instant return to Groq/local-only mode.
