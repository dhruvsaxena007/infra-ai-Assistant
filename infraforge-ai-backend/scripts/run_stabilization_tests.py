#!/usr/bin/env python3
"""Stabilization + universal paraphrase tests (Groq/local only)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database
from app.core.config import settings

CASES = [
    ("hi", "g1", True, "greeting"),
    ("what can you do", "g2", True, None),
    ("I want refund", "r1", True, "refund_return"),
    ("payment failed", "p1", True, "payment_issue"),
    ("weather in Jaipur", "o1", True, "out_of_scope"),
    ("crawler drill in Jaipur", "m1", False, None),
    ("JCB in Delhi", "m2", False, None),
]

# Universal paraphrase families — NOT the exact phrases we coded
PARAPHRASE_CONVERSATIONAL = [
    ("are you fine", "conv1", "conversational"),
    ("how are you doing today", "conv2", "conversational"),
    ("i am fine what about you", "conv3", "conversational"),
    ("people know me as Rahul", "conv4", "conversational"),
    ("call me Priya", "conv5", "conversational"),
    ("im doing good thanks", "conv6", "conversational"),
    ("hope you are well", "conv7", "conversational"),
    ("my name id rajan", "conv8", "conversational"),
    ("are you good ?", "conv9", "conversational"),
]

PARAPHRASE_COMPARE = [
    ("which is better jcb or cat for road roller", "cmp1", "comparison"),
    ("volvo versus komatsu excavator", "cmp2", "comparison"),
    ("should i pick tata or mahindra dump truck", "cmp3", "comparison"),
    (
        "wese genrally hundai ke road roller acche hote hai ya CAT ke",
        "cmp4",
        "comparison",
    ),
]

PARAPHRASE_ATTRIBUTE = [
    ("what is the weight of that one", "attr1", "machine_detail"),
    ("tell me more about it", "attr2", "machine_detail"),
    ("fuel efficiency of this machine", "attr3", "machine_detail"),
    ("dimensions and weight please", "attr4", "machine_detail"),
    ("how much fuel does it consumes", "attr5", "machine_detail"),
]

PARAPHRASE_CONTEXTUAL = [
    ("Cheaper options", "ctx1", "cheaper_options"),
    ("Compare similar", "ctx2", "comparison"),
]


async def _check(msg: str, sid: str, expect_mode: str, *, setup_search: bool = False) -> dict:
    clear_conversation(sid)
    if setup_search:
        await chatbot_response(sid, "road roller in delhi under 10000", database)
    resp = await chatbot_response(sid, msg, database)
    data = resp.get("data") or {}
    mode = (data.get("context") or {}).get("assistant_mode") or ""
    machines = data.get("machines") or []
    ok = expect_mode in mode
    if expect_mode in (
        "conversational", "payment_issue", "refund_return", "out_of_scope",
    ):
        if len(machines) > 0:
            ok = False
    return {"pass": ok, "mode": mode, "machines": len(machines)}


async def main() -> int:
    print("=" * 72)
    print("Universal Assistant Tests")
    print(f"AI_PROVIDER={settings.AI_PROVIDER} ENABLE_OPENAI={settings.ENABLE_OPENAI}")
    print("=" * 72)

    passed = failed = 0

    for msg, suffix, must_not, expect in CASES:
        sid = f"stab_{suffix}"
        clear_conversation(sid)
        resp = await chatbot_response(sid, msg, database)
        mode = (resp.get("data", {}).get("context") or {}).get("assistant_mode", "")
        ok = (len(resp.get("data", {}).get("machines") or []) == 0) if must_not else True
        if expect and expect not in mode:
            ok = False
        passed += int(ok)
        failed += int(not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {msg[:48]:48} | {mode}")

    print("-" * 72)
    print("Conversational paraphrases")
    for msg, suffix, expect in PARAPHRASE_CONVERSATIONAL:
        r = await _check(msg, f"para_{suffix}", expect)
        passed += int(r["pass"])
        failed += int(not r["pass"])
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {msg[:48]:48} | {r['mode']}")

    print("-" * 72)
    print("Comparison paraphrases")
    for msg, suffix, expect in PARAPHRASE_COMPARE:
        r = await _check(msg, f"para_{suffix}", expect)
        passed += int(r["pass"])
        failed += int(not r["pass"])
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {msg[:48]:48} | {r['mode']}")

    print("-" * 72)
    print("Attribute paraphrases (after search context)")
    for msg, suffix, expect in PARAPHRASE_ATTRIBUTE:
        r = await _check(msg, f"para_{suffix}", expect, setup_search=True)
        passed += int(r["pass"])
        failed += int(not r["pass"])
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {msg[:48]:48} | {r['mode']}")

    print("-" * 72)
    print("Contextual chip follow-ups (after search context)")
    for msg, suffix, expect in PARAPHRASE_CONTEXTUAL:
        r = await _check(msg, f"para_{suffix}", expect, setup_search=True)
        passed += int(r["pass"])
        failed += int(not r["pass"])
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {msg[:48]:48} | {r['mode']}")

    print("=" * 72)
    print(f"Total passed: {passed} | failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
