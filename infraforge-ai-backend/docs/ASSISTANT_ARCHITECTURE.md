# Assistant Architecture

## API layer

| Route | Role |
|-------|------|
| `POST /chat` | Thin validation → `chatbot_service.chatbot_response()` |
| `POST /voice/chat` | Transcribe → normalize → same chat pipeline |
| `POST /image-search` | Image classify → safe search or clarification |
| `POST /rag/upload-*` | Document ingest (optional `session_id`) |
| `POST /rag/ask` | Document Q&A (optional `session_id`) |

## Central orchestrator: `assistant_router.py`

Single routing brain:

1. `message_normalizer` — input cleanup
2. `universal_turn_engine` — turn shape (conversational/compare/attribute/refine/defer)
3. `intent_classifier` — marketplace intent + `should_search_machines`
4. Route: greeting, document RAG, support, recommendation, machine search

Never searches for support/refund/payment/out-of-scope.

## Intent source: `intent_classifier.py`

- `SEARCH_INTENTS` / `NON_SEARCH_INTENTS` (canonical)
- `is_blocked_search_intent()` / `is_machine_search_intent()`

## Filter merge: `intent_resolver.py`

Search filter merge, follow-ups, clarification answers only. No support routing.

## Support copy: `support_response_service.py`

All refund/payment/order/delivery/platform responses. Imports `NON_SEARCH_INTENTS` from classifier.

## RAG: `rag_service.py`

- **Session scope**: chunks keyed by `session_id` when provided
- **Global legacy**: uploads without `session_id`
- `/chat` document questions prefer session docs; no cross-session leakage
- `rag_scope`: `session | global | none`

## Image search

`image_classifier.py` → YOLO → MobileNet → CLIP/OpenCV → clarification gate in `image_search.py`.

## Voice flow

```
/voice/chat → transcribe → message_normalizer → chatbot_response → assistant_router
```

Returns `voice_input` + `input` metadata parity with text chat.

## Frontend panel behavior

- Machine panel updates when response includes machines
- Cleared for support/refund/document/image_clarification modes
- See `docs/FRONTEND_STABILITY_CHECKLIST.md`

## Normalization pipeline

1. **message_normalizer** — structural, phrase, token fixes; optional Groq
2. **spell_correction** (in intent_resolver) — fuzzy category/city/brand for search parse only

Corrections exposed in `data.input.corrections` and `data.context.corrections`.
