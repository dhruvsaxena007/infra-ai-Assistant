"""
Run sequential conversation eval (10–15 turn chats) with transcript reports.

Run:
    python scripts/generate_conversation_eval_cases.py
    python scripts/run_conversation_eval.py
    python scripts/run_conversation_eval.py --judge
    python scripts/run_conversation_eval.py --id en_greet_jaipur_excavator

Reports:
    promptfoo/output/conversation_report.html   — full transcripts per chat
    promptfoo/output/conversation_report.json
    promptfoo/output/conversation_report.csv
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
extract_meta = _scorer.extract_meta
groq_judge_available = _scorer.groq_judge_available
groq_judge_scores = _scorer.groq_judge_scores

_mod = _load_module("infraforge_chat", ROOT / "promptfoo" / "providers" / "infraforge_chat.py")
check_expect = _mod.check_expect
_msg = _mod._msg

_mem = _load_module("conversation_memory_checker", ROOT / "scripts" / "conversation_memory_checker.py")
RollingContext = _mem.RollingContext
evaluate_turn_memory = _mem.evaluate_turn_memory

CASES_PATH = ROOT / "promptfoo" / "tests" / "conversation_cases.json"
OUT_DIR = ROOT / "promptfoo" / "output"


async def run_conversation(case: dict, *, use_judge: bool) -> dict:
    sid = case["session_id"]
    if case.get("clear_session"):
        clear_conversation(sid)

    turn_results = []
    all_failures = []
    rolling = RollingContext()
    memory_checks = 0
    memory_pass = 0

    for i, t in enumerate(case["turns"]):
        resp = await chatbot_response(sid, t["message"], database)
        reply = _msg(resp)
        meta = extract_meta(resp)
        expect = t.get("expect") or {}
        structural_ok = True
        failures = []

        if expect:
            structural_ok, failures = check_expect(resp, expect)
            if not structural_ok:
                all_failures.extend([f"turn {i + 1}: {f}" for f in failures])

        mem = evaluate_turn_memory(
            message=t["message"],
            meta=meta,
            expect=expect,
            memory_role=t.get("memory_role"),
            rolling=rolling,
        )
        if mem["memory_failures"]:
            all_failures.extend([f"turn {i + 1} memory: {f}" for f in mem["memory_failures"]])
            structural_ok = False
            failures = failures + mem["memory_failures"]

        if mem["memory_required"]:
            memory_checks += 1
            if mem["memory_remembered"]:
                memory_pass += 1

        quality = compute_quality_scores(
            t["message"],
            resp,
            expect,
            structural_pass=structural_ok,
            case=case,
        )

        judge = None
        if use_judge and expect:
            judge = await groq_judge_scores(t["message"], quality["reply"], quality["meta"])

        turn_results.append({
            "turn": i + 1,
            "query": t["message"],
            "reply": reply,
            "mode": meta.get("assistant_mode", ""),
            "category": meta.get("category", ""),
            "city": meta.get("city", ""),
            "machines_count": meta.get("machines_count", 0),
            "used_previous_context": meta.get("used_previous_context", False),
            "memory_role": mem["memory_role"],
            "memory_required": mem["memory_required"],
            "memory_remembered": mem["memory_remembered"],
            "prior_context": mem["prior_context"],
            "expected_context": mem["expected_context"],
            "actual_context": mem["actual_context"],
            "memory_notes": mem["memory_notes"],
            "structural_pass": structural_ok if (expect or mem["memory_required"]) else None,
            "failures": failures,
            "expect": expect,
            "verdict": quality["verdict"] if (expect or mem["memory_required"]) else "INFO",
            "overall_quality": quality["overall"] if expect else None,
            "analysis": quality.get("analysis", "") if expect else "",
            "judge": judge,
        })

    turns_with_expect = [tr for tr in turn_results if tr["structural_pass"] is not None]
    avg_quality = 0.0
    scored = [tr for tr in turn_results if tr["overall_quality"] is not None]
    if scored:
        avg_quality = round(sum(tr["overall_quality"] for tr in scored) / len(scored), 1)

    memory_turns = [tr for tr in turn_results if tr["memory_required"]]
    memory_remembered_count = sum(1 for tr in memory_turns if tr["memory_remembered"])

    return {
        "id": case["id"],
        "title": case.get("title", case["id"]),
        "lang_mix": case.get("lang_mix", ""),
        "flow_type": case.get("flow_type", ""),
        "description": case.get("description", ""),
        "turn_count": len(turn_results),
        "turns_with_expect": len(turns_with_expect),
        "turns_passed": sum(1 for tr in turn_results if tr["structural_pass"] is True),
        "turns_failed": sum(1 for tr in turn_results if tr["structural_pass"] is False),
        "memory_checks": len(memory_turns),
        "memory_remembered": memory_remembered_count,
        "memory_forgot": len(memory_turns) - memory_remembered_count,
        "pass": len(all_failures) == 0,
        "failures": all_failures,
        "memory_score": round(100 * memory_pass / memory_checks, 1) if memory_checks else 100.0,
        "avg_quality": avg_quality,
        "turns": turn_results,
    }


def _conversation_html(results: list[dict], summary: dict) -> str:
    esc = html_lib.escape
    cards = []

    for r in results:
        status_color = "#34d399" if r["pass"] else "#f87171"
        turn_rows = []
        for tr in r["turns"]:
            if tr["structural_pass"] is True:
                st = '<span style="color:#34d399">PASS</span>'
            elif tr["structural_pass"] is False:
                st = '<span style="color:#f87171">FAIL</span>'
            else:
                st = '<span style="color:#94a3b8">—</span>'
            if tr["memory_required"]:
                if tr["memory_remembered"]:
                    mem_st = '<span style="color:#34d399;font-weight:700">YES</span>'
                else:
                    mem_st = '<span style="color:#f87171;font-weight:700">NO</span>'
            else:
                mem_st = '<span style="color:#64748b">n/a</span>'
            prior = tr.get("prior_context") or {}
            exp = tr.get("expected_context") or {}
            act = tr.get("actual_context") or {}
            ctx_line = ""
            if tr["memory_required"]:
                ctx_line = (
                    f"need: {esc(exp.get('category','') or '—')}/{esc(exp.get('city','') or '—')} "
                    f"· prior: {esc(prior.get('category','') or '—')}/{esc(prior.get('city','') or '—')} "
                    f"· got: {esc(act.get('category','') or '—')}/{esc(act.get('city','') or '—')}"
                )
            ctx_flag = "yes" if tr["used_previous_context"] else "—"
            machines = str(tr["machines_count"]) if tr["machines_count"] else "—"
            fail_txt = "<br>".join(esc(f) for f in tr["failures"]) if tr["failures"] else "—"
            turn_rows.append(f"""
            <tr>
              <td>{tr['turn']}</td>
              <td class="user">{esc(tr['query'])}</td>
              <td class="bot">{esc(tr['reply'])}</td>
              <td>{esc(tr.get('memory_role',''))}</td>
              <td>{mem_st}</td>
              <td class="ctx">{ctx_line or '—'}</td>
              <td>{esc(tr['mode'])}</td>
              <td>{esc(tr['category'])}</td>
              <td>{esc(tr['city'])}</td>
              <td>{machines}</td>
              <td>{ctx_flag}</td>
              <td>{st}</td>
              <td class="fail">{fail_txt}</td>
            </tr>""")

        fail_block = ""
        if r["failures"]:
            fail_block = "<div class='fails'><b>Failures:</b><ul>" + "".join(
                f"<li>{esc(f)}</li>" for f in r["failures"]
            ) + "</ul></div>"

        cards.append(f"""
        <div class="conv-card" data-lang="{esc(r['lang_mix'])}" data-flow="{esc(r['flow_type'])}">
          <div class="conv-header" style="border-left:4px solid {status_color}">
            <h3>{esc(r['title'])} <span class="id">({esc(r['id'])})</span></h3>
            <div class="meta">
              <span class="badge" style="background:{status_color}">{'PASS' if r['pass'] else 'FAIL'}</span>
              <span>{r['turn_count']} turns</span>
              <span>{esc(r['lang_mix'])}</span>
              <span>{esc(r['flow_type'])}</span>
              <span>memory {r['memory_score']}% ({r.get('memory_remembered',0)}/{r.get('memory_checks',0)} remembered)</span>
              <span>quality {r['avg_quality']}%</span>
              <span>{r['turns_passed']}/{r['turns_with_expect']} checks passed</span>
            </div>
            <p class="desc">{esc(r.get('description', ''))}</p>
            {fail_block}
          </div>
          <table>
            <thead><tr>
              <th>#</th><th>USER</th><th>ASSISTANT REPLY</th><th>Role</th>
              <th>Remembered?</th><th>Context need/prior/got</th><th>Mode</th>
              <th>Category</th><th>City</th><th>Machines</th><th>Used ctx</th>
              <th>Check</th><th>Issues</th>
            </tr></thead>
            <tbody>{''.join(turn_rows)}</tbody>
          </table>
        </div>""")

    by_lang = summary.get("by_lang_mix", {})
    by_flow = summary.get("by_flow_type", {})
    lang_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v['pass']}/{v['total']}</td><td>{v['avg_quality']}%</td></tr>"
        for k, v in sorted(by_lang.items())
    )
    flow_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v['pass']}/{v['total']}</td><td>{v['avg_quality']}%</td></tr>"
        for k, v in sorted(by_flow.items())
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Conversation Eval — InfraForge Assistant</title>
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
h2{{color:#a78bfa;font-size:16px}}
.filter input, .filter select{{padding:10px 14px;background:#1a1a22;border:1px solid #444;color:#fff;border-radius:8px;margin-right:8px;margin-bottom:8px}}
.conv-card{{background:#12121a;border:1px solid #2a2a35;border-radius:12px;margin:20px 32px;overflow:hidden}}
.conv-header{{padding:16px 20px;background:#1a1a24}}
.conv-header h3{{margin:0 0 8px;color:#e2e8f0;font-size:16px}}
.conv-header .id{{color:#94a3b8;font-weight:normal;font-size:13px}}
.meta{{display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:#94a3b8;align-items:center}}
.badge{{padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;color:#000}}
.desc{{font-size:13px;color:#a5b4fc;margin:10px 0 0}}
.fails{{background:#2a1515;padding:10px;border-radius:8px;margin-top:10px;font-size:12px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#151520;padding:8px;text-align:left;border-bottom:2px solid #6366f1}}
td{{padding:8px;border-bottom:1px solid #222;vertical-align:top}}
td.user{{font-weight:600;color:#f0f0ff;min-width:140px;max-width:200px}}
td.bot{{background:#0f0f16;color:#e2e8f0;white-space:pre-wrap;word-break:break-word;min-width:280px;max-width:420px;border-left:3px solid #6366f1}}
td.ctx{{font-size:11px;color:#a5b4fc;max-width:220px}}
td.fail{{color:#fbbf24;font-size:11px}}
.summary-table td, .summary-table th{{padding:8px 12px}}
</style>
<script>
function filterConvs() {{
  const q = (document.getElementById('q').value || '').toLowerCase();
  const lang = document.getElementById('lang').value;
  const flow = document.getElementById('flow').value;
  document.querySelectorAll('.conv-card').forEach(card => {{
    const text = card.innerText.toLowerCase();
    const okQ = !q || text.includes(q);
    const okL = !lang || card.dataset.lang === lang;
    const okF = !flow || card.dataset.flow === flow;
    card.style.display = (okQ && okL && okF) ? '' : 'none';
  }});
}}
</script>
</head><body>
<div class="header">
  <h1>Sequential Conversation Eval Report</h1>
  <div class="sub">10–15 turn real-life chats · English / Hinglish / Hindi · {summary['generated_at'][:19]}</div>
  <div class="stats">
    <div class="stat"><b>{summary['conversations']}</b><span>conversations</span></div>
    <div class="stat"><b>{summary['total_turns']}</b><span>total messages</span></div>
    <div class="stat"><b style="color:#34d399">{summary['passed']}</b><span>conversations passed</span></div>
    <div class="stat"><b style="color:#f87171">{summary['failed']}</b><span>conversations failed</span></div>
    <div class="stat"><b>{summary['turn_pass_rate']}%</b><span>turn checks passed</span></div>
    <div class="stat"><b>{summary['avg_memory_score']}%</b><span>avg memory score</span></div>
    <div class="stat"><b>{summary['avg_quality']}%</b><span>avg quality (checked turns)</span></div>
  </div>
</div>

<div class="note">
  <b>Yeh report single prompts se alag hai.</b> Har card ek poori conversation hai (10–15 messages).
  <b>USER</b> → <b>ASSISTANT REPLY</b> sequence dekho.   <b>Remembered?</b> = kya assistant ne pichla context (category/city) yaad rakha — har follow-up query ke liye.
  <b>Context column</b> = need/prior/got — kya chahiye tha, pehle kya tha, response me kya aaya.
</div>

<div class="section">
  <h2>Breakdown by language mix</h2>
  <table class="summary-table"><tr><th>Lang mix</th><th>Pass</th><th>Avg quality</th></tr>{lang_rows}</table>
  <h2>Breakdown by flow type</h2>
  <table class="summary-table"><tr><th>Flow</th><th>Pass</th><th>Avg quality</th></tr>{flow_rows}</table>
</div>

<div class="section filter">
  <input id="q" placeholder="Search conversation text…" oninput="filterConvs()">
  <select id="lang" onchange="filterConvs()">
    <option value="">All languages</option>
    <option value="english">English</option>
    <option value="hinglish">Hinglish</option>
    <option value="hindi">Hindi</option>
    <option value="mixed">Mixed</option>
  </select>
  <select id="flow" onchange="filterConvs()">
    <option value="">All flows</option>
    {"".join(f'<option value="{esc(k)}">{esc(k)}</option>' for k in sorted(by_flow.keys()))}
  </select>
</div>

{''.join(cards)}
</body></html>"""


def _write_csv(results: list[dict], path: Path) -> None:
    fields = [
        "conversation_id", "title", "lang_mix", "flow_type", "turn",
        "user_message", "assistant_reply", "memory_role", "memory_required",
        "memory_remembered", "prior_category", "prior_city",
        "expected_category", "expected_city", "actual_category", "actual_city",
        "used_previous_context", "mode", "machines_count",
        "structural_pass", "failures", "conversation_pass", "conversation_memory_score",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            for tr in r["turns"]:
                w.writerow({
                    "conversation_id": r["id"],
                    "title": r["title"],
                    "lang_mix": r["lang_mix"],
                    "flow_type": r["flow_type"],
                    "turn": tr["turn"],
                    "user_message": tr["query"],
                    "assistant_reply": tr["reply"],
                    "memory_role": tr.get("memory_role", ""),
                    "memory_required": tr.get("memory_required", False),
                    "memory_remembered": tr.get("memory_remembered"),
                    "prior_category": (tr.get("prior_context") or {}).get("category", ""),
                    "prior_city": (tr.get("prior_context") or {}).get("city", ""),
                    "expected_category": (tr.get("expected_context") or {}).get("category", ""),
                    "expected_city": (tr.get("expected_context") or {}).get("city", ""),
                    "actual_category": (tr.get("actual_context") or {}).get("category", ""),
                    "actual_city": (tr.get("actual_context") or {}).get("city", ""),
                    "used_previous_context": tr["used_previous_context"],
                    "mode": tr["mode"],
                    "machines_count": tr["machines_count"],
                    "structural_pass": tr["structural_pass"],
                    "failures": " | ".join(tr["failures"]),
                    "conversation_pass": r["pass"],
                    "conversation_memory_score": r["memory_score"],
                })


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--id", help="Run single conversation by id")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    gen_script = ROOT / "scripts" / "generate_conversation_eval_cases.py"
    if not CASES_PATH.exists():
        print("conversation_cases.json missing — generating…")
        import subprocess
        subprocess.run([sys.executable, str(gen_script)], check=True)

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.id:
        cases = [c for c in cases if c["id"] == args.id]
        if not cases:
            print(f"No conversation with id={args.id!r}")
            return 1
    if args.limit:
        cases = cases[: args.limit]

    use_judge = args.judge and groq_judge_available()
    if args.judge and not use_judge:
        print("Warning: --judge requested but GROQ_API_KEY not set")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Running {len(cases)} conversations (sequential multi-turn) ===\n")
    t0 = time.time()
    results = []

    for i, case in enumerate(cases):
        try:
            r = await run_conversation(case, use_judge=use_judge)
        except Exception as exc:
            r = {
                "id": case.get("id", f"conv_{i}"),
                "title": case.get("title", ""),
                "lang_mix": case.get("lang_mix", ""),
                "flow_type": case.get("flow_type", ""),
                "description": case.get("description", ""),
                "turn_count": len(case.get("turns", [])),
                "turns_with_expect": 0,
                "turns_passed": 0,
                "turns_failed": 0,
                "pass": False,
                "failures": [str(exc)],
                "memory_score": 0,
                "avg_quality": 0,
                "turns": [],
            }
        results.append(r)
        mark = "PASS" if r["pass"] else "FAIL"
        print(
            f"  [{mark}] {r['id']} — {r['turns_passed']}/{r['turns_with_expect']} checks "
            f"mem={r['memory_score']}% ({r.get('memory_remembered',0)}/{r.get('memory_checks',0)}) "
            f"({i + 1}/{len(cases)})"
        )
        if not r["pass"]:
            for f in r["failures"][:5]:
                print(f"         {f}")

    duration = round(time.time() - t0, 1)
    passed = sum(1 for r in results if r["pass"])
    total_turns = sum(r["turn_count"] for r in results)
    total_checks = sum(r["turns_with_expect"] for r in results)
    checks_passed = sum(r["turns_passed"] for r in results)

    by_lang: dict[str, dict] = defaultdict(lambda: {"total": 0, "pass": 0, "qualities": []})
    by_flow: dict[str, dict] = defaultdict(lambda: {"total": 0, "pass": 0, "qualities": []})
    for r in results:
        by_lang[r["lang_mix"]]["total"] += 1
        by_flow[r["flow_type"]]["total"] += 1
        by_lang[r["lang_mix"]]["qualities"].append(r["avg_quality"])
        by_flow[r["flow_type"]]["qualities"].append(r["avg_quality"])
        if r["pass"]:
            by_lang[r["lang_mix"]]["pass"] += 1
            by_flow[r["flow_type"]]["pass"] += 1

    def _agg(d: dict) -> dict:
        return {
            k: {
                "total": v["total"],
                "pass": v["pass"],
                "avg_quality": round(sum(v["qualities"]) / len(v["qualities"]), 1) if v["qualities"] else 0,
            }
            for k, v in d.items()
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conversations": len(results),
        "total_turns": total_turns,
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(100 * passed / len(results), 1) if results else 0,
        "turn_pass_rate": round(100 * checks_passed / total_checks, 1) if total_checks else 0,
        "avg_memory_score": round(sum(r["memory_score"] for r in results) / len(results), 1) if results else 0,
        "avg_quality": round(sum(r["avg_quality"] for r in results) / len(results), 1) if results else 0,
        "duration_s": duration,
        "by_lang_mix": _agg(by_lang),
        "by_flow_type": _agg(by_flow),
        "judge_enabled": use_judge,
    }

    report = {"summary": summary, "results": results}
    OUT_DIR.joinpath("conversation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    OUT_DIR.joinpath("conversation_report.html").write_text(
        _conversation_html(results, summary), encoding="utf-8"
    )
    _write_csv(results, OUT_DIR / "conversation_report.csv")

    print(f"\n=== Conversations: {passed}/{len(results)} passed ({summary['pass_rate']}%) ===")
    print(f"=== Turn checks:   {checks_passed}/{total_checks} ({summary['turn_pass_rate']}%) ===")
    print(f"=== Memory score:  avg {summary['avg_memory_score']}% ===")
    print(f"=== Duration:      {duration}s ===\n")
    print(f">>> OPEN REPORT: {OUT_DIR / 'conversation_report.html'}")
    print(f"    CSV:         {OUT_DIR / 'conversation_report.csv'}")
    print(f"    JSON:        {OUT_DIR / 'conversation_report.json'}\n")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
