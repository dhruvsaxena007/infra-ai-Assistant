"""
Phase 9 — Old template / dead code cleanup verification.

Run: python scripts/test_cleanup_baseline.py
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import unittest.mock as mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("ASSISTANT_DEBUG", "true")


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


def test_dead_modules_removed(c: Counter) -> None:
    dead = [
        "app.ai.llm_response_polisher",
    ]
    for mod in dead:
        try:
            importlib.import_module(mod)
            c.record(f"dead module gone: {mod}", False, "still importable")
        except ImportError:
            c.record(f"dead module gone: {mod}", True)


def test_config_modes(c: Counter) -> None:
    from app.core.config import settings

    config_path = os.path.join(PROJECT_ROOT, "app", "core", "config.py")
    with open(config_path, encoding="utf-8") as fh:
        src = fh.read()
    c.record("rules_first default in config", 'or "rules_first"' in src)
    c.record("llm_first property exists", hasattr(settings, "llm_intent_first"))
    c.record("llm_shadow property exists", hasattr(settings, "llm_shadow"))
    c.record("LLM_RESPONSE_POLISH removed", "LLM_RESPONSE_POLISH" not in src)
    c.record("USE_CONVERSATION_AWARE removed", "USE_CONVERSATION_AWARE_RESPONSE" not in src)
    c.record("ENABLE_OPENAI false default", not settings.ENABLE_OPENAI)


def test_suggestions_consolidated(c: Counter) -> None:
    from app.ai.conversation_aware_response import _SUGGESTIONS
    from app.ai.response_plan import GOAL_SUGGESTIONS

    c.record("suggestions share GOAL_SUGGESTIONS", _SUGGESTIONS is GOAL_SUGGESTIONS)
    c.record("recovery goal chips present", bool(GOAL_SUGGESTIONS.get("explain_no_result_with_recovery")))


async def test_gateway_still_used(c: Counter) -> None:
    from app.ai.assistant_response_gateway import deliver_assistant_response

    out = await deliver_assistant_response(
        session_id="p9_gateway",
        user_message="hello",
        draft_message="Hello",
        response_goal="greet_user",
        intent="greeting",
        assistant_mode="greeting",
        session_context={"session_id": "p9_gateway"},
    )
    c.record("gateway_used", bool(out.get("gateway_used")))
    c.record("response_plan attached", bool(out.get("response_plan")))


async def test_local_fallback_on_llm_fail(c: Counter) -> None:
    from app.ai.dynamic_response_generator import generate_dynamic_response
    from app.ai.response_plan import build_response_plan

    plan = build_response_plan(
        response_goal="greet_user",
        intent="greeting",
        assistant_mode="greeting",
        draft_message="Hello draft",
    )
    with mock.patch(
        "app.ai.dynamic_response_generator._call_llm_generator",
        new_callable=mock.AsyncMock,
        return_value=None,
    ):
        out = await generate_dynamic_response(
            user_message="hi",
            response_plan=plan,
            session_context={"session_id": "p9_fallback"},
        )
    c.record("local fallback message", bool(out.get("message")))
    c.record("fallback_used flag", bool(out.get("fallback_used")))


async def test_recovery_engine_importable(c: Counter) -> None:
    from app.ai.no_result_recovery import run_no_result_recovery, empty_recovery_output

    out = await run_no_result_recovery(
        mock.MagicMock(),
        intent="payment_issue",
        filters={},
    )
    c.record("recovery engine runs", out.get("recovery_type") == "support_missing_details")
    c.record("empty_recovery_output", "recovery_type" in empty_recovery_output())


async def test_chat_integration_trace(c: Counter) -> None:
    from app.ai.assistant_debug_trace import get_last_debug_trace
    from app.chatbot.chatbot_service import chatbot_response
    from app.chatbot.memory import clear_conversation
    from app.database.mongodb import database

    sid = "p9_trace"
    clear_conversation(sid)
    await chatbot_response(sid, "i need a machine for digging in Jaipur", database)
    trace = get_last_debug_trace() or {}
    c.record("debug trace classification", bool(trace.get("classification")))
    c.record("debug trace permission", bool(trace.get("permission")))
    c.record("debug trace state", bool(trace.get("state")))
    resp = trace.get("response") or {}
    c.record(
        "gateway on search path",
        resp.get("gateway_used") is True or resp.get("response_plan_created") is True,
        str(resp.get("gateway_used")),
    )


async def main() -> int:
    c = Counter()
    print("\n=== Phase 9 — Cleanup Verification ===\n")

    test_dead_modules_removed(c)
    test_config_modes(c)
    test_suggestions_consolidated(c)
    await test_gateway_still_used(c)
    await test_local_fallback_on_llm_fail(c)
    await test_recovery_engine_importable(c)
    await test_chat_integration_trace(c)

    print(f"\nPhase 9 cleanup: {c.passed} passed, {c.failed} failed\n")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
