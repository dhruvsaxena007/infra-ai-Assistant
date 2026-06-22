"""
Phase 1B — Assistant evaluation baseline tests.

Documents current pass/fail behavior before behavior changes.
Run: python scripts/test_assistant_evaluation_baseline.py

Optional:
  ASSISTANT_DEBUG=true python scripts/test_assistant_evaluation_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.database.mongodb import database  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402


@dataclass
class EvalResult:
    name: str
    passed: bool
    expected_failure: bool = False
    detail: str = ""


@dataclass
class EvalSummary:
    results: list[EvalResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, *, xfail: bool = False, detail: str = "") -> None:
        self.results.append(EvalResult(name=name, passed=ok, expected_failure=xfail, detail=detail))

    def report(self) -> None:
        passed = sum(1 for r in self.results if r.passed and not r.expected_failure)
        failed = sum(1 for r in self.results if not r.passed and not r.expected_failure)
        xfail_ok = sum(1 for r in self.results if r.expected_failure and not r.passed)
        xfail_unexpected = sum(1 for r in self.results if r.expected_failure and r.passed)

        print("\n=== Assistant Evaluation Baseline ===\n")
        for r in self.results:
            if r.expected_failure:
                tag = "XFAIL-OK" if not r.passed else "XFAIL-UNEXPECTED-PASS"
            else:
                tag = "PASS" if r.passed else "FAIL"
            line = f"  [{tag}] {r.name}"
            if r.detail:
                line += f" — {r.detail}"
            print(line)

        print(f"\nPassed: {passed}")
        print(f"Failed (baseline): {failed}")
        print(f"Expected failures (confirmed): {xfail_ok}")
        if xfail_unexpected:
            print(f"Expected failures that unexpectedly passed: {xfail_unexpected}")
        print(f"Total: {len(self.results)}")


def _data(resp: dict) -> dict:
    return resp.get("data") or {}


def _msg(resp: dict) -> str:
    return (resp.get("message") or _data(resp).get("message") or "").strip()


def _mode(resp: dict) -> str:
    d = _data(resp)
    return str((d.get("context") or {}).get("assistant_mode") or d.get("assistant_mode") or "")


def _intent(resp: dict) -> str:
    d = _data(resp)
    return str((d.get("context") or {}).get("intent") or "")


def _machines(resp: dict) -> list:
    return _data(resp).get("machines") or []


def _cat(resp: dict) -> str:
    return str((_data(resp).get("filters") or {}).get("category") or "").lower()


def _city(resp: dict) -> str:
    return str((_data(resp).get("filters") or {}).get("city") or "").lower()


def _asks_clarification(msg: str) -> bool:
    lower = msg.lower()
    patterns = (
        r"\bcity\b", r"\blocation\b", r"\bsite\b", r"\bsheher\b",
        r"\bwork\b", r"\bpurpose\b", r"\bproject\b", r"\bkaam\b",
        r"\bcategory\b", r"\btype\b", r"\bwhich\b", r"\bwhat\b",
        r"\bbata\b", r"\btell me\b", r"\bshare\b",
    )
    return any(re.search(p, lower) for p in patterns)


def _not_excavator_assumed(resp: dict, msg: str) -> bool:
    cat = _cat(resp)
    if cat == "excavator":
        return False
    lower = msg.lower()
    if "excavator" in lower and cat == "excavator":
        return False
    return True


async def test_01_broad_request(summary: EvalSummary) -> None:
    sid = "eval_broad_machine"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "i need a machine", database)
    msg = _msg(resp)
    ok = (
        _not_excavator_assumed(resp, msg)
        and _asks_clarification(msg)
        and len(_machines(resp)) == 0
    )
    summary.add(
        "1. Broad request — no excavator assumption, asks purpose/city",
        ok,
        detail=f"mode={_mode(resp)} cat={_cat(resp)!r} msg={msg[:80]!r}",
    )


async def test_02_rent_broad(summary: EvalSummary) -> None:
    sid = "eval_rent_broad"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "i want to rent a machine", database)
    msg = _msg(resp)
    ok = _asks_clarification(msg) and len(_machines(resp)) == 0
    summary.add(
        "2. Rent broad — asks purpose/city, no immediate search",
        ok,
        detail=f"mode={_mode(resp)} machines={len(_machines(resp))}",
    )


async def test_03_recommendation_broad(summary: EvalSummary) -> None:
    sid = "eval_recommend_broad"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "can you recommend me a machine", database)
    msg = _msg(resp)
    ok = (
        _mode(resp) != "greeting"
        and _asks_clarification(msg)
        and len(_machines(resp)) == 0
    )
    summary.add(
        "3. Recommendation broad — asks project/work + city, not greeting",
        ok,
        detail=f"mode={_mode(resp)} intent={_intent(resp)}",
    )


async def test_04_roadroller_brands(summary: EvalSummary) -> None:
    sid = "eval_rr_brands"
    clear_conversation(sid)
    resp = await chatbot_response(
        sid, "konse konse brands ke roadroller hai tumhare pas", database,
    )
    msg = _msg(resp).lower()
    ok = (
        "road roller" in _cat(resp) or "road roller" in msg or "roller" in msg
    ) and _mode(resp) in ("comparison", "clarification", "machine_search", "support", "recommendation", "conversational", "unknown", "")
    summary.add(
        "4. Road roller brand query — identifies road roller / brand context",
        ok,
        xfail=True,
        detail=f"mode={_mode(resp)} cat={_cat(resp)!r}",
    )


async def test_05_jcb_vs_cat_roller(summary: EvalSummary) -> None:
    sid = "eval_jcb_cat_roller"
    clear_conversation(sid)
    resp = await chatbot_response(
        sid, "JCB ke roadroller acche hote hai ya CAT ke", database,
    )
    cat = _cat(resp)
    ok = cat != "backhoe loader" and "road roller" in cat or cat == ""
    summary.add(
        "5. JCB vs CAT road roller — must not map JCB to backhoe loader",
        ok,
        xfail=True,
        detail=f"cat={cat!r} mode={_mode(resp)}",
    )


async def test_06_cheaper_followup(summary: EvalSummary) -> None:
    sid = "eval_cheaper_followup"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in jaipur under 8000", database)
    resp = await chatbot_response(sid, "cheaper option hai?", database)
    ok = _cat(resp) == "excavator" and (_city(resp) == "jaipur" or "jaipur" in _msg(resp).lower())
    summary.add(
        "6. Cheaper follow-up — reuses category/city/budget context",
        ok,
        detail=f"cat={_cat(resp)} city={_city(resp)}",
    )


async def test_07_higher_budget_followup(summary: EvalSummary) -> None:
    sid = "eval_higher_budget"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in jaipur under 8000", database)
    resp = await chatbot_response(sid, "higher budget me kya option hai?", database)
    ok = _cat(resp) == "excavator" and (_city(resp) == "jaipur" or "jaipur" in _msg(resp).lower())
    summary.add(
        "7. Higher budget follow-up — reuses category/city context",
        ok,
        xfail=True,
        detail=f"cat={_cat(resp)} city={_city(resp)}",
    )


async def test_08_acknowledgement(summary: EvalSummary) -> None:
    sid = "eval_ack_flow"
    clear_conversation(sid)
    r1 = await chatbot_response(sid, "i need a machine", database)
    r2 = await chatbot_response(sid, "ok", database)
    ok = (
        _mode(r1) in ("clarification", "recommendation_clarification", "unknown", "conversational")
        and _mode(r2) != "greeting"
        and len(_machines(r2)) == 0
    )
    summary.add(
        "8. Acknowledgement — ok does not reset conversation randomly",
        ok,
        detail=f"turn1={_mode(r1)} turn2={_mode(r2)}",
    )


async def test_09_frustration(summary: EvalSummary) -> None:
    sid = "eval_frustration"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "you are useless", database)
    ok = len(_machines(resp)) == 0 and _mode(resp) not in ("machine_search",)
    summary.add(
        "9. Frustration — recovery, no machine search",
        ok,
        detail=f"mode={_mode(resp)} intent={_intent(resp)}",
    )


async def test_10_payment_issue(summary: EvalSummary) -> None:
    sid = "eval_payment"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "payment cut gaya booking nahi hui", database)
    mode = _mode(resp)
    intent = _intent(resp)
    ok = (
        len(_machines(resp)) == 0
        and (
            mode in ("support", "payment_issue", "order_issue", "refund_return")
            or intent in ("refund_return", "order_issue", "payment_issue")
            or "payment" in intent
        )
    )
    summary.add(
        "10. Payment issue — support flow, no machine search",
        ok,
        detail=f"mode={mode} intent={intent}",
    )


async def test_11_irrelevant(summary: EvalSummary) -> None:
    sid = "eval_irrelevant"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "what is the weather today", database)
    ok = len(_machines(resp)) == 0 and _intent(resp) in ("out_of_scope", "unknown", "conversational", "")
    summary.add(
        "11. Irrelevant query — out_of_scope, no machine search",
        ok,
        detail=f"mode={_mode(resp)} intent={_intent(resp)}",
    )


async def test_12_repeated_response(summary: EvalSummary) -> None:
    sid = "eval_repeat"
    clear_conversation(sid)
    replies = []
    for q in (
        "how are you",
        "can you recommend me a machine",
        "can you help me finding a machine",
    ):
        resp = await chatbot_response(sid, q, database)
        replies.append(_msg(resp).lower().strip())
    unique = len(set(replies))
    ok = unique >= 2 and replies[0] != replies[1]
    summary.add(
        "12. Repeated response — should not return same generic sentence repeatedly",
        ok,
        detail=f"unique_replies={unique}/3",
    )


async def test_13_debug_trace_fields(summary: EvalSummary) -> None:
    from app.core.config import settings
    from app.ai.assistant_debug_trace import get_last_debug_trace

    if not settings.ASSISTANT_DEBUG:
        summary.add(
            "13. Debug trace fields — skipped (set ASSISTANT_DEBUG=true to run)",
            True,
            detail="skipped",
        )
        return

    sid = "eval_debug_trace"
    clear_conversation(sid)
    await chatbot_response(sid, "i need a machine", database)
    trace = get_last_debug_trace()
    ok = bool(
        trace
        and trace.get("response", {}).get("final_response_source")
        and "llm_intent_called" in (trace.get("classification") or {})
        and "rules_intent_called" in (trace.get("classification") or {})
    )
    src = (trace or {}).get("response", {}).get("final_response_source", "")
    cls = (trace or {}).get("classification") or {}
    summary.add(
        "13. Debug trace — final_response_source + intent flags present",
        ok,
        detail=f"source={src!r} llm_intent={cls.get('llm_intent_called')} rules={cls.get('rules_intent_called')}",
    )


async def run_all() -> EvalSummary:
    summary = EvalSummary()
    tests: list[Callable] = [
        test_01_broad_request,
        test_02_rent_broad,
        test_03_recommendation_broad,
        test_04_roadroller_brands,
        test_05_jcb_vs_cat_roller,
        test_06_cheaper_followup,
        test_07_higher_budget_followup,
        test_08_acknowledgement,
        test_09_frustration,
        test_10_payment_issue,
        test_11_irrelevant,
        test_12_repeated_response,
        test_13_debug_trace_fields,
    ]
    for fn in tests:
        await fn(summary)
    return summary


def main() -> int:
    summary = asyncio.run(run_all())
    summary.report()
    failed = sum(1 for r in summary.results if not r.passed and not r.expected_failure)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
