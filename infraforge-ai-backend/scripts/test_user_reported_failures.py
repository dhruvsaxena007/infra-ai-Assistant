"""
Regression tests for user-reported assistant failures (mechanism-level).
Run: python scripts/test_user_reported_failures.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.numeric_normalizer import extract_budget_amount, expand_numeric_shorthand
from app.ai.query_parser import parse_query
from app.ai.semantic_turn_gateway import understand_turn_semantically
from app.ai.capability_registry import has_support_action_signal
from app.ai.knowledge_query_engine import detect_knowledge_query


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    if cond:
        print(f"  [PASS] {name}")
        return True
    print(f"  [FAIL] {name} {detail}")
    return False


async def _async_tests() -> int:
    failed = 0

    print("\n--- Numeric ---")
    failed += 0 if _ok("8.5k -> 8500", extract_budget_amount(expand_numeric_shorthand("under 8.5k per day")) == 8500) else 1
    failed += 0 if _ok("7k -> 7000", extract_budget_amount(expand_numeric_shorthand("under 7k per day")) == 7000) else 1
    p = parse_query("excavator in delhi under 8.5k per day")
    failed += 0 if _ok("parse 8.5k", p.get("max_price") == 8500, str(p.get("max_price"))) else 1

    print("\n--- Semantic intent ---")
    cases = [
        ("how can you help me", "meta_help"),
        ("what is my name", "memory_question"),
        ("whats my name", "memory_question"),
        ("are you mad", "frustration"),
        ("I need help from support", "support"),
        ("what is jcb", "domain_knowledge"),
        ("bahri pathar lejane ke liye best machine konsi hogi", "recommendation"),
        ("mujhe machine recommendation chaiye", "recommendation"),
        ("which digging machine is the best jcb or komatsu", "comparison"),
        ("inme se best konsa brand hai", "comparison"),
    ]
    for msg, want in cases:
        u = await understand_turn_semantically(msg, parsed=parse_query(msg), context={})
        failed += 0 if _ok(f"{want}: {msg[:40]}", u.primary_intent == want, f"got {u.primary_intent}") else 1

    print("\n--- Support signal ---")
    failed += 0 if _ok("help from support", has_support_action_signal("I need help from support")) else 1

    print("\n--- Knowledge ---")
    kq = detect_knowledge_query("what is jcb", parse_query("what is jcb"))
    failed += 0 if _ok("what is jcb knowledge", kq is not None) else 1

    print("\n--- Live chat (subset) ---")
    try:
        from app.database.mongodb import database
        from app.chatbot.chatbot_service import chatbot_response, reset_session_state

        async def chat(msg: str, sid: str) -> dict:
            return await chatbot_response(sid, msg, database)

        sid = "test_user_failures"
        reset_session_state(sid)

        r = await chat("how can you help me", sid)
        m = (r.get("message") or "").lower()
        failed += 0 if _ok("live meta_help", "went wrong" not in m and ("help" in m or "madad" in m or "search" in m)) else 1

        r = await chat("what is my name", sid)
        m = (r.get("message") or "").lower()
        failed += 0 if _ok("live memory", "went wrong" not in m) else 1

        reset_session_state(sid)
        await chat("digging ke liye best machine konsi hogi", sid)
        r = await chat("in jaipur", sid)
        m = (r.get("message") or "").lower()
        failed += 0 if _ok("live fragment jaipur", "bahar" not in m and "outside what" not in m and "went wrong" not in m) else 1

        reset_session_state(sid)
        r = await chat("excavator in delhi under 8.5k per day", sid)
        filt = (r.get("data") or {}).get("filters") or {}
        failed += 0 if _ok("live 8.5k search", filt.get("max_price") == 8500, str(filt.get("max_price"))) else 1
    except Exception as exc:
        print(f"  [SKIP] live chat tests: {exc}")

    return failed


def main() -> int:
    print("=" * 60)
    failed = asyncio.run(_async_tests())
    print("=" * 60)
    if failed:
        print(f"FAILED: {failed}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
