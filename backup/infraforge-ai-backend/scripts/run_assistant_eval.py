"""
Run assistant eval with STRUCTURAL checks + QUALITY scoring reports.

Structural: category/city/mode assertions (pass/fail)
Quality:    how well the actual reply text matches the query (0–100 scores)

Run:
    python scripts/generate_eval_cases.py
    python scripts/run_assistant_eval.py
    python scripts/run_assistant_eval.py --judge    # + Groq semantic scores (needs GROQ_API_KEY)

Reports:
    promptfoo/output/eval_report.json/html     — structural pass/fail
    promptfoo/output/quality_report.json/html  — detailed optimization report
    promptfoo/output/quality_report.csv        — spreadsheet for analysis
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import html as html_lib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.mongodb import database  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402
import importlib.util  # noqa: E402

def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_scorer = _load_module("assistant_quality_scorer", ROOT / "scripts" / "assistant_quality_scorer.py")
compute_quality_scores = _scorer.compute_quality_scores
groq_judge_available = _scorer.groq_judge_available
groq_judge_scores = _scorer.groq_judge_scores

_mod = _load_module("infraforge_chat", ROOT / "promptfoo" / "providers" / "infraforge_chat.py")
check_expect = _mod.check_expect

CASES_PATH = ROOT / "promptfoo" / "tests" / "cases.json"
OUT_DIR = ROOT / "promptfoo" / "output"


async def run_case(case: dict, *, use_judge: bool) -> dict:
    sid = case["session_id"]
    if case.get("clear_session"):
        clear_conversation(sid)

    turns_detail = []
    last_resp = {}
    failures = []
    query_for_score = case.get("message", "")
    expect_for_score = case.get("expect", {})

    if "turns" in case:
        for i, t in enumerate(case["turns"]):
            last_resp = await chatbot_response(sid, t["message"], database)
            turns_detail.append({
                "turn": i + 1,
                "query": t["message"],
                "reply": _mod._msg(last_resp) if hasattr(_mod, "_msg") else (last_resp.get("message") or ""),
            })
            expect = t.get("expect")
            if expect:
                ok, fails = check_expect(last_resp, expect)
                if not ok:
                    failures.extend([f"turn {i+1}: {f}" for f in fails])
                expect_for_score = expect
            query_for_score = t["message"]
    else:
        last_resp = await chatbot_response(sid, case["message"], database)
        expect_for_score = case.get("expect", {})
        ok, failures = check_expect(last_resp, expect_for_score)
        failures = failures if not ok else []

    structural_pass = len(failures) == 0
    quality = compute_quality_scores(
        query_for_score,
        last_resp,
        expect_for_score,
        structural_pass=structural_pass,
        case=case,
    )

    judge = None
    if use_judge:
        judge = await groq_judge_scores(
            query_for_score,
            quality["reply"],
            quality["meta"],
        )

    return {
        "id": case["id"],
        "category": case["id"].split("_")[0],
        "pass": structural_pass,
        "failures": failures,
        "query": query_for_score,
        "all_turns": turns_detail or None,
        "reply": quality["reply"],
        "mode": quality["meta"].get("assistant_mode", ""),
        "category_detected": quality["meta"].get("category", ""),
        "city": quality["meta"].get("city", ""),
        "machines_count": quality["meta"].get("machines_count", 0),
        "machine_names": quality["meta"].get("machine_names", []),
        "suggestions": quality["meta"].get("suggestions", []),
        "reply_language": quality["meta"].get("reply_language", ""),
        "scores": quality["scores"],
        "overall_quality": quality["overall"],
        "issues": quality["issues"],
        "optimize": quality["optimize"],
        "optimization_hints": quality["optimization_hints"],
        "expected_behavior": quality["expected_behavior"],
        "verdict": quality["verdict"],
        "logical": quality["logical"],
        "verdict_summary": quality["verdict_summary"],
        "analysis": quality["analysis"],
        "llm_judge": judge,
    }


def _bar(score: int, width: int = 120) -> str:
    fill = int(width * score / 100)
    color = "#34d399" if score >= 80 else "#fbbf24" if score >= 65 else "#f87171"
    return (
        f'<div style="background:#2a2a35;border-radius:4px;height:8px;width:{width}px">'
        f'<div style="background:{color};height:8px;width:{fill}px;border-radius:4px"></div></div>'
    )


def _verdict_color(v: str) -> str:
    return {
        "RELEVANT": "#34d399",
        "PARTIAL": "#fbbf24",
        "NEEDS_FIX": "#f87171",
        "WRONG": "#ef4444",
    }.get(v, "#94a3b8")


def _response_analysis_html(results: list[dict], summary: dict) -> str:
    """Primary report: QUERY → ACTUAL OUTPUT → relevant? logical?"""
    esc = html_lib.escape

    rows = []
    for i, r in enumerate(results, 1):
        vc = _verdict_color(r["verdict"])
        machines = ""
        if r["machines_count"]:
            names = ", ".join(r.get("machine_names") or [])
            machines = f"{r['machines_count']} found" + (f": {names}" if names else "")
        else:
            machines = "—"

        fix_row = "background:#2a1515" if r["verdict"] in ("WRONG", "NEEDS_FIX") else (
            "background:#1a2218" if r["verdict"] == "RELEVANT" else "background:#221f14"
        )
        hints = " · ".join(r.get("optimization_hints") or [])

        rows.append(f"""
        <tr style="{fix_row}">
          <td>{i}</td>
          <td class="query">{esc(r['query'])}</td>
          <td class="expected">{esc(r.get('expected_behavior', ''))}</td>
          <td class="output">{esc(r['reply'])}</td>
          <td>{esc(machines)}</td>
          <td><span class="badge" style="background:{vc}">{esc(r['verdict'])}</span></td>
          <td>{'✓ Yes' if r['logical'] else '✗ No'}</td>
          <td class="analysis">{esc(r.get('analysis', ''))}</td>
          <td>{r['overall_quality']}%</td>
          <td class="fix">{esc(hints) if r['optimize'] else '—'}</td>
        </tr>""")

    wrong = [r for r in results if r["verdict"] in ("WRONG", "NEEDS_FIX")]
    partial = [r for r in results if r["verdict"] == "PARTIAL"]

    priority = ""
    for r in wrong + partial:
        priority += f"""
        <div class="priority-card">
          <div class="q"><b>Query:</b> {esc(r['query'])}</div>
          <div class="e"><b>Should:</b> {esc(r.get('expected_behavior',''))}</div>
          <div class="o"><b>Got:</b> {esc(r['reply'])}</div>
          <div class="v" style="color:{_verdict_color(r['verdict'])}"><b>{esc(r['verdict'])}</b> — {esc(r.get('verdict_summary',''))}</div>
          <div class="a">{esc(r.get('analysis',''))}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Response Analysis — InfraForge Assistant</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:Segoe UI,system-ui,sans-serif;margin:0;background:#0a0a0f;color:#e8e8ec}}
.header{{background:linear-gradient(135deg,#1a1030,#0f0f18);padding:24px 32px;border-bottom:1px solid #333}}
h1{{margin:0;color:#c4b5fd;font-size:22px}}
.sub{{color:#9ca3af;font-size:13px;margin-top:8px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}}
.stat{{background:#1a1a28;padding:12px 18px;border-radius:10px;border:1px solid #2d2d3d}}
.stat b{{display:block;font-size:22px;color:#fff}}
.stat span{{font-size:11px;color:#9ca3af}}
.note{{margin:20px 32px;padding:14px 18px;background:#1a1528;border-left:4px solid #a78bfa;border-radius:0 8px 8px 0;font-size:13px}}
.section{{padding:16px 32px}}
h2{{color:#a78bfa;font-size:16px;margin:24px 0 12px}}
.filter input{{width:100%;max-width:400px;padding:10px 14px;background:#1a1a22;border:1px solid #444;color:#fff;border-radius:8px;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#151520;padding:10px 8px;text-align:left;position:sticky;top:0;z-index:2;border-bottom:2px solid #a78bfa}}
td{{padding:10px 8px;border-bottom:1px solid #222;vertical-align:top}}
td.query{{font-weight:600;color:#f0f0ff;min-width:140px;max-width:180px}}
td.expected{{color:#a5b4fc;font-size:12px;max-width:200px}}
td.output{{background:#12121c;color:#e2e8f0;font-size:13px;min-width:320px;max-width:480px;white-space:pre-wrap;word-break:break-word;line-height:1.5;border-left:3px solid #6366f1;padding-left:12px}}
td.analysis{{font-size:12px;color:#94a3b8;max-width:200px}}
td.fix{{font-size:11px;color:#fbbf24}}
.badge{{padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;color:#000}}
.priority-card{{background:#1a1a22;border:1px solid #333;border-radius:10px;padding:14px;margin:10px 0}}
.priority-card .o{{background:#12121c;padding:10px;margin:8px 0;border-radius:6px;border-left:3px solid #6366f1;white-space:pre-wrap}}
.wrap{{overflow-x:auto}}
</style>
<script>
function filterRows(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('#main tbody tr').forEach(tr => {{
    tr.style.display = tr.innerText.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
function filterVerdict(v) {{
  document.querySelectorAll('#main tbody tr').forEach(tr => {{
    const badge = tr.querySelector('.badge');
    tr.style.display = (!v || (badge && badge.innerText === v)) ? '' : 'none';
  }});
}}
</script>
</head><body>
<div class="header">
  <h1>Response Analysis Report</h1>
  <div class="sub">Har query ka ACTUAL output + kya relevant/logical hai — {summary['generated_at'][:19]}</div>
  <div class="stats">
    <div class="stat"><b>{summary['total']}</b><span>queries tested</span></div>
    <div class="stat"><b style="color:#34d399">{summary.get('relevant_count',0)}</b><span>RELEVANT</span></div>
    <div class="stat"><b style="color:#fbbf24">{summary.get('partial_count',0)}</b><span>PARTIAL</span></div>
    <div class="stat"><b style="color:#f87171">{summary.get('fix_count',0)}</b><span>NEEDS FIX / WRONG</span></div>
    <div class="stat"><b>{summary['avg_quality']}%</b><span>avg match score</span></div>
  </div>
</div>

<div class="note">
  <b>Yeh report kya dikhati hai:</b> Pehle wali report sirf PASS/FAIL thi. 
  <b>Is report mein har row mein poora assistant reply dikhega</b> (OUTPUT column). 
  <b>VERDICT</b> = query ke liye response relevant hai ya nahi. 
  <b>LOGICAL</b> = backend ne sahi type ka jawab diya ya nahi. 
  <b>FIX column</b> = kahan optimize karna hai.
</div>

<div class="section">
  <h2>🔴 Priority — galat ya incomplete responses (optimize these first)</h2>
  {priority if priority else '<p style="color:#34d399">Sab responses relevant aur logical hain!</p>'}
</div>

<div class="section">
  <h2>📋 Full catalog — har query ka output</h2>
  <div class="filter">
    <input placeholder="Search query ya output text…" oninput="filterRows(this.value)">
    <button onclick="filterVerdict('')" style="margin-left:8px;padding:8px 12px;cursor:pointer">All</button>
    <button onclick="filterVerdict('RELEVANT')" style="padding:8px 12px;cursor:pointer;background:#34d399;border:none;border-radius:6px">Relevant</button>
    <button onclick="filterVerdict('PARTIAL')" style="padding:8px 12px;cursor:pointer;background:#fbbf24;border:none;border-radius:6px">Partial</button>
    <button onclick="filterVerdict('NEEDS_FIX')" style="padding:8px 12px;cursor:pointer;background:#f87171;border:none;border-radius:6px">Needs Fix</button>
    <button onclick="filterVerdict('WRONG')" style="padding:8px 12px;cursor:pointer;background:#ef4444;border:none;border-radius:6px;color:#fff">Wrong</button>
  </div>
  <div class="wrap">
  <table id="main">
    <thead><tr>
      <th>#</th>
      <th>USER QUERY</th>
      <th>WHAT SHOULD HAPPEN</th>
      <th>ACTUAL OUTPUT (poora reply)</th>
      <th>Machines</th>
      <th>VERDICT</th>
      <th>LOGICAL?</th>
      <th>ANALYSIS</th>
      <th>SCORE</th>
      <th>OPTIMIZE</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</div>
</body></html>"""


def _quality_html(results: list[dict], summary: dict) -> str:
    esc = html_lib.escape

    # Low-score section first
    low = [r for r in results if r["overall_quality"] < 75]
    low.sort(key=lambda x: x["overall_quality"])

    low_rows = []
    for r in low[:30]:
        hints = "<br>".join(esc(h) for h in r.get("optimization_hints", []))
        issues = "<br>".join(esc(i) for i in r.get("issues", []))
        judge = r.get("llm_judge") or {}
        judge_txt = ""
        if judge and not judge.get("error"):
            judge_txt = (
                f"<br><b>LLM judge:</b> {judge.get('overall', '?')}/100 — "
                f"{esc(judge.get('summary', ''))}<br><i>{esc(judge.get('improve', ''))}</i>"
            )
        low_rows.append(f"""
        <tr class="low">
          <td>{esc(r['id'])}</td>
          <td>{esc(r['query'][:100])}</td>
          <td class="reply">{esc(r['reply'][:500])}</td>
          <td>{r['overall_quality']}%</td>
          <td>{issues}</td>
          <td>{hints}{judge_txt}</td>
        </tr>""")

    all_rows = []
    for r in results:
        sc = r["scores"]
        judge = r.get("llm_judge") or {}
        llm_overall = judge.get("overall", "") if judge and not judge.get("error") else ""
        all_rows.append(f"""
        <tr class="{'low' if r['optimize'] else 'ok'}">
          <td>{esc(r['id'])}</td>
          <td>{esc(r['query'][:80])}</td>
          <td class="reply">{esc(r['reply'])}</td>
          <td>{esc(r['mode'])}</td>
          <td>{r['machines_count']}</td>
          <td>{sc['intent_match']}</td>
          <td>{sc['response_relevance']}</td>
          <td>{sc['language_match']}</td>
          <td>{sc['result_quality']}</td>
          <td>{sc['helpfulness']}</td>
          <td><b>{r['overall_quality']}</b></td>
          <td>{llm_overall}</td>
          <td>{'YES' if r['optimize'] else ''}</td>
        </tr>""")

    dim_avgs = summary.get("dimension_averages", {})
    dim_bars = "".join(
        f"<div style='margin:8px 0'><span style='display:inline-block;width:140px'>{k}</span>"
        f"{_bar(v)} <b>{v}%</b></div>"
        for k, v in dim_avgs.items()
    )

    cat_rows = ""
    for cat, avg in sorted(summary.get("avg_by_category", {}).items(), key=lambda x: x[1]):
        cat_rows += f"<tr><td>{esc(cat)}</td><td>{avg}%</td><td>{_bar(avg)}</td></tr>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>InfraForge Quality Report</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#0f0f12;color:#e8e8ec;line-height:1.5}}
h1,h2{{color:#a78bfa}} a{{color:#93c5fd}}
.summary{{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}}
.card{{background:#1a1a22;padding:16px 20px;border-radius:12px;min-width:120px;border:1px solid #2a2a35}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0}}
th,td{{border:1px solid #333;padding:8px;text-align:left;vertical-align:top}}
th{{background:#1a1a22;position:sticky;top:0}}
tr.low td{{background:#2a1a1a}} tr.ok td{{background:#12121a}}
td.reply{{max-width:420px;white-space:pre-wrap;word-break:break-word;font-size:11px;color:#c4c4d4}}
.filter{{margin:12px 0}} input{{padding:8px 12px;width:320px;background:#1a1a22;border:1px solid #444;color:#fff;border-radius:8px}}
.note{{background:#1a1a22;border-left:3px solid #a78bfa;padding:12px;margin:16px 0;font-size:13px}}
</style>
<script>
function filterTable(id, q) {{
  q = q.toLowerCase();
  document.querySelectorAll('#'+id+' tbody tr').forEach(tr => {{
    tr.style.display = tr.innerText.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</head><body>
<h1>InfraForge Assistant — Quality &amp; Optimization Report</h1>
<p>Generated: {summary['generated_at']} · {summary['total']} queries · {summary['duration_s']}s
 · LLM judge: {'enabled' if summary.get('judge_enabled') else 'off (use --judge + GROQ_API_KEY)'}</p>

<div class="note">
<b>How to use this report:</b> Structural pass/fail only checks backend logic.
<b>Quality scores (0–100)</b> show how well the <em>actual reply text</em> matches what the user asked.
Focus on rows marked <b>OPTIMIZE</b> or scores below 75 — those are where wording, language, or UX need improvement.
</div>

<div class="summary">
  <div class="card"><b>Avg quality</b><br><span style="font-size:28px">{summary['avg_quality']}%</span></div>
  <div class="card"><b>Need optimize</b><br><span style="font-size:28px">{summary['optimize_count']}</span></div>
  <div class="card"><b>Structural pass</b><br><span style="font-size:28px">{summary['pass_rate']}%</span></div>
  <div class="card"><b>Excellent (≥90)</b><br><span style="font-size:28px">{summary['excellent_count']}</span></div>
</div>

<h2>Score dimensions (average)</h2>
{dim_bars}
<p><small>intent_match · response_relevance · language_match · result_quality · helpfulness</small></p>

<h2>Average by test category</h2>
<table><tr><th>Category</th><th>Avg quality</th><th></th></tr>{cat_rows}</table>

<h2>Priority — lowest quality (optimize first)</h2>
<div class="filter"><input placeholder="Filter…" oninput="filterTable('low', this.value)"></div>
<table id="low"><tr>
  <th>ID</th><th>User query</th><th>Actual assistant reply</th><th>Score</th><th>Issues</th><th>How to improve</th>
</tr>{''.join(low_rows) if low_rows else '<tr><td colspan="6">All responses scored ≥ 75 — great!</td></tr>'}</table>

<h2>Full report — every query &amp; response</h2>
<div class="filter"><input placeholder="Search query or reply…" oninput="filterTable('all', this.value)"></div>
<table id="all"><tr>
  <th>ID</th><th>Query</th><th>Assistant reply</th><th>Mode</th><th>#Machines</th>
  <th>Intent</th><th>Relevance</th><th>Language</th><th>Results</th><th>Helpful</th>
  <th>Overall</th><th>LLM</th><th>Fix?</th>
</tr>{''.join(all_rows)}</table>
</body></html>"""


def _redirect_html(target: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={target}">
<title>Redirecting…</title></head>
<body style="font-family:system-ui;background:#0f0f12;color:#fff;padding:40px">
<p>Redirecting to <a href="{target}" style="color:#a78bfa">{target}</a> …</p>
<p><b>Us report mein har query ka ACTUAL OUTPUT dikhega.</b></p>
</body></html>"""


def _write_csv(results: list[dict], path: Path) -> None:
    fields = [
        "id", "query", "expected_behavior", "reply", "verdict", "logical",
        "verdict_summary", "analysis", "mode", "city", "category_detected",
        "machines_count", "reply_language",
        "intent_match", "response_relevance", "language_match",
        "result_quality", "helpfulness", "overall_quality",
        "llm_judge_overall", "optimize", "issues", "optimization_hints",
        "structural_pass",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            judge = r.get("llm_judge") or {}
            w.writerow({
                "id": r["id"],
                "query": r["query"],
                "expected_behavior": r.get("expected_behavior", ""),
                "reply": r["reply"],
                "verdict": r.get("verdict", ""),
                "logical": r.get("logical", ""),
                "verdict_summary": r.get("verdict_summary", ""),
                "analysis": r.get("analysis", ""),
                "mode": r["mode"],
                "city": r["city"],
                "category_detected": r["category_detected"],
                "machines_count": r["machines_count"],
                "reply_language": r["reply_language"],
                "intent_match": r["scores"]["intent_match"],
                "response_relevance": r["scores"]["response_relevance"],
                "language_match": r["scores"]["language_match"],
                "result_quality": r["scores"]["result_quality"],
                "helpfulness": r["scores"]["helpfulness"],
                "overall_quality": r["overall_quality"],
                "llm_judge_overall": judge.get("overall", "") if not judge.get("error") else "",
                "optimize": r["optimize"],
                "issues": " | ".join(r["issues"]),
                "optimization_hints": " | ".join(r["optimization_hints"]),
                "structural_pass": r["pass"],
            })


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Run Groq LLM-as-judge for semantic relevance (needs GROQ_API_KEY)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run only first N cases (for quick tests)",
    )
    args = parser.parse_args()

    if not CASES_PATH.exists():
        print("cases.json missing — run: python scripts/generate_eval_cases.py")
        return 1

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]

    use_judge = args.judge and groq_judge_available()
    if args.judge and not use_judge:
        print("Warning: --judge requested but GROQ_API_KEY not set — skipping LLM judge")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Running {len(cases)} cases (structural + quality scoring) ===\n")
    t0 = time.time()
    results = []

    for i, case in enumerate(cases):
        r = await run_case(case, use_judge=use_judge)
        results.append(r)
        mark = "PASS" if r["pass"] else "FAIL"
        q = r["overall_quality"]
        v = r.get("verdict", "?")
        opt = " FIX" if r["optimize"] else ""
        q_preview = r["query"][:50].encode("ascii", "replace").decode()
        print(f"  [{mark}] {v:10s} Q={q:3d}{opt} ({i+1}/{len(cases)}) {q_preview}")
        if r["optimize"]:
            out_preview = r["reply"][:120].encode("ascii", "replace").decode()
            print(f"           OUTPUT: {out_preview}...")
        if not r["pass"]:
            for f in r["failures"]:
                print(f"         structural: {f}")

    passed = sum(1 for r in results if r["pass"])
    duration = round(time.time() - t0, 1)

    dim_keys = ["intent_match", "response_relevance", "language_match", "result_quality", "helpfulness"]
    dim_avgs = {}
    for k in dim_keys:
        dim_avgs[k] = round(sum(r["scores"][k] for r in results) / len(results), 1)

    cat_avgs: dict[str, list] = defaultdict(list)
    for r in results:
        cat_avgs[r["category"]].append(r["overall_quality"])
    avg_by_cat = {k: round(sum(v) / len(v), 1) for k, v in cat_avgs.items()}

    avg_quality = round(sum(r["overall_quality"] for r in results) / len(results), 1)
    optimize_count = sum(1 for r in results if r["optimize"])
    excellent_count = sum(1 for r in results if r["overall_quality"] >= 90)
    relevant_count = sum(1 for r in results if r.get("verdict") == "RELEVANT")
    partial_count = sum(1 for r in results if r.get("verdict") == "PARTIAL")
    fix_count = sum(1 for r in results if r.get("verdict") in ("NEEDS_FIX", "WRONG"))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(100 * passed / len(results), 1),
        "avg_quality": avg_quality,
        "optimize_count": optimize_count,
        "excellent_count": excellent_count,
        "relevant_count": relevant_count,
        "partial_count": partial_count,
        "fix_count": fix_count,
        "dimension_averages": dim_avgs,
        "avg_by_category": avg_by_cat,
        "duration_s": duration,
        "judge_enabled": use_judge,
    }

    # Write reports
    quality_report = {"summary": summary, "results": results}
    analysis_html = _response_analysis_html(results, summary)
    OUT_DIR.joinpath("response_analysis.html").write_text(analysis_html, encoding="utf-8")
    OUT_DIR.joinpath("quality_report.html").write_text(analysis_html, encoding="utf-8")
    OUT_DIR.joinpath("quality_report.json").write_text(
        json.dumps(quality_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_csv(results, OUT_DIR / "quality_report.csv")

    OUT_DIR.joinpath("eval_report.html").write_text(_redirect_html("response_analysis.html"), encoding="utf-8")
    OUT_DIR.joinpath("eval_report.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n=== Structural: {passed}/{len(results)} passed ({summary['pass_rate']}%) ===")
    print(f"=== Relevance:  {relevant_count} RELEVANT · {partial_count} PARTIAL · {fix_count} NEED FIX ===")
    print(f"=== Quality:    avg {avg_quality}% · {optimize_count} to optimize ===\n")
    print(f">>> OPEN THIS (har query ka actual output): {OUT_DIR / 'response_analysis.html'}")
    print(f"    CSV (Excel):  {OUT_DIR / 'quality_report.csv'}")
    print(f"    JSON:         {OUT_DIR / 'quality_report.json'}\n")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
