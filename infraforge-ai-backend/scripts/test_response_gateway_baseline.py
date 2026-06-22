"""
Phase 6 — Unified Response Plan + Dynamic Response Gateway baseline tests.

Run: python scripts/test_response_gateway_baseline.py
With debug: ASSISTANT_DEBUG=true python scripts/test_response_gateway_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("ASSISTANT_DEBUG", "true")

from app.ai.assistant_debug_trace import get_last_debug_trace  # noqa: E402
from app.ai.assistant_response_gateway import deliver_assistant_response  # noqa: E402
from app.ai.response_plan import build_response_plan  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response  # noqa: E402
from app.database.mongodb import database  # noqa: E402


class Counter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def record(self, label: str, ok: bool, detail: str = "") -> None:
        tag = "PASS" if ok else "FAIL"
        line = f"  [{tag}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)
        if ok:
            self.passed += 1
        else:
            self.failed += 1


async def test_gateway_always_used(c: Counter) -> None:
    out = await deliver_assistant_response(
        session_id="p6_gateway_unit",
        user_message="hello",
        draft_message="Hello draft",
        response_goal="greet_user",
        intent="greeting",
        assistant_mode="greeting",
        session_context={"session_id": "p6_gateway_unit"},
    )
    c.record("gateway returns message", bool(out.get("message")))
    c.record("gateway_used flag", bool(out.get("gateway_used")))
    c.record("response_plan attached", bool(out.get("response_plan")))
    c.record("response_signature present", bool(out.get("response_signature")))


async def test_context_aware_must_ask(c: Counter) -> None:
    plan_city = build_response_plan(
        response_goal="collect_machine_requirements",
        intent="broad_machine_request",
        assistant_mode="clarification",
        missing_fields=["city"],
        session_context={
            "_conversation_state": {
                "collected_fields": {"purpose": "compaction"},
                "last_search_filters": {},
            }
        },
    )
    c.record(
        "purpose known asks only city",
        plan_city.get("response_goal") == "ask_city"
        and "city" in " ".join(plan_city.get("must_ask") or []).lower(),
        f"goal={plan_city.get('response_goal')} must_ask={plan_city.get('must_ask')}",
    )

    plan_purpose = build_response_plan(
        response_goal="collect_machine_requirements",
        intent="broad_machine_request",
        assistant_mode="clarification",
        missing_fields=["purpose"],
        session_context={
            "_conversation_state": {
                "collected_fields": {"city": "delhi"},
                "last_search_filters": {"city": "delhi"},
            }
        },
    )
    c.record(
        "city known asks only purpose",
        plan_purpose.get("response_goal") == "ask_purpose"
        and any("work" in m or "category" in m for m in (plan_purpose.get("must_ask") or [])),
        f"goal={plan_purpose.get('response_goal')} must_ask={plan_purpose.get('must_ask')}",
    )


async def test_repetition_variation(c: Counter) -> None:
    sid = "p6_repeat"
    ctx: dict = {"session_id": sid, "turn_count": 0}
    signatures: list[str] = []
    for i in range(5):
        out = await deliver_assistant_response(
            session_id=sid,
            user_message=f"hello again {i}",
            draft_message="Welcome to InfraForge.",
            response_goal="greet_user",
            intent="greeting",
            assistant_mode="greeting",
            session_context=ctx,
        )
        sig = out.get("response_signature") or ""
        if sig:
            signatures.append(sig)
        ctx = dict(out.get("updated_session_context") or ctx)
        ctx["turn_count"] = i + 1
    unique = len(set(signatures))
    c.record("5 greet turns produce varied signatures", unique >= 2, f"unique={unique} sigs={signatures}")


async def test_llm_failure_local_fallback(c: Counter) -> None:
    with mock.patch(
        "app.ai.dynamic_response_generator._call_llm_generator",
        new=mock.AsyncMock(return_value=None),
    ):
        out = await deliver_assistant_response(
            session_id="p6_llm_fail",
            user_message="payment issue",
            draft_message="Please share booking ID.",
            response_goal="collect_transaction_id",
            intent="payment_issue",
            assistant_mode="support",
        )
    c.record("llm fail uses local fallback", bool(out.get("fallback_used")))
    c.record("fallback still has message", len(out.get("message") or "") > 5)
    c.record("fallback gateway_used", bool(out.get("gateway_used")))


async def test_integration_branches(c: Counter) -> None:
    cases = [
        ("p6_greet", "hello", "greeting"),
        ("p6_frustration", "this is so frustrating nothing works", "frustration"),
        ("p6_unknown", "xyzzy plugh random", "unknown"),
        ("p6_oos", "write python code for me", "out_of_scope"),
        ("p6_broad", "i need a machine", "broad_machine_request"),
        ("p6_support", "payment failed for my booking", "payment_issue"),
    ]
    for sid, message, label in cases:
        clear_conversation(sid)
        await chatbot_response(sid, message, database)
        trace = get_last_debug_trace() or {}
        resp = trace.get("response") or {}
        c.record(
            f"integration {label}: gateway_used",
            resp.get("gateway_used") is True,
            str(resp.get("final_response_source")),
        )
        c.record(
            f"integration {label}: response_plan_created",
            resp.get("response_plan_created") is True,
            f"goal={resp.get('response_goal')}",
        )
        c.record(
            f"integration {label}: no bypass",
            resp.get("response_gateway_bypass_detected") is not True,
            str(resp),
        )


async def test_search_no_invented_machines(c: Counter) -> None:
    sid = "p6_search"
    clear_conversation(sid)
    r = await chatbot_response(sid, "excavator in Jaipur", database)
    trace = get_last_debug_trace() or {}
    resp = trace.get("response") or {}
    machines = r.get("machines") or []
    c.record("search gateway used", resp.get("gateway_used") is True)
    c.record("search has response_signature", bool(resp.get("response_signature")))
    if machines:
        c.record(
            "search machines have names",
            all(m.get("name") or m.get("title") for m in machines[:3]),
            f"count={len(machines)}",
        )


async def test_requirement_flow_context_ask(c: Counter) -> None:
    sid = "p6_req_flow"
    clear_conversation(sid)
    await chatbot_response(sid, "i need a machine", database)
    r = await chatbot_response(sid, "compaction", database)
    msg = (r.get("message") or "").lower()
    c.record(
        "after purpose only, asks city not both",
        ("city" in msg or "sheher" in msg or "delhi" in msg or "jaipur" in msg)
        and "work type" not in msg
        and "digging" not in msg,
        msg[:120],
    )


async def main() -> int:
    c = Counter()
    print("Phase 6 — Response Gateway baseline")
    await test_gateway_always_used(c)
    await test_context_aware_must_ask(c)
    await test_repetition_variation(c)
    await test_llm_failure_local_fallback(c)
    await test_integration_branches(c)
    await test_search_no_invented_machines(c)
    await test_requirement_flow_context_ask(c)
    print(f"\nPhase 6 totals: {c.passed} passed, {c.failed} failed")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
