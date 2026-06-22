#!/usr/bin/env python3
"""Dynamic response system tests — Response Plan, memory, fallback, compatibility."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.conversation_aware_response import generate_conversation_aware_response
from app.ai.dynamic_response_generator import compute_response_signature, generate_dynamic_response
from app.ai.intent_action_router import ACTION_BROAD_CLARIFY, ACTION_SUPPORT, select_action
from app.ai.intent_entity_validator import validate_llm_classification
from app.ai.intent_schema import default_assistant_mode, empty_rich_payload, merge_flat_into_rich
from app.ai.llm_intent_classifier import to_legacy_classification
from app.ai.response_memory import get_response_memory, record_response_memory
from app.ai.response_plan import build_response_plan, response_goal_for_intent


def _rich_payload(intent: str, message: str = "", **flat_kw) -> dict:
    rich = empty_rich_payload(layer="test")
    rich.update(
        {
            "intent": intent,
            "confidence": float(flat_kw.pop("confidence", 0.88)),
            "assistant_mode": flat_kw.pop("assistant_mode", default_assistant_mode(intent)),
            "should_search_machines": flat_kw.pop("should_search_machines", False),
            "requires_clarification": flat_kw.pop("requires_clarification", False),
            "missing_fields": list(flat_kw.pop("missing_fields", [])),
            "reason": "test",
        }
    )
    entities = merge_flat_into_rich(flat_kw)
    if flat_kw.get("issue_subcategory"):
        entities["support"]["issue_subcategory"] = flat_kw["issue_subcategory"]
    rich["entities"] = entities
    return validate_llm_classification(rich, message)


def test_response_plan_schema():
    plan = build_response_plan(
        response_goal="collect_machine_requirements",
        intent="broad_machine_request",
        assistant_mode="clarification",
        language="english",
        user_message="i need a machine",
        draft_message="What work and city?",
        session_context={"session_id": "s1", "user_name": "Dhruv"},
        response_memory=get_response_memory({}),
    )
    ok = (
        plan.get("response_goal") == "collect_machine_requirements"
        and plan.get("rules", {}).get("do_not_invent_data") is True
        and "city" in " ".join(plan.get("must_ask") or [])
        and plan.get("known_context", {}).get("user_name") == "Dhruv"
    )
    print(f"[{'PASS' if ok else 'FAIL'}] response plan schema")
    return ok


def test_memory_avoids_signature_repetition():
    ctx: dict = {}
    sigs = set()
    for i in range(5):
        ctx = record_response_memory(
            ctx,
            intent="greeting",
            response_goal="greet_user",
            message=f"Hello variant {i}",
            response_signature=compute_response_signature(f"Hello variant {i}", "greet_user"),
        )
        mem = get_response_memory(ctx)
        sigs.update(mem.get("recent_response_signatures") or [])
    ok = len(sigs) >= 3
    print(f"[{'PASS' if ok else 'FAIL'}] response memory tracks signatures ({len(sigs)} unique)")
    return ok


def test_repeated_intent_not_identical():
    messages = set()
    for turn in range(5):
        out = generate_conversation_aware_response(
            intent="greeting",
            assistant_mode="conversation",
            response_goal="greet_user",
            session_context={"turn_count": turn, "session_id": "sess-a"},
            session_id="sess-a",
        )
        messages.add(out["message"])
    ok = len(messages) >= 2
    print(f"[{'PASS' if ok else 'FAIL'}] repeated intent varies ({len(messages)} unique)")
    return ok


def test_broad_no_excavator_assumption():
    payload = _rich_payload("broad_machine_request", message="i need a machine")
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    ok = (
        action["action"] == ACTION_BROAD_CLARIFY
        and legacy.get("entities", {}).get("machine_category") is None
    )
    print(f"[{'PASS' if ok else 'FAIL'}] broad request no category assumption")
    return ok


def test_payment_no_search():
    legacy = to_legacy_classification(_rich_payload("payment_issue", message="payment failed"))
    action = select_action(legacy)
    ok = action["action"] == ACTION_SUPPORT and not legacy.get("should_search_machines")
    print(f"[{'PASS' if ok else 'FAIL'}] payment issue no machine search")
    return ok


def test_refund_no_false_claim():
    plan = build_response_plan(
        response_goal="collect_booking_id",
        intent="refund_return",
        assistant_mode="refund_return",
        draft_message="Share booking ID. Refund eligibility depends on policy.",
        tool_result={"message": "Share booking ID. Refund eligibility depends on policy."},
    )
    ok = "refund_processed" in (plan.get("must_not_claim") or [])
    print(f"[{'PASS' if ok else 'FAIL'}] refund plan must_not_claim processed")
    return ok


def test_factual_draft_preserved_in_fallback():
    draft = "Found JCB 220X in Jaipur at INR 45000/day."
    plan = build_response_plan(
        response_goal="show_machine_results",
        intent="machine_search",
        assistant_mode="search",
        draft_message=draft,
        tool_result={"message": draft, "machines": [{"name": "JCB 220X", "price_per_day": 45000}]},
    )
    from app.ai.dynamic_response_generator import _local_fallback_from_plan

    out = _local_fallback_from_plan(plan, session_id="s1")
    ok = "45000" in out["message"] and "JCB" in out["message"]
    print(f"[{'PASS' if ok else 'FAIL'}] machine result preserves tool_result facts")
    return ok


async def test_llm_fallback_when_unavailable():
    plan = build_response_plan(
        response_goal="greet_user",
        intent="greeting",
        assistant_mode="greeting",
        draft_message="Hello!",
    )
    with patch("app.ai.dynamic_response_generator.settings") as mock_settings:
        mock_settings.use_llm_response_generation = True
        mock_settings.GROQ_API_KEY = None
        mock_settings.ENVIRONMENT = "development"
        out = await generate_dynamic_response(plan, "hi", {}, [])
    ok = out.get("fallback_used") is True and out.get("message")
    print(f"[{'PASS' if ok else 'FAIL'}] LLM unavailable uses local fallback")
    return ok


def test_frontend_shape_compatible():
    out = generate_conversation_aware_response(
        intent="greeting",
        assistant_mode="greeting",
        response_goal="greet_user",
        session_id="s1",
    )
    ok = isinstance(out.get("message"), str) and isinstance(out.get("suggestions"), list)
    print(f"[{'PASS' if ok else 'FAIL'}] response shape has message + suggestions")
    return ok


def test_goal_mapping():
    ok = response_goal_for_intent("payment_issue") == "collect_transaction_id"
    print(f"[{'PASS' if ok else 'FAIL'}] response_goal_for_intent mapping")
    return ok


async def main() -> int:
    tests = [
        test_response_plan_schema,
        test_memory_avoids_signature_repetition,
        test_repeated_intent_not_identical,
        test_broad_no_excavator_assumption,
        test_payment_no_search,
        test_refund_no_false_claim,
        test_factual_draft_preserved_in_fallback,
        test_frontend_shape_compatible,
        test_goal_mapping,
    ]
    passed = sum(1 for t in tests if t())
    passed += 1 if await test_llm_fallback_when_unavailable() else 0
    total = len(tests) + 1
    print(f"\nDynamic response tests: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
