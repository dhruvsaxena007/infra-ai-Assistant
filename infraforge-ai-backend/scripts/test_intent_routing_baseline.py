"""
Phase 3 — Generalized intent / routing baseline tests.

Run: python scripts/test_intent_routing_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.intent_classifier import classify_intent  # noqa: E402
from app.ai.intent_signals import (  # noqa: E402
    is_acknowledgement_signal,
    is_broad_machine_request_signal,
    is_cheaper_option_signal,
    is_frustration_signal,
    is_higher_budget_signal,
    is_machine_brand_query_signal,
    is_machine_comparison_signal,
    is_recommendation_broad_signal,
)
from app.ai.query_parser import parse_query  # noqa: E402
from app.database.mongodb import database  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402


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


async def test_brand_inventory_signals(c: Counter) -> None:
    cases = [
        "konse brands ke roadroller hai tumhare pas",
        "which brands of excavator do you have",
        "crane companies available hai",
        "wheel loader ke brands batao",
        "Hyundai excavator milta hai kya",
    ]
    for q in cases:
        p = parse_query(q)
        ok = is_machine_brand_query_signal(q, p) or bool(p.get("category") or p.get("brand"))
        c.record(f"brand inventory signal: {q[:50]}", ok)


async def test_comparison_signals(c: Counter) -> None:
    cases = [
        "JCB ke roadroller acche hote hai ya CAT ke",
        "Hyundai excavator vs Komatsu excavator",
        "backhoe loader or excavator for digging",
        "road roller vs compactor for compaction",
    ]
    for q in cases:
        p = parse_query(q)
        c.record(f"comparison signal: {q[:50]}", is_machine_comparison_signal(q, p), f"cat={p.get('category')}")


async def test_followup_signals(c: Counter) -> None:
    ctx = {"last_filters": {"category": "excavator", "city": "jaipur", "max_price": 8000}}
    c.record("higher budget signal with session", is_higher_budget_signal("higher budget me kya option hai?", ctx))
    c.record("cheaper follow-up signal with session", is_cheaper_option_signal("cheaper option hai?", ctx))
    c.record("rent-only refinement signal", is_cheaper_option_signal("rent only", ctx))


async def test_broad_and_recommendation_signals(c: Counter) -> None:
    for q in (
        "i need a machine",
        "i want to rent a machine",
        "buy machine chahiye",
        "construction equipment chahiye",
    ):
        c.record(f"broad request: {q}", is_broad_machine_request_signal(q))
    for q in (
        "can you recommend me a machine",
        "suggest equipment for my site",
        "kaunsi machine sahi rahegi",
    ):
        c.record(f"recommendation broad: {q[:40]}", is_recommendation_broad_signal(q))


async def test_ack_frustration_oos_signals(c: Counter) -> None:
    c.record(
        "acknowledgement with pending",
        is_acknowledgement_signal("ok", {"pending": {"missing_field": "machine_purpose"}}),
    )
    for q in ("you are useless", "not helpful", "kuch samajh nahi raha"):
        c.record(f"frustration: {q}", is_frustration_signal(q))


async def test_classifier_intents(c: Counter) -> None:
    async def check(label: str, coro):
        r = await coro
        ok = r.get("intent") not in ("unknown", None, "")
        detail = f"{r.get('intent')} search={r.get('should_search_machines')}"
        c.record(label, ok, detail)

    await check("classifier: road roller brands", classify_intent("konse brands ke roadroller hai tumhare pas"))
    await check("classifier: recommendation", classify_intent("can you recommend me a machine"))
    await check("classifier: frustration", classify_intent("you are useless"))
    ctx = {"last_filters": {"category": "excavator", "city": "jaipur", "max_price": 8000}}
    await check("classifier: higher budget", classify_intent("higher budget me kya option hai?", ctx))
    await check("classifier: rent broad", classify_intent("i want to rent a machine"))
    await check("classifier: comparison", classify_intent("JCB ke roadroller acche hote hai ya CAT ke"))
    await check("classifier: out of scope", classify_intent("what is the weather today"))


async def test_integration_flows(c: Counter) -> None:
    def intent(resp) -> str:
        return (resp.get("data", {}).get("context", {}) or {}).get("intent") or ""

    def mode(resp) -> str:
        return (resp.get("data", {}).get("context", {}) or {}).get("assistant_mode") or ""

    def machines(resp) -> list:
        return resp.get("data", {}).get("machines") or []

    def cat(resp) -> str:
        return str((resp.get("data", {}).get("filters") or {}).get("category") or "")

    sid = "p3_recommend"
    clear_conversation(sid)
    r = await chatbot_response(sid, "can you recommend me a machine", database)
    c.record(
        "integration: recommendation not greeting",
        mode(r) in ("recommendation_clarification", "clarification", "project_recommendation"),
        f"mode={mode(r)} intent={intent(r)}",
    )

    sid = "p3_frustration"
    clear_conversation(sid)
    r = await chatbot_response(sid, "you are useless", database)
    c.record(
        "integration: frustration no search",
        len(machines(r)) == 0 and intent(r) in ("frustration", "support", ""),
        f"intent={intent(r)}",
    )

    sid = "p3_brand"
    clear_conversation(sid)
    r = await chatbot_response(sid, "konse brands ke roadroller hai tumhare pas", database)
    c.record(
        "integration: brand query not unknown",
        intent(r) not in ("unknown", "") or mode(r) in ("brand_query", "machine_search", "search"),
        f"intent={intent(r)} mode={mode(r)}",
    )

    sid = "p3_higher"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in jaipur under 8000", database)
    r = await chatbot_response(sid, "higher budget me kya option hai?", database)
    c.record(
        "integration: higher budget follow-up",
        intent(r) in ("higher_budget_query", "machine_search", "cheaper_option_query", "") or cat(r) == "excavator",
        f"intent={intent(r)} cat={cat(r)}",
    )

    sid = "p3_cheaper"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in jaipur under 8000", database)
    r = await chatbot_response(sid, "cheaper option hai?", database)
    c.record(
        "integration: cheaper follow-up keeps context",
        cat(r) == "excavator" or intent(r) in ("cheaper_option_query", "machine_search", ""),
        f"intent={intent(r)} cat={cat(r)}",
    )

    sid = "p3_ack"
    clear_conversation(sid)
    await chatbot_response(sid, "i need a machine", database)
    r = await chatbot_response(sid, "ok", database)
    c.record(
        "integration: acknowledgement flow",
        mode(r) != "greeting" and len(machines(r)) == 0,
        f"mode={mode(r)} intent={intent(r)}",
    )

    sid = "p3_oos"
    clear_conversation(sid)
    r = await chatbot_response(sid, "what is the weather today", database)
    c.record("integration: out of scope", intent(r) == "out_of_scope" and len(machines(r)) == 0, f"intent={intent(r)}")


async def main() -> int:
    print("\n=== Phase 3 Intent / Routing Baseline ===\n")
    c = Counter()
    for title, fn in (
        ("Brand inventory signals", test_brand_inventory_signals),
        ("Comparison signals", test_comparison_signals),
        ("Follow-up signals", test_followup_signals),
        ("Broad + recommendation signals", test_broad_and_recommendation_signals),
        ("Ack / frustration signals", test_ack_frustration_oos_signals),
        ("Classifier intents", test_classifier_intents),
        ("Integration flows", test_integration_flows),
    ):
        print(f"-- {title} --")
        await fn(c)
    print(f"\nTotal: {c.passed}/{c.passed + c.failed} passed, {c.failed} failed\n")
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
