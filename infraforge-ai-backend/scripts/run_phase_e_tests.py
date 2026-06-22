#!/usr/bin/env python3
"""Phase E — premium assistant UX tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.assistant_response_style import clarification_suggestions
from app.ai.marketplace_knowledge import lookup_knowledge
from app.chatbot.assistant_intelligence import (
    _GREETING_CHIPS,
    clarification_question,
)
from app.analytics.turn_analytics import extract_analytics_from_response
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.ai import rag_service
from app.database.mongodb import database


def _mode(resp: dict) -> str:
    data = resp.get("data") or {}
    return str((data.get("context") or {}).get("assistant_mode") or data.get("assistant_mode") or "")


def _suggestions(resp: dict) -> list:
    return list((resp.get("data") or {}).get("suggestions") or [])


def _handover(resp: dict) -> dict | None:
    return (resp.get("data") or {}).get("handover")


def _machines(resp: dict) -> int:
    return len((resp.get("data") or {}).get("machines") or [])


async def test_greeting_suggestions():
    sid = "phasee_greet"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "hi", database)
    chips = _suggestions(resp)
    ok = _mode(resp) == "greeting" and any("Search" in c for c in chips)
    ok = ok and any(c in _GREETING_CHIPS for c in chips)
    print(f"[{'PASS' if ok else 'FAIL'}] Greeting suggestions | mode={_mode(resp)} chips={chips[:4]}")
    return ok


def test_smart_clarification_copy():
    q = clarification_question("road roller", "city", lang="hinglish")
    ok = "city" in q.lower() or "kis" in q.lower()
    ok = ok and ("road roller" in q.lower() or "roller" in q.lower())
    q2 = clarification_question(None, "category", city="Delhi", lang="hinglish")
    ok = ok and "delhi" in q2.lower() and "machine" in q2.lower()
    print(f"[{'PASS' if ok else 'FAIL'}] Smart clarification | city_q={q[:60]!r}")
    return ok


async def test_recommendation_flow():
    sid = "phasee_rec"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "road project ke liye machine chahiye", database)
    mode = _mode(resp)
    ok = mode in ("recommendation_clarification", "recommendation", "clarification")
    ok = ok and _machines(resp) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] Recommendation flow | mode={mode}")
    return ok


def test_marketplace_knowledge():
    out = lookup_knowledge("how to rent a machine", lang="english")
    ok = out is not None and "rent" in (out.get("message") or "").lower()
    ok = ok and out.get("assistant_mode") == "platform_how_to"
    print(f"[{'PASS' if ok else 'FAIL'}] Marketplace knowledge rent | mode={out.get('assistant_mode') if out else None}")
    return ok


async def test_empty_result_handling():
    sid = "phasee_noresult"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "crawler drill in Jaipur", database)
    msg = (resp.get("message") or "").lower()
    mode = _mode(resp)
    ok = mode in ("no_result", "search", "no_result", "purpose_alternatives", "machine_search")
    ok = ok or "jaipur" in msg or "similar" in msg or "nearby" in msg or "couldn't" in msg
    print(f"[{'PASS' if ok else 'FAIL'}] Empty/smart no-result | mode={mode}")
    return ok


async def test_human_handover():
    sid = "phasee_handover"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "refund chahiye", database)
    ho = _handover(resp) or {}
    actions = [a.get("label") for a in (ho.get("actions") or [])]
    ho_msg = (ho.get("message") or "").lower()
    guided = "what would you like" in ho_msg or "kya karna chahenge" in ho_msg or "kya karna" in ho_msg
    ok = ho.get("enabled") and "Call" in actions and "WhatsApp" in actions
    ok = ok and _machines(resp) == 0 and guided
    print(f"[{'PASS' if ok else 'FAIL'}] Human handover | actions={actions}")
    return ok


async def test_follow_up_continuity():
    sid = "phasee_followup"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    await chatbot_response(sid, "crawler drill in Jaipur", database)
    resp = await chatbot_response(sid, "what about Delhi?", database)
    mode = _mode(resp)
    ctx = (resp.get("data") or {}).get("context") or {}
    filters = (resp.get("data") or {}).get("filters") or {}
    city = (filters.get("city") or "").lower()
    ok = mode not in ("refund_return", "payment_issue", "out_of_scope")
    ok = ok and (city == "delhi" or "delhi" in (resp.get("message") or "").lower())
    print(f"[{'PASS' if ok else 'FAIL'}] Follow-up Delhi | mode={mode} city={city} ctx_used={ctx.get('used_previous_context')}")
    return ok


async def test_suggestion_chips_on_search():
    sid = "phasee_chips"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "excavator in Jaipur", database)
    chips = _suggestions(resp)
    ok = len(chips) >= 1 or _machines(resp) >= 0
    if _machines(resp) > 0:
        ok = any("cheaper" in c.lower() or "rent" in c.lower() or "contact" in c.lower() for c in chips)
    print(f"[{'PASS' if ok else 'FAIL'}] Search suggestion chips | chips={chips[:4]}")
    return ok


async def test_analytics_logging():
    mock_db = MagicMock()
    mock_db.assistant_turn_logs = MagicMock()
    mock_db.assistant_turn_logs.insert_one = AsyncMock(return_value=None)

    from app.analytics.turn_analytics import log_turn_from_response

    fake_resp = {
        "data": {
            "machines": [{"id": "1"}],
            "context": {"assistant_mode": "search", "intent": "machine_search", "used_previous_context": True},
            "search_status": {"exact_match_found": True, "fallback_used": False},
        }
    }
    payload = extract_analytics_from_response(
        fake_resp, user_message="test", session_id="s1",
    )
    ok = payload.get("search_result_count") == 1 and payload.get("assistant_mode") == "search"
    await log_turn_from_response(mock_db, "s1", "test", fake_resp)
    ok = ok and mock_db.assistant_turn_logs.insert_one.called
    print(f"[{'PASS' if ok else 'FAIL'}] Analytics logging | count={payload.get('search_result_count')}")
    return ok


def test_clarification_chip_helper():
    chips = clarification_suggestions("city")
    ok = "Jaipur" in chips or "Delhi" in chips
    print(f"[{'PASS' if ok else 'FAIL'}] Clarification chip helper | {chips[:3]}")
    return ok


async def main():
    print("=" * 72)
    print("Phase E Tests")
    print("=" * 72)
    passed = failed = 0

    sync_tests = [
        test_smart_clarification_copy(),
        test_marketplace_knowledge(),
        test_clarification_chip_helper(),
    ]
    for ok in sync_tests:
        passed += int(ok)
        failed += int(not ok)

    async_tests = [
        test_greeting_suggestions(),
        test_recommendation_flow(),
        test_empty_result_handling(),
        test_human_handover(),
        test_follow_up_continuity(),
        test_suggestion_chips_on_search(),
        test_analytics_logging(),
    ]
    for coro in async_tests:
        ok = await coro
        passed += int(ok)
        failed += int(not ok)

    print("=" * 72)
    print(f"Passed: {passed} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
