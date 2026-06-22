#!/usr/bin/env python3
"""Phase A+B minimum acceptance tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database

# (session_suffix, message, expect_mode_substr, max_machines, setup_msgs)
CASES = [
    ("t1", "hi", "greeting", 0, []),
    ("t2", "refund chahiye", "refund", 0, []),
    ("t3", "payment cut gaya booking nahi hui", "payment", 0, []),
    ("t4", "machine abhi tak deliver nahi hui", "order", 0, []),
    ("t5", "machine kaise book karu", "platform", 0, []),
    ("t6", "crawler drill in Jaipur", "search", 999, []),
    ("t7a", "road roller chahiye", "clarification", 999, []),
    ("t7b", "Pune", "search", 999, [("road roller chahiye", "t7a")]),
    ("t8a", "crane in Jaipur", "search", 999, []),
    ("t8b", "excavator in Delhi", "search", 999, [("crane in Jaipur", "t8a")]),
    ("t9a", "road roller", "clarification", 999, []),
    ("t9b", "dump truck in Mumbai", "search", 999, [("road roller", "t9a")]),
    ("t10", "CAT excavator Mumbai", "search", 999, []),
    ("t11", "weather in Jaipur", "out_of_scope", 0, []),
]


SEARCH_OK_MODES = (
    "search", "no_result", "machine_search", "clarification",
    "purpose_alternatives", "too_many_results", "rent_machine", "buy_machine",
)


async def run_case(suffix, msg, expect, max_m, setup):
    sid = f"phaseab_{suffix}"
    clear_conversation(sid)
    for setup_msg, _ in setup:
        await chatbot_response(sid, setup_msg, database)
    resp = await chatbot_response(sid, msg, database)
    data = resp.get("data") or {}
    mode = (data.get("context") or {}).get("assistant_mode", "")
    machines = len(data.get("machines") or [])
    ok = expect in mode
    if expect == "search":
        ok = mode in SEARCH_OK_MODES or "search" in mode
    if max_m == 0 and machines > 0:
        ok = False
    # excavator in Delhi must not return crane context in filters
    if suffix == "t8b":
        filters = data.get("filters") or {}
        cat = (filters.get("category") or "").lower()
        city = (filters.get("city") or "").lower()
        if "excavator" not in cat and "excavator" not in (resp.get("message") or "").lower():
            ok = False
        if city and city != "delhi":
            ok = False
    if suffix == "t9b":
        filters = data.get("filters") or {}
        cat = (filters.get("category") or "").lower()
        if "dump" not in cat and "dump" not in (resp.get("message") or "").lower():
            ok = False
    print(f"[{'PASS' if ok else 'FAIL'}] {msg[:45]:45} | mode={mode} machines={machines}")
    return ok


async def main():
    print("=" * 72)
    print("Phase A+B Tests")
    print("=" * 72)
    passed = failed = 0
    for suffix, msg, expect, max_m, setup in CASES:
        ok = await run_case(suffix, msg, expect, max_m, setup)
        passed += int(ok)
        failed += int(not ok)
    print("=" * 72)
    print(f"Passed: {passed} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
