"""
Phase 4 — Tool Permission Matrix + Safe Action Routing baseline tests.

Run: python scripts/test_tool_permission_baseline.py
With debug: ASSISTANT_DEBUG=true python scripts/test_tool_permission_baseline.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.safe_action_router import resolve_action_decision, validate_tool_call  # noqa: E402
from app.ai.tool_permission_matrix import (  # noqa: E402
    INTENT_PERMISSIONS,
    TOOL_MONGODB_SEARCH,
    TOOL_RAG,
    TOOL_SUPPORT,
    get_intent_permissions,
    is_tool_allowed,
)
from app.ai.query_parser import parse_query  # noqa: E402
from app.ai.intent_classifier import classify_intent  # noqa: E402


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


async def _classify(message: str, ctx: dict | None = None) -> dict:
    return await classify_intent(message, context=ctx or {})


async def _decision(message: str, ctx: dict | None = None) -> dict:
    clf = await _classify(message, ctx)
    return resolve_action_decision(clf, ctx or {}, message=message)


async def test_every_intent_tool_allowed(c: Counter) -> None:
    samples = {
        "greeting": "hello",
        "user_introduction": "my name is Rahul",
        "gratitude": "thank you",
        "polite_conversation": "how are you",
        "broad_machine_request": "i need a machine",
        "machine_recommendation": "recommend a machine for my site in jaipur",
        "machine_search": "excavator in jaipur",
        "machine_brand_query": "which brands of road roller do you have",
        "machine_comparison": "JCB vs CAT road roller",
        "cheaper_option_query": "cheaper option",
        "higher_budget_query": "higher budget option",
        "payment_issue": "payment failed",
        "refund_return": "i want refund",
        "document_question": "what does my invoice say",
        "frustration": "this is useless",
        "out_of_scope": "write me python code",
        "unknown": "xyzzy plugh",
        "acknowledgement": "ok",
    }
    ctx = {"last_filters": {"category": "excavator", "city": "jaipur"}}
    for intent_key, message in samples.items():
        use_ctx = ctx if intent_key in ("cheaper_option_query", "higher_budget_query", "acknowledgement") else {}
        if intent_key == "acknowledgement":
            use_ctx = {**use_ctx, "pending": {"type": "broad_machine", "missing_field": "category"}}
        dec = await _decision(message, use_ctx)
        tool = dec.get("allowed_tool") or ""
        ok = is_tool_allowed(dec.get("intent") or intent_key, tool)
        c.record(f"intent tool allowed: {intent_key}", ok, f"tool={tool}")


async def test_negative_search_blocks(c: Counter) -> None:
    negatives = [
        ("greeting", "hi there"),
        ("frustration", "you are useless"),
        ("payment_issue", "payment stuck"),
        ("refund_return", "refund my order"),
        ("document_question", "summarize my uploaded pdf"),
        ("out_of_scope", "tell me a joke"),
        ("unknown", "asdf qwerty"),
    ]
    for intent_hint, message in negatives:
        dec = await _decision(message)
        blocked = dec.get("allowed_tool") not in (TOOL_MONGODB_SEARCH, "mongodb_brand_inventory")
        c.record(f"no machine search: {intent_hint}", blocked and not dec.get("should_search_machines"), dec.get("allowed_tool"))

    search_dec = await _decision("excavator in jaipur")
    c.record("machine_search must not use RAG", search_dec.get("allowed_tool") != TOOL_RAG)
    c.record("machine_search blocked RAG in matrix", TOOL_RAG in (get_intent_permissions("machine_search").get("blocked_tools") or []))


async def test_brand_inventory_routing(c: Counter) -> None:
    cases = [
        ("which brands of road roller do you have", "query_brands_by_category", "mongodb_brand_inventory"),
        ("konse brands ke excavator hai", "query_brands_by_category", "mongodb_brand_inventory"),
        ("Hyundai excavator milta hai kya", "check_brand_availability", "mongodb_search"),
        ("JCB brands", "list_categories_for_brand", "mongodb_brand_inventory"),
        ("which brands available", "ask_brand_category", "clarification"),
    ]
    for message, expected_action, expected_tool in cases:
        dec = await _decision(message)
        c.record(
            f"brand route: {message[:40]}",
            dec.get("selected_action") == expected_action and dec.get("allowed_tool") == expected_tool,
            f"action={dec.get('selected_action')} tool={dec.get('allowed_tool')}",
        )


async def test_followup_routing(c: Counter) -> None:
    ctx = {"last_filters": {"category": "excavator", "city": "jaipur", "max_price": 8000}}
    cheap = await _decision("cheaper option hai?", ctx)
    c.record("cheaper uses search with context", cheap.get("allowed_tool") == TOOL_MONGODB_SEARCH and cheap.get("should_search_machines"))
    higher = await _decision("higher budget me kya option hai?", ctx)
    c.record("higher budget uses search with context", higher.get("allowed_tool") == TOOL_MONGODB_SEARCH)
    no_ctx = await _decision("cheaper option hai?", {})
    c.record("cheaper without context clarifies", no_ctx.get("allowed_tool") == "clarification")


async def test_acknowledgement_routing(c: Counter) -> None:
    pending_ctx = {"pending": {"type": "broad_machine", "missing_field": "category"}}
    with_pending = await _decision("ok", pending_ctx)
    c.record("ack with pending continues flow", with_pending.get("selected_action") == "continue_pending_flow")
    no_pending = await _decision("ok", {})
    c.record("ack without pending no search", not no_pending.get("should_search_machines"))


async def test_comparison_routing(c: Counter) -> None:
    dec = await _decision("JCB vs CAT road roller which is better")
    c.record("comparison not support", dec.get("allowed_tool") != TOOL_SUPPORT)
    c.record("comparison not RAG", dec.get("allowed_tool") != TOOL_RAG)


async def test_validate_tool_call(c: Counter) -> None:
    ok, _ = validate_tool_call("greeting", TOOL_MONGODB_SEARCH)
    c.record("validate blocks greeting search", not ok)
    ok2, _ = validate_tool_call("machine_search", TOOL_MONGODB_SEARCH)
    c.record("validate allows machine_search", ok2)
    ok3, _ = validate_tool_call("payment_issue", TOOL_MONGODB_SEARCH)
    c.record("validate blocks payment search", not ok3)


async def test_debug_trace_permission(c: Counter) -> None:
    os.environ["ASSISTANT_DEBUG"] = "true"
    try:
        from app.core.config import settings
        settings.ASSISTANT_DEBUG = True
        from app.ai.assistant_debug_trace import (
            begin_chat_trace,
            end_chat_trace,
            record_action_decision,
            get_current_debug_trace,
        )
        from app.ai.safe_action_router import resolve_action_decision

        token = begin_chat_trace("perm-test-session", "excavator in jaipur")
        clf = await _classify("excavator in jaipur")
        dec = resolve_action_decision(clf, {}, message="excavator in jaipur")
        record_action_decision(dec)
        trace = get_current_debug_trace()
        end_chat_trace(token)
        perm = (trace or {}).get("permission") or {}
        routing = (trace or {}).get("routing") or {}
        c.record("debug permission.matrix_applied", perm.get("matrix_applied") is True)
        c.record("debug permission.selected_tool", bool(perm.get("selected_tool")))
        c.record("debug permission.passed flag", perm.get("permission_passed") is True)
        c.record("debug routing.selected_action", bool(routing.get("selected_action")))
    finally:
        os.environ.pop("ASSISTANT_DEBUG", None)


async def test_matrix_coverage(c: Counter) -> None:
    required = {
        "greeting", "machine_brand_query", "machine_comparison", "payment_issue",
        "frustration", "document_question", "unknown", "acknowledgement",
    }
    for key in required:
        c.record(f"matrix has {key}", key in INTENT_PERMISSIONS)


async def main() -> None:
    c = Counter()
    print("Phase 4 — Tool Permission Matrix tests\n")
    await test_matrix_coverage(c)
    await test_every_intent_tool_allowed(c)
    await test_negative_search_blocks(c)
    await test_brand_inventory_routing(c)
    await test_followup_routing(c)
    await test_acknowledgement_routing(c)
    await test_comparison_routing(c)
    await test_validate_tool_call(c)
    await test_debug_trace_permission(c)
    print(f"\nPhase 4 results: {c.passed} passed, {c.failed} failed")
    if c.failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
