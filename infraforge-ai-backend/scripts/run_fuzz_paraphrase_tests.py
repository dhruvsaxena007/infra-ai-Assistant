#!/usr/bin/env python3
"""
Fuzz paraphrase tests — NOT the user's screenshot examples.
Proves semantic + rules handle unseen wording variants.
"""

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

# Each tuple: (message, expected_mode_substring, setup_search_first)
FUZZ = [
    # Name intro — never listed in code as exact strings
    ("im called suresh", "conversational", False),
    ("mera naam ankit hai", "conversational", False),
    ("they say im kavita", "conversational", False),
    ("people call me by the name vikram", "conversational", False),
    ("my name iz deepak", "conversational", False),
    # Wellbeing
    ("u doing ok", "conversational", False),
    ("hope ur alright", "conversational", False),
    ("main thik hoon aur aap", "conversational", False),
    # Compare — indirect Hinglish
    ("tata ya jcb kaun sa behtar hai backhoe ke liye", "comparison", False),
    ("between volvo and komatsu which one should i take", "comparison", False),
    ("generally hyundai rollers better or cat", "comparison", False),
    # Attribute after context
    ("iskaa weight kya hai", "machine_detail", True),
    ("mileage kitni hai is machine ki", "machine_detail", True),
    ("can u tell me more about the first one", "machine_detail", True),
    # Contextual refine
    ("kuch sasta dikhao", "cheaper_options", True),
    ("dusra similar option", "comparison", True),
    ("owner se kaise baat karu", "contact_owner", True),
    # Support — must NOT search
    ("mera payment fail ho gaya", "payment", False),
    ("refund chahiye order ka", "refund", False),
]


async def run_one(msg: str, expect: str, setup: bool) -> bool:
    sid = f"fuzz_{abs(hash(msg)) % 10**8}"
    clear_conversation(sid)
    if setup:
        await chatbot_response(sid, "road roller in delhi under 10000", database)
    resp = await chatbot_response(sid, msg, database)
    mode = (resp.get("data", {}).get("context") or {}).get("assistant_mode", "")
    ok = expect in mode
    if expect == "conversational" and len(resp.get("data", {}).get("machines") or []) > 0:
        ok = False
    print(f"[{'PASS' if ok else 'FAIL'}] {msg[:52]:52} | {mode}")
    return ok


async def main() -> int:
    print("=" * 72)
    print("Fuzz Paraphrase Tests (unseen wording)")
    print(f"GROQ universal={settings.groq_universal_enabled} key={'yes' if settings.GROQ_API_KEY else 'no'}")
    print("=" * 72)
    passed = failed = 0
    for msg, expect, setup in FUZZ:
        ok = await run_one(msg, expect, setup)
        passed += int(ok)
        failed += int(not ok)
    print("=" * 72)
    print(f"Passed: {passed} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
