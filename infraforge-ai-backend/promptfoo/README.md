# InfraForge Assistant — Promptfoo Evaluation

Automated regression testing for **189 prompts** covering greetings, search, spell correction, Hindi/Hinglish, context memory, off-topic blocking, and project recommendations.

## Quick start (no Node.js required)

```powershell
cd infraforge-ai-backend
.\.venv\Scripts\activate

# 1. Generate / refresh test cases
python scripts/generate_eval_cases.py

# 2. Run full eval + HTML report
python scripts/run_assistant_eval.py
```

**Reports:**

| File | What it shows |
|------|----------------|
| **`response_analysis.html`** | **← YEH KHOLO** — har query ka **poora actual output** + RELEVANT/PARTIAL/WRONG verdict |
| `quality_report.html` | Same as response_analysis (alias) |
| `quality_report.csv` | Excel — query, output, verdict, logical?, analysis |
| `quality_report.json` | Full JSON |
| `eval_report.html` | Redirects to response_analysis.html |

```powershell
# With Groq semantic judge (optional, needs GROQ_API_KEY in .env)
python scripts/run_assistant_eval.py --judge

# Quick test on 20 queries
python scripts/run_assistant_eval.py --limit 20
```

### Quality score dimensions (0–100 each)

| Dimension | Meaning |
|-----------|---------|
| **intent_match** | Did backend pick right category/city/mode? |
| **response_relevance** | Does reply text mention what user asked? |
| **language_match** | Hindi/Hinglish/English alignment |
| **result_quality** | Right machines / clarification / no wrong results |
| **helpfulness** | Clear, actionable, not too short |
| **overall** | Weighted average — **focus on rows &lt; 75** |

## Promptfoo CLI (optional UI)

```powershell
cd infraforge-ai-backend\promptfoo
npm install
npm run eval          # uses promptfoo eval
npm run view          # open promptfoo web UI
```

Or from backend root:

```powershell
npx promptfoo eval -c promptfoo/promptfoo.yaml
npx promptfoo view
```

## Test case categories (189 total)

| Category | Count | Examples |
|----------|-------|----------|
| Greetings | 12 | `hi`, `hii`, `namaste` |
| Basic search | 55 | `excavator in delhi`, `JCB in Jaipur` |
| Spell correction | 28 | `excvator in jaipir`, `nodia` |
| Hindi / Hinglish | 25 | `mujhe jaipur me excavator chahiye` |
| Clarification | 15 | `jaipur`, `road roller chaiye` |
| Off-topic | 12 | `bitcoin price today`, weather |
| Budget / edge | 12 | free budget, list all |
| Multi-turn context | 25 | `same in delhi`, project → city |
| Project recommendation | 5 | `road project ke liye...` |

## Adding new tests

Edit `scripts/generate_eval_cases.py`, then regenerate:

```powershell
python scripts/generate_eval_cases.py
```

Single-turn assertion fields in `expect`:
- `category`, `city`, `assistant_mode`, `not_assistant_mode`
- `reply_language` or `reply_language_in: ["english", "hinglish"]`
- `machines_max`, `machines_min`, `has_corrections`, `message_contains`

## CI integration

```powershell
python scripts/run_assistant_eval.py
# exit code 0 = all passed, 1 = failures
```
