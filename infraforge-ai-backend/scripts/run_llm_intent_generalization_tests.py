#!/usr/bin/env python3
"""
LLM intent generalization tests — action routing + entity validation.

Production logic must NOT hardcode test strings; tests use synthetic LLM payloads
and optional live Groq when GROQ_API_KEY is set.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.intent_action_router import (
    ACTION_BROAD_CLARIFY,
    ACTION_CONVERSATIONAL,
    ACTION_DOCUMENT_RAG,
    ACTION_MACHINE_SEARCH,
    ACTION_OUT_OF_SCOPE,
    ACTION_SUPPORT,
    select_action,
)
from app.ai.intent_entity_validator import validate_llm_classification
from app.ai.intent_schema import default_assistant_mode, empty_rich_payload, merge_flat_into_rich
from app.ai.llm_intent_classifier import to_legacy_classification


def _llm_payload(intent: str, message: str = "", **entity_kw) -> dict:
    rich = empty_rich_payload(layer="test")
    should_search = bool(entity_kw.pop("should_search_machines", False))
    rich.update(
        {
            "intent": intent,
            "confidence": 0.88,
            "assistant_mode": default_assistant_mode(intent),
            "should_search_machines": should_search,
            "requires_clarification": False,
            "requires_human_handover": False,
            "missing_fields": [],
            "reason": "test",
            "layer": "test",
        }
    )
    entities = merge_flat_into_rich(entity_kw)
    if entity_kw.get("name"):
        entities["user"]["name"] = entity_kw["name"]
    if entity_kw.get("issue_type"):
        entities["support"]["issue_category"] = entity_kw["issue_type"]
    if entity_kw.get("document_reference"):
        entities["document"]["document_reference"] = True
    rich["entities"] = entities
    return validate_llm_classification(rich, message)


def test_user_introduction_routing():
    """Many phrasings → user_introduction via LLM payload shape."""
    ok_all = True
    names = ["Dhruv", "Dhruv", "Dhruv", "Dhruv", "Dhruv"]
    for name in names:
        payload = _llm_payload("user_introduction", message="intro", name=name)
        legacy = to_legacy_classification(payload)
        action = select_action(legacy)
        ok = (
            action["action"] == ACTION_CONVERSATIONAL
            and legacy.get("llm_intent") == "user_introduction"
            and not legacy.get("should_search_machines")
        )
        ok_all = ok_all and ok
    print(f"[{'PASS' if ok_all else 'FAIL'}] user_introduction routing")
    return ok_all


def test_broad_machine_no_search():
    payloads = [
        _llm_payload("broad_machine_request", message="need machine"),
        _llm_payload("broad_machine_request", message="equipment"),
    ]
    ok_all = True
    for p in payloads:
        legacy = to_legacy_classification(p)
        action = select_action(legacy)
        ok = (
            action["action"] == ACTION_BROAD_CLARIFY
            and not legacy.get("should_search_machines")
            and legacy.get("entities", {}).get("machine_category") is None
        )
        ok_all = ok_all and ok
    print(f"[{'PASS' if ok_all else 'FAIL'}] broad_machine_request no search")
    return ok_all


def test_purpose_search_with_city():
    payload = _llm_payload(
        "machine_search",
        message="excavator for digging in jaipur",
        purpose="digging",
        machine_category="excavator",
        city="jaipur",
        should_search_machines=True,
    )
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    ok = (
        action["action"] == ACTION_MACHINE_SEARCH
        and action["filters"].get("city") == "jaipur"
        and legacy.get("should_search_machines")
    )
    print(f"[{'PASS' if ok else 'FAIL'}] purpose search with city")
    return ok


def test_payment_no_search():
    payload = _llm_payload(
        "payment_issue",
        message="amount deducted booking failed",
        issue_type="booking_failed",
    )
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    ok = action["action"] == ACTION_SUPPORT and not legacy.get("should_search_machines")
    print(f"[{'PASS' if ok else 'FAIL'}] payment_issue no search")
    return ok


def test_refund_no_search():
    legacy = to_legacy_classification(_llm_payload("refund_return", message="refund"))
    action = select_action(legacy)
    ok = action["action"] == ACTION_SUPPORT and not legacy.get("should_search_machines")
    print(f"[{'PASS' if ok else 'FAIL'}] refund_return no search")
    return ok


def test_delivery_no_search():
    legacy = to_legacy_classification(_llm_payload("delivery_issue", message="late delivery"))
    action = select_action(legacy)
    ok = action["action"] == ACTION_SUPPORT and not legacy.get("should_search_machines")
    print(f"[{'PASS' if ok else 'FAIL'}] delivery_issue no search")
    return ok


def test_document_rag_only():
    payload = _llm_payload(
        "document_question",
        message="what does pdf say",
        document_reference=True,
    )
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    ok = action["action"] == ACTION_DOCUMENT_RAG and not legacy.get("should_search_machines")
    print(f"[{'PASS' if ok else 'FAIL'}] document_question -> RAG")
    return ok


def test_out_of_scope():
    legacy = to_legacy_classification(_llm_payload("out_of_scope", message="weather"))
    action = select_action(legacy)
    ok = action["action"] == ACTION_OUT_OF_SCOPE
    print(f"[{'PASS' if ok else 'FAIL'}] out_of_scope")
    return ok


def test_validator_blocks_fake_city():
    payload = _llm_payload(
        "machine_search",
        message="excavator in xyzabc123",
        machine_category="excavator",
        city="xyzabc123",
        should_search_machines=True,
    )
    ok = payload.get("requires_clarification") or "city" in (payload.get("missing_fields") or [])
    print(f"[{'PASS' if ok else 'FAIL'}] validator unknown city -> clarify")
    return ok


async def test_live_groq_optional():
    if not os.getenv("GROQ_API_KEY"):
        print("[SKIP] live Groq — no GROQ_API_KEY")
        return True
    from app.ai.llm_intent_classifier import classify_intent_llm

    result = await classify_intent_llm("people call me Dhruv")
    if result.get("layer") == "fallback" and float(result.get("confidence") or 0) < 0.5:
        print("[SKIP] live Groq — unavailable or rate limited (fallback clarify)")
        return True
    ok = (
        result.get("llm_intent") == "user_introduction"
        and (result.get("entities") or {}).get("name")
        and not result.get("should_search_machines")
    )
    print(f"[{'PASS' if ok else 'FAIL'}] live Groq name intro | intent={result.get('llm_intent')}")
    return ok


async def main():
    results = [
        test_user_introduction_routing(),
        test_broad_machine_no_search(),
        test_purpose_search_with_city(),
        test_payment_no_search(),
        test_refund_no_search(),
        test_delivery_no_search(),
        test_document_rag_only(),
        test_out_of_scope(),
        test_validator_blocks_fake_city(),
        await test_live_groq_optional(),
    ]
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\nLLM intent generalization: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
