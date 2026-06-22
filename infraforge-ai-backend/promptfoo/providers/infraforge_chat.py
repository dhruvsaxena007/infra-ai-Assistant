"""
Promptfoo custom provider — calls InfraForge chatbot directly (no HTTP server).

Usage in promptfoo.yaml:
  providers:
    - id: file://providers/infraforge_chat.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Backend root (infraforge-ai-backend/)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402
from app.utils.reference_cache import reset_reference_cache  # noqa: E402

import app.database.mongodb as _mongo_mod  # noqa: E402

_loop: asyncio.AbstractEventLoop | None = None
_motor_loop_id: int | None = None


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Promptfoo calls call_api many times; reuse one loop per worker process."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _ensure_database():
    """Rebind Motor when the asyncio loop changes (avoids 'Event loop is closed')."""
    global _motor_loop_id
    loop = _get_event_loop()
    loop_id = id(loop)
    if _motor_loop_id == loop_id:
        return
    _mongo_mod.client = AsyncIOMotorClient(settings.MONGODB_URL)
    _mongo_mod.database = _mongo_mod.client[settings.DATABASE_NAME]
    reset_reference_cache()
    _motor_loop_id = loop_id


def _database():
    _ensure_database()
    return _mongo_mod.database


def _get(resp: dict, *keys, default=None):
    cur = resp
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _mode(resp: dict) -> str:
    return _get(resp, "data", "context", "assistant_mode") or _get(resp, "data", "assistant_mode") or ""


def _cat(resp: dict) -> str:
    return (_get(resp, "data", "filters", "category") or "").lower()


def _city(resp: dict) -> str:
    return (_get(resp, "data", "filters", "city") or "").lower()


def _machines(resp: dict) -> list:
    return _get(resp, "data", "machines") or []


def _msg(resp: dict) -> str:
    return resp.get("message") or _get(resp, "data", "message") or ""


def _lang(resp: dict) -> str:
    return _get(resp, "data", "context", "reply_language") or ""


def _ctx(resp: dict) -> dict:
    return _get(resp, "data", "context") or {}


def check_expect(resp: dict, expect: dict) -> tuple[bool, list[str]]:
    """Return (pass, failure_reasons)."""
    failures: list[str] = []

    if "category" in expect:
        got = _cat(resp)
        want = expect["category"].lower()
        if got != want:
            failures.append(f"category: got '{got}' want '{want}'")

    if "city" in expect:
        got = _city(resp)
        want = expect["city"].lower()
        if got != want:
            failures.append(f"city: got '{got}' want '{want}'")

    if "assistant_mode" in expect:
        got = _mode(resp)
        want = expect["assistant_mode"]
        if got != want:
            failures.append(f"assistant_mode: got '{got}' want '{want}'")

    if "not_assistant_mode" in expect:
        got = _mode(resp)
        bad = expect["not_assistant_mode"]
        if got == bad:
            failures.append(f"assistant_mode should not be '{bad}'")

    if "reply_language" in expect:
        got = _lang(resp)
        want = expect["reply_language"]
        if got != want:
            failures.append(f"reply_language: got '{got}' want '{want}'")

    if "reply_language_in" in expect:
        got = _lang(resp)
        allowed = expect["reply_language_in"]
        if got not in allowed:
            failures.append(f"reply_language: got '{got}' not in {allowed}")

    if expect.get("machines_max") is not None:
        n = len(_machines(resp))
        if n > expect["machines_max"]:
            failures.append(f"machines count {n} > max {expect['machines_max']}")

    if expect.get("machines_min") is not None:
        n = len(_machines(resp))
        if n < expect["machines_min"]:
            failures.append(f"machines count {n} < min {expect['machines_min']}")

    if expect.get("has_corrections"):
        ctx = _ctx(resp)
        if not ctx.get("corrected_query") and not ctx.get("corrections"):
            failures.append("expected spell corrections in context")

    if "message_contains" in expect:
        needle = expect["message_contains"].lower()
        if needle not in _msg(resp).lower():
            failures.append(f"message missing '{needle}'")

    return len(failures) == 0, failures


async def _run_turns(session_id: str, turns: list[dict], clear: bool) -> dict:
    db = _database()
    if clear:
        clear_conversation(session_id)

    last_resp = {}
    all_failures: list[str] = []

    for i, t in enumerate(turns):
        msg = t["message"]
        last_resp = await chatbot_response(session_id, msg, db)
        expect = t.get("expect")
        if expect:
            ok, fails = check_expect(last_resp, expect)
            if not ok:
                all_failures.extend([f"turn {i + 1} ({msg!r}): {f}" for f in fails])

    if all_failures:
        return {
            "pass": False,
            "failures": all_failures,
            "response": last_resp,
        }
    return {"pass": True, "response": last_resp}


async def _run_single(session_id: str, message: str, expect: dict, clear: bool) -> dict:
    db = _database()
    if clear:
        clear_conversation(session_id)
    resp = await chatbot_response(session_id, message, db)
    ok, failures = check_expect(resp, expect)
    return {
        "pass": ok,
        "failures": failures,
        "response": resp,
    }


def call_api(prompt, options, context):  # noqa: ARG001 — promptfoo signature
    """Promptfoo entry point."""
    vars_ = (context or {}).get("vars") or {}
    session_id = vars_.get("session_id") or "promptfoo_default"
    clear = vars_.get("clear_session", True)
    if isinstance(clear, str):
        clear = clear.lower() == "true"

    turns_json = vars_.get("turns_json")
    expect_json = vars_.get("expect_json") or "{}"
    expect = json.loads(expect_json) if isinstance(expect_json, str) else (expect_json or {})

    loop = _get_event_loop()
    _ensure_database()
    try:
        if turns_json:
            turns = json.loads(turns_json) if isinstance(turns_json, str) else turns_json
            result = loop.run_until_complete(_run_turns(session_id, turns, clear))
        else:
            message = vars_.get("message") or prompt
            result = loop.run_until_complete(_run_single(session_id, message, expect, clear))
    except Exception as exc:  # noqa: BLE001
        result = {"pass": False, "failures": [str(exc)], "response": {}}

    # Promptfoo expects string output for javascript asserts
    return {"output": json.dumps(result, default=str)}
