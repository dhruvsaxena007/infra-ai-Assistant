# InfraForge AI Assistant — Demo Script

Best showcase flow for stakeholders. Run backend + frontend locally first (`docs/PRODUCTION_READINESS.md`).

---

## 1. Greeting demo

**Say:** `Hi`

**Expect:** Warm welcome, chips: Search Machine, Upload Image, Ask About Rental, Upload Document.

**Tip:** Click **Search Machine** to jump into search.

---

## 2. Search demo

**Say:** `excavator in Jaipur under 8000`

**Expect:** Machine cards, advisor note, chips: Show cheaper options, Show rent only, Contact owner.

**Follow-up:** `what about Delhi?` (after a prior search with category)

**Expect:** Same category refined to Delhi — conversational continuity.

---

## 3. Smart clarification demo

**Say:** `road roller chahiye`

**Expect:** "Sure — Road Roller… Which city?" (not generic "provide details").

**Say:** `Delhi me machine chahiye`

**Expect:** "Delhi me kaunsi machine chahiye?"

---

## 4. Recommendation demo

**Say:** `road project ke liye machine chahiye`

**Expect:** Project-type clarification (Highway, Urban road, Earthwork…).

**Say:** `Highway`

**Expect:** Explanation why Motor Grader, Road Roller, Excavator fit + matching listings.

---

## 5. Image demo

**Action:** Upload a clear excavator/crane photo.

**Expect:** Detected type or safe clarification — never fake search on non-machine images.

**Follow-up:** `is this available in Jaipur?`

**Expect:** Search uses image context (excavator + Jaipur).

---

## 6. Voice demo

**Action:** Voice button → "Jaipur me excavator chahiye"

**Expect:** Same pipeline as text; response includes `voice_input` metadata.

---

## 7. Document demo

**Action:** Upload PDF/text via document chip, then ask: `What machines are needed for highway project?`

**Expect:** Answer from document, panel clears machine cards, `rag_scope: session`.

---

## 8. Refund demo

**Say:** `refund chahiye`

**Expect:** Guided support message, handover card (Call / WhatsApp / Raise Request), no machine search.

---

## 9. Payment demo

**Say:** `payment failed`

**Expect:** Payment guidance + handover, no machine panel.

---

## 10. Delivery demo

**Say:** `how is transport calculated for machine delivery`

**Expect:** Deterministic marketplace knowledge — no hallucinated prices.

---

## Marketplace knowledge quick prompts

| Prompt | Topic |
|--------|--------|
| How to rent a machine? | Rent process |
| How to buy? | Buy process |
| How does InfraForge work? | Platform overview |
| What is security deposit? | Deposit policy |
| What documents are required? | Documents |
| How to contact owner? | Contact owner |

---

## Empty-result demo

**Say:** `crawler drill in Jaipur` (if no exact stock)

**Expect:** Nearby cities + similar categories suggested — not a dead-end.

---

## Regression before demo

```bash
python scripts/run_phase_e_tests.py
python scripts/run_phase_d_tests.py
python scripts/run_phase_c_tests.py
python scripts/run_phase_ab_tests.py
```

All should pass.
