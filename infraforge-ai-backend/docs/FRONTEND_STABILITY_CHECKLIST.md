# Frontend Stability Checklist

Manual verification (no heavy test framework required).

## Machine panel

- [ ] Search response with machines → panel shows latest cards
- [ ] Refund/support/payment response → panel **cleared**
- [ ] Document Q&A response → panel **cleared**
- [ ] Image clarification → panel **cleared**
- [ ] Support mode after prior search → no stale cards

## Document flow

- [ ] Document chip appears above input after picker
- [ ] Upload + question sends with `session_id`
- [ ] Answer appears in chat thread as assistant message
- [ ] Image upload preview still works independently

## Voice

- [ ] Voice response includes transcript in user bubble
- [ ] Assistant response renders without crash
- [ ] `voice_input.normalized_text` / `input.enhanced_query` present in network tab

## Null safety

- [ ] Empty `machines` array → no panel crash
- [ ] Missing `sources` on document Q&A → no crash
- [ ] Missing `handover` on support → no crash
- [ ] Broken machine image URL → category placeholder, no broken icon

## Regression smoke

- [ ] `hi` → greeting, no search
- [ ] `refund chahiye` → support, panel clear
- [ ] `excavator in Jaipur` → search results
- [ ] Upload doc + question → document_qa answer
