#!/usr/bin/env python3
"""Tests for suggestion chip resolver and related response-goal fixes."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _assert(label: str, cond: bool) -> None:
    print(f"{'OK' if cond else 'FAIL'} {label}")
    if not cond:
        raise SystemExit(1)


def test_chip_detection() -> None:
    from app.ai.suggestion_action_resolver import is_suggestion_chip, resolve_suggestion_chip

    for chip in [
        "Contact support",
        "Search this machine",
        "Compare brands",
        "Ask recommendation",
        "Show cheaper options",
        "Upload image",
    ]:
        _assert(f"is chip: {chip}", is_suggestion_chip(chip))

    _assert("not chip", not is_suggestion_chip("random unrelated question about weather"))


def test_static_resolution() -> None:
    from app.ai.suggestion_action_resolver import resolve_suggestion_chip

    r = resolve_suggestion_chip("Contact support")
    _assert("contact support sends", r["action"] == "send_message")
    _assert("support hint", r.get("intent_hint") == "support")
    _assert("support message", "support" in (r.get("message") or "").lower())


def test_contextual_search_this_machine() -> None:
    from app.ai.suggestion_action_resolver import resolve_suggestion_chip

    ctx = {
        "conversation_state": {
            "last_knowledge_context": {
                "brand": "CAT",
                "model": "320D",
                "category": "excavator",
                "display_name": "CAT 320D Excavator",
            },
            "last_search_filters": {"city": "Jaipur"},
        }
    }
    r = resolve_suggestion_chip("Search this machine", session_ctx=ctx)
    msg = (r.get("message") or "").lower()
    _assert("contextual search", "320d" in msg or "cat" in msg)
    _assert("search intent", r.get("intent_hint") == "machine_search")


def test_ui_actions() -> None:
    from app.ai.suggestion_action_resolver import resolve_suggestion_chip

    r = resolve_suggestion_chip("Upload image")
    _assert("upload ui", r["action"] == "ui_action" and r["ui_action"] == "open_image_picker")


def test_machine_spec_detection_hinglish() -> None:
    from app.ai.machine_spec_service import detect_machine_knowledge_query
    from app.ai.query_parser import parse_query

    cases = [
        "mujhe CAT 320D Excavator iske bare mai information do",
        "mujhe CAT 320D Excavator ke specification do",
        "CAT 320D excavator ke bare me details batao",
        "320D ki jankari do",
        "tell me about CAT 320D excavator specifications",
    ]
    for msg in cases:
        k = detect_machine_knowledge_query(msg, parse_query(msg))
        _assert(f"machine knowledge: {msg[:40]!r}", k is not None)
        _assert(f"kind spec/advisory: {msg[:30]!r}", k.get("kind") in (
            "machine_specification", "machine_advisory",
        ))


def test_support_response_import() -> None:
    from app.ai.support_response_service import build_response

    r = build_response("support_request", lang="english", message="contact support")
    _assert("support message", len(r.get("message") or "") > 20)
    _assert("support handover", bool(r.get("handover")))


def test_knowledge_goal_registered() -> None:
    from app.ai.conversation_aware_response import _FACTUAL_DRAFT_GOALS, _VARIANTS

    _assert("domain knowledge factual", "domain_knowledge_answer" in _FACTUAL_DRAFT_GOALS)
    _assert("support guidance factual", "support_guidance" in _FACTUAL_DRAFT_GOALS)
    _assert("support variants", "support_guidance" in _VARIANTS)


async def test_knowledge_answer_draft() -> None:
    from app.ai.knowledge_query_engine import build_knowledge_answer, knowledge_turn_from_message
    from app.ai.query_parser import parse_query

    msg = "mujhe CAT 320D Excavator ke specification do"
    turn = knowledge_turn_from_message(msg, parse_query(msg))
    _assert("turn detected", turn is not None)
    resp = await build_knowledge_answer(
        {**turn, "shape": "knowledge_answer"},
        user_message=msg,
        lang="hinglish",
    )
    _assert("goal is domain_knowledge_answer", resp.get("response_goal") == "domain_knowledge_answer")
    _assert("draft substance", len(resp.get("message") or "") > 40)
    _assert("has suggestions", len(resp.get("suggestions") or []) >= 2)


def test_recoverable_exception_support() -> None:
    from app.ai.safe_error_fallback import build_recoverable_exception_response

    resp = build_recoverable_exception_response(
        user_message="contact support",
        exc=RuntimeError("boom"),
        lang="english",
    )
    _assert("recoverable support success", resp.get("success") is True)
    _assert("support handover on crash", bool((resp.get("data") or {}).get("handover")))
    _assert("no generic error text", "Something didn't work" not in (resp.get("message") or ""))


def test_recoverable_exception_search_db() -> None:
    from app.ai.safe_error_fallback import build_recoverable_exception_response

    resp = build_recoverable_exception_response(
        user_message="excavator in jaipur",
        exc=AttributeError("'NoneType' object has no attribute 'equipmentcategories'"),
        lang="english",
    )
    _assert("search crash still success", resp.get("success") is True)
    _assert("search helpful msg", "search" in (resp.get("message") or "").lower())


def main() -> None:
    test_chip_detection()
    test_static_resolution()
    test_contextual_search_this_machine()
    test_ui_actions()
    test_machine_spec_detection_hinglish()
    test_support_response_import()
    test_knowledge_goal_registered()
    test_recoverable_exception_support()
    test_recoverable_exception_search_db()
    asyncio.run(test_knowledge_answer_draft())
    print("ALL SUGGESTION / KNOWLEDGE MECHANISM TESTS PASSED")


if __name__ == "__main__":
    main()
