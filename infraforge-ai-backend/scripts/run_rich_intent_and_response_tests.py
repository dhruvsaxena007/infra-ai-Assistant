#!/usr/bin/env python3
"""Rich intent JSON v1.0 + global conversation-aware response variation tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.conversation_aware_response import generate_conversation_aware_response
from app.ai.intent_action_router import (
    ACTION_BROAD_CLARIFY,
    ACTION_CLARIFY,
    ACTION_DOCUMENT_RAG,
    ACTION_MACHINE_SEARCH,
    ACTION_SUPPORT,
    select_action,
)
from app.ai.intent_entity_validator import validate_llm_classification
from app.ai.intent_schema import default_assistant_mode, empty_rich_payload, merge_flat_into_rich
from app.ai.llm_intent_classifier import to_legacy_classification


def _rich_payload(intent: str, message: str = "", **flat_kw) -> dict:
    rich = empty_rich_payload(layer="test")
    rich.update(
        {
            "intent": intent,
            "confidence": float(flat_kw.pop("confidence", 0.88)),
            "assistant_mode": flat_kw.pop("assistant_mode", default_assistant_mode(intent)),
            "should_search_machines": flat_kw.pop("should_search_machines", False),
            "should_use_rag": flat_kw.pop("should_use_rag", False),
            "requires_clarification": flat_kw.pop("requires_clarification", False),
            "requires_human_handover": flat_kw.pop("requires_handover", False),
            "missing_fields": list(flat_kw.pop("missing_fields", [])),
            "reason": "test",
        }
    )
    entities = merge_flat_into_rich(flat_kw)
    if flat_kw.get("name"):
        entities["user"]["name"] = flat_kw["name"]
    if flat_kw.get("issue_type"):
        entities["support"]["issue_category"] = flat_kw["issue_type"]
    if flat_kw.get("issue_subcategory"):
        entities["support"]["issue_subcategory"] = flat_kw["issue_subcategory"]
    if flat_kw.get("document_reference"):
        entities["document"]["document_reference"] = True
        entities["document"]["question_about_document"] = True
    rich["entities"] = entities
    return validate_llm_classification(rich, message)


def test_payment_issue_subcategory_and_missing_txn():
    payload = _rich_payload(
        "payment_issue",
        message="amount deducted but booking failed",
        issue_type="payment",
        issue_subcategory="booking_failed",
    )
    support = payload["entities"]["support"]
    ok = (
        support.get("issue_subcategory") == "booking_failed"
        and "support.transaction_id" in payload.get("missing_fields", [])
        and not payload.get("should_search_machines")
    )
    print(f"[{'PASS' if ok else 'FAIL'}] payment issue subcategory + missing transaction")
    return ok


def test_broad_machine_no_search():
    payload = _rich_payload("broad_machine_request", message="i need a machine")
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    ok = (
        action["action"] == ACTION_BROAD_CLARIFY
        and not legacy.get("should_search_machines")
        and legacy.get("entities", {}).get("machine_category") is None
        and "purpose_or_category" in (legacy.get("missing_fields") or [])
    )
    print(f"[{'PASS' if ok else 'FAIL'}] broad machine request no search")
    return ok


def test_machine_search_valid_filters():
    payload = _rich_payload(
        "machine_search",
        message="excavator in jaipur",
        machine_category="excavator",
        city="jaipur",
        should_search_machines=True,
    )
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    sf = legacy.get("search_filters") or {}
    ok = (
        action["action"] == ACTION_MACHINE_SEARCH
        and sf.get("category") == "excavator"
        and sf.get("city") == "jaipur"
        and legacy.get("should_search_machines")
    )
    print(f"[{'PASS' if ok else 'FAIL'}] machine search valid search_filters")
    return ok


def test_document_rag_not_search():
    payload = _rich_payload(
        "document_question",
        message="what does my pdf say",
        document_reference=True,
        should_use_rag=True,
    )
    legacy = to_legacy_classification(payload)
    action = select_action(legacy)
    ok = action["action"] == ACTION_DOCUMENT_RAG and not legacy.get("should_search_machines")
    print(f"[{'PASS' if ok else 'FAIL'}] document question RAG only")
    return ok


def test_support_never_searches():
    ok_all = True
    for intent in ("payment_issue", "refund_return", "delivery_issue", "invoice_issue"):
        legacy = to_legacy_classification(_rich_payload(intent, message=intent))
        action = select_action(legacy)
        ok = action["action"] == ACTION_SUPPORT and not legacy.get("should_search_machines")
        ok_all = ok_all and ok
    print(f"[{'PASS' if ok_all else 'FAIL'}] support intents never search")
    return ok_all


def test_invalid_city_triggers_clarification():
    payload = _rich_payload(
        "machine_search",
        message="excavator in atlantis",
        machine_category="excavator",
        city="atlantis",
        should_search_machines=True,
    )
    legacy = to_legacy_classification(payload)
    ok = (
        not legacy.get("should_search_machines")
        and legacy.get("requires_clarification")
        and "invalid_city" in " ".join(legacy.get("validation_notes") or [])
    )
    print(f"[{'PASS' if ok else 'FAIL'}] invalid city triggers clarification")
    return ok


def test_greeting_variation():
    messages = set()
    for turn in range(5):
        out = generate_conversation_aware_response(
            intent="greeting",
            assistant_mode="conversation",
            response_goal="greet_user",
            session_context={"turn_count": turn, "recent_variant_ids": list(messages)[-3:]},
            session_id="sess-greet",
        )
        messages.add(out["message"])
    ok = len(messages) >= 2
    print(f"[{'PASS' if ok else 'FAIL'}] greeting responses vary ({len(messages)} unique)")
    return ok


def test_broad_request_varies_but_asks_purpose_city():
    messages = []
    for turn in range(5):
        out = generate_conversation_aware_response(
            intent="broad_machine_request",
            assistant_mode="clarification",
            response_goal="collect_machine_requirements",
            session_context={"turn_count": turn},
            session_id="sess-broad",
        )
        messages.append(out["message"])
    combined = " ".join(messages).lower()
    ok = len(set(messages)) >= 2 and ("city" in combined or "location" in combined)
    print(f"[{'PASS' if ok else 'FAIL'}] broad_machine_request varies and asks purpose/city")
    return ok


def test_payment_varies_but_asks_ids():
    messages = []
    for turn in range(5):
        out = generate_conversation_aware_response(
            intent="payment_issue",
            assistant_mode="support",
            response_goal="collect_transaction_id",
            session_context={"turn_count": turn},
            session_id="sess-pay",
            sentiment="frustrated" if turn % 2 else "neutral",
        )
        messages.append(out["message"])
    combined = " ".join(messages).lower()
    ok = len(set(messages)) >= 2 and ("booking" in combined or "transaction" in combined)
    print(f"[{'PASS' if ok else 'FAIL'}] payment_issue varies and asks transaction/booking")
    return ok


def test_refund_no_false_claim():
    messages = []
    for turn in range(4):
        out = generate_conversation_aware_response(
            intent="refund_return",
            assistant_mode="support",
            response_goal="collect_booking_id",
            session_context={"turn_count": turn},
            session_id="sess-refund",
        )
        messages.append(out["message"].lower())
    ok = all("processed" not in m and "refunded" not in m for m in messages)
    print(f"[{'PASS' if ok else 'FAIL'}] refund_return does not claim refund processed")
    return ok


def test_no_result_varies_safe_suggestions():
    draft = "No excavator found in Jaipur right now."
    messages = []
    suggestions = set()
    for turn in range(4):
        out = generate_conversation_aware_response(
            intent="machine_search",
            assistant_mode="no_result",
            response_goal="explain_no_result",
            draft_message=draft,
            session_context={"turn_count": turn},
            session_id="sess-nores",
        )
        messages.append(out["message"])
        suggestions.update(out.get("suggestions") or [])
    ok = draft in messages[0] and len(suggestions) >= 2
    print(f"[{'PASS' if ok else 'FAIL'}] no_result keeps facts and safe suggestions")
    return ok


def test_document_does_not_invent_sources():
    draft = "Section 4 mentions a 30-day rental term."
    out = generate_conversation_aware_response(
        intent="document_question",
        assistant_mode="document_qa",
        response_goal="answer_document_question",
        draft_message=draft,
        tool_result={"sources": [{"title": "uploaded.pdf"}]},
        session_id="sess-doc",
    )
    ok = draft in out["message"] and "uploaded.pdf" not in out["message"]
    print(f"[{'PASS' if ok else 'FAIL'}] document response does not invent sources in message")
    return ok


def test_machine_result_preserves_prices():
    draft = "Found 2 excavators in Jaipur. JCB 220X at INR 45000/day."
    out = generate_conversation_aware_response(
        intent="machine_search",
        assistant_mode="search",
        response_goal="show_machine_results",
        draft_message=draft,
        tool_result={"machines": [{"name": "JCB 220X", "price": 45000}]},
        session_id="sess-res",
    )
    ok = "45000" in out["message"] and "JCB 220X" in out["message"]
    print(f"[{'PASS' if ok else 'FAIL'}] machine result preserves names and prices")
    return ok


def test_name_not_every_sentence():
    with_name = generate_conversation_aware_response(
        intent="broad_machine_request",
        assistant_mode="clarification",
        response_goal="collect_machine_requirements",
        entities={"name": "Dhruv"},
        session_context={"turn_count": 0},
        session_id="sess-name-a",
    )
    without_name = generate_conversation_aware_response(
        intent="broad_machine_request",
        assistant_mode="clarification",
        response_goal="collect_machine_requirements",
        entities={"name": "Dhruv"},
        session_context={"turn_count": 1},
        session_id="sess-name-b",
    )
    ok = "Dhruv" not in with_name["message"] or "Dhruv" not in without_name["message"]
    print(f"[{'PASS' if ok else 'FAIL'}] user name not forced in every sentence")
    return ok


def test_frustrated_gets_empathetic():
    out = generate_conversation_aware_response(
        intent="payment_issue",
        assistant_mode="support",
        response_goal="collect_transaction_id",
        sentiment="frustrated",
        session_context={"turn_count": 0},
        session_id="sess-emp",
    )
    ok = out.get("response_style") == "empathetic" or "sorry" in out["message"].lower() or "understand" in out["message"].lower()
    print(f"[{'PASS' if ok else 'FAIL'}] frustrated user gets empathetic wording")
    return ok


def main() -> int:
    tests = [
        test_payment_issue_subcategory_and_missing_txn,
        test_broad_machine_no_search,
        test_machine_search_valid_filters,
        test_document_rag_not_search,
        test_support_never_searches,
        test_invalid_city_triggers_clarification,
        test_greeting_variation,
        test_broad_request_varies_but_asks_purpose_city,
        test_payment_varies_but_asks_ids,
        test_refund_no_false_claim,
        test_no_result_varies_safe_suggestions,
        test_document_does_not_invent_sources,
        test_machine_result_preserves_prices,
        test_name_not_every_sentence,
        test_frustrated_gets_empathetic,
    ]
    passed = sum(1 for t in tests if t())
    total = len(tests)
    print(f"\nRich intent + response tests: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
