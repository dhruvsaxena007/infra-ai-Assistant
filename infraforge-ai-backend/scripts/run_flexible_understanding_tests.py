#!/usr/bin/env python3
"""Flexible understanding stabilization — name intro, polite chat, broad machine, purpose."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.universal_turn_engine import analyze_universal_turn, extract_user_name
from app.chatbot.assistant_intelligence import (
    is_broad_vague_query,
    resolve_purpose_key,
)
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database


def _ctx(resp: dict) -> dict:
    return (resp.get("data") or {}).get("context") or {}


def _mode(resp: dict) -> str:
    return _ctx(resp).get("assistant_mode") or ""


def _msg(resp: dict) -> str:
    return (resp.get("data") or {}).get("message") or resp.get("message") or ""


def _machines(resp: dict) -> int:
    return len((resp.get("data") or {}).get("machines") or [])


def _sources(resp: dict) -> int:
    return len((resp.get("data") or {}).get("sources") or [])


async def _chat(sid: str, message: str, *, setup: str | None = None) -> dict:
    clear_conversation(sid)
    if setup:
        await chatbot_response(sid, setup, database)
    return await chatbot_response(sid, message, database)


def test_name_rules():
    cases = [
        ("hello myself dhruv", "Dhruv"),
        ("myself dhruv", "Dhruv"),
        ("hellow my name is dhruv", "Dhruv"),
    ]
    ok_all = True
    for text, expected in cases:
        name = extract_user_name(text)
        turn = analyze_universal_turn(text)
        ok = name == expected and turn.get("shape") == "conversational"
        ok_all = ok_all and ok
        print(f"[{'PASS' if ok else 'FAIL'}] name_rules {text!r} -> {name} shape={turn.get('shape')}")
    return ok_all


async def test_name_intro_e2e():
    sid = "flex_name"
    resp = await _chat(sid, "myself dhruv")
    msg = _msg(resp).lower()
    ok = (
        "dhruv" in msg
        and _mode(resp) == "conversational"
        and _machines(resp) == 0
        and _sources(resp) == 0
    )
    print(f"[{'PASS' if ok else 'FAIL'}] myself dhruv e2e | mode={_mode(resp)}")
    return ok


async def test_polite_conversation():
    sid = "flex_polite"
    resp = await _chat(sid, "its my pleasure to meet you")
    ok = (
        _mode(resp) == "conversational"
        and _machines(resp) == 0
        and _sources(resp) == 0
        and "likewise" in _msg(resp).lower()
    )
    print(f"[{'PASS' if ok else 'FAIL'}] pleasure to meet you | mode={_mode(resp)}")
    return ok


async def test_broad_machine():
    cases = ["i need a machine", "i want a machine", "machine chahiye"]
    ok_all = True
    for text in cases:
        sid = f"flex_broad_{hash(text) % 10000}"
        resp = await _chat(sid, text)
        msg = _msg(resp).lower()
        ok = (
            is_broad_vague_query(text)
            and _mode(resp) == "clarification"
            and "digging" in msg
            and "city" in msg
            and _machines(resp) == 0
            and "excavator" not in msg
        )
        ok_all = ok_all and ok
        print(f"[{'PASS' if ok else 'FAIL'}] broad {text!r} | mode={_mode(resp)}")
    return ok_all


async def test_purpose_digging():
    sid = "flex_dig"
    resp = await _chat(sid, "i need machine for digging road")
    msg = _msg(resp).lower()
    ok = (
        resolve_purpose_key("i need machine for digging road") == "digging"
        and _mode(resp) in ("clarification", "search", "no_result", "purpose_alternatives")
        and _machines(resp) <= 5
    )
    print(f"[{'PASS' if ok else 'FAIL'}] digging road purpose | mode={_mode(resp)}")
    return ok


async def test_hinglish_digging():
    sid = "flex_hin_dig"
    pk = resolve_purpose_key("mujhe road digging ke liye machine chahiye")
    ok = pk == "digging"
    print(f"[{'PASS' if ok else 'FAIL'}] hinglish road digging purpose={pk}")
    return ok


async def test_leveling():
    sid = "flex_level"
    pk = resolve_purpose_key("suggest me machine for leveling the road")
    resp = await _chat(sid, "suggest me machine for leveling the road")
    ok = pk == "leveling" and _mode(resp) in (
        "clarification", "search", "no_result", "purpose_alternatives",
    )
    print(f"[{'PASS' if ok else 'FAIL'}] leveling road | purpose={pk} mode={_mode(resp)}")
    return ok


async def test_pending_compaction():
    sid = "flex_comp"
    await _chat(sid, "i need a machine")
    resp = await chatbot_response(sid, "compaction", database)
    ok = (
        _mode(resp) in ("clarification", "search", "no_result", "purpose_alternatives")
        and _sources(resp) == 0
        and _ctx(resp).get("intent") not in ("unknown", "refund_return")
    )
    print(f"[{'PASS' if ok else 'FAIL'}] compaction pending | mode={_mode(resp)}")
    return ok


async def test_pending_city():
    sid = "flex_city"
    await _chat(sid, "i need a machine")
    await chatbot_response(sid, "digging", database)
    resp = await chatbot_response(sid, "in delhi", database)
    ok = (
        _mode(resp) in ("search", "no_result", "purpose_alternatives", "clarification")
        and _sources(resp) == 0
    )
    print(f"[{'PASS' if ok else 'FAIL'}] in delhi pending | mode={_mode(resp)}")
    return ok


async def test_thanks_and_wellbeing():
    ok_all = True
    for text in ("thank you", "how are you"):
        sid = f"flex_soc_{hash(text) % 10000}"
        resp = await _chat(sid, text)
        ok = _mode(resp) == "conversational" and _machines(resp) == 0
        ok_all = ok_all and ok
        print(f"[{'PASS' if ok else 'FAIL'}] social {text!r} | mode={_mode(resp)}")
    return ok_all


async def test_lifting_jaipur():
    sid = "flex_lift"
    pk = resolve_purpose_key("i need machinery for lifting in Jaipur")
    resp = await _chat(sid, "i need machinery for lifting in Jaipur")
    ok = pk == "lifting" and _mode(resp) in (
        "search", "no_result", "purpose_alternatives", "clarification",
    )
    print(f"[{'PASS' if ok else 'FAIL'}] lifting jaipur | purpose={pk} mode={_mode(resp)}")
    return ok


async def main():
    results = [
        test_name_rules(),
        await test_name_intro_e2e(),
        await test_polite_conversation(),
        await test_broad_machine(),
        await test_purpose_digging(),
        await test_hinglish_digging(),
        await test_leveling(),
        await test_pending_compaction(),
        await test_pending_city(),
        await test_thanks_and_wellbeing(),
        await test_lifting_jaipur(),
    ]
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\nFlexible understanding: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
