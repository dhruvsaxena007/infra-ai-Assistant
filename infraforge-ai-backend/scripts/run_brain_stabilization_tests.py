#!/usr/bin/env python3
"""Brain stabilization regression — RAG gate, memory, purpose mapping, no catalog dump."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import rag_service
from app.chatbot.assistant_intelligence import (
    PURPOSE_TO_MACHINE,
    map_purpose_to_categories,
    resolve_purpose_key,
)
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database

DOC = "Policy: Warehouse projects require forklift. Highway needs roller."


def _ctx(resp: dict) -> dict:
    return (resp.get("data") or {}).get("context") or {}


def _machines(resp: dict) -> int:
    return len((resp.get("data") or {}).get("machines") or [])


def _sources(resp: dict) -> int:
    return len((resp.get("data") or {}).get("sources") or [])


async def test_greeting_no_rag():
    rag_service.clear_rag_for_tests()
    rag_service.add_document_to_rag(DOC, session_id="stab_greet")
    sid = "stab_greet"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "hi", database)
    ok = _ctx(resp).get("assistant_mode") == "greeting" and _sources(resp) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] Greeting no RAG | sources={_sources(resp)}")
    return ok


async def test_machine_search_no_rag():
    rag_service.clear_rag_for_tests()
    rag_service.add_document_to_rag(DOC, session_id="stab_search")
    sid = "stab_search"
    clear_conversation(sid)
    resp = await chatbot_response(sid, "excavator in Jaipur", database)
    ok = _sources(resp) == 0 and _ctx(resp).get("intent") != "document_question"
    print(f"[{'PASS' if ok else 'FAIL'}] Machine search no RAG | sources={_sources(resp)}")
    return ok


async def test_vague_machine_no_dump():
    sid = "stab_vague"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "I need a machine", database)
    mode = _ctx(resp).get("assistant_mode")
    ok = _machines(resp) <= 5 and mode in ("clarification", "greeting", "unknown", "support")
    print(f"[{'PASS' if ok else 'FAIL'}] Vague machine no dump | mode={mode} machines={_machines(resp)}")
    return ok


async def test_recommendation_compaction_resume():
    sid = "stab_rec"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    await chatbot_response(sid, "road project ke liye machine chahiye", database)
    resp = await chatbot_response(sid, "compaction", database)
    mode = _ctx(resp).get("assistant_mode")
    ok = _sources(resp) == 0 and mode not in ("document_qa", "refund_return")
    print(f"[{'PASS' if ok else 'FAIL'}] Compaction resume | mode={mode} rag_sources={_sources(resp)}")
    return ok


async def test_refund_no_rag_no_search():
    sid = "stab_refund"
    clear_conversation(sid)
    rag_service.add_document_to_rag(DOC, session_id=sid)
    resp = await chatbot_response(sid, "refund chahiye", database)
    ok = _machines(resp) == 0 and _sources(resp) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] Refund no RAG/search | machines={_machines(resp)}")
    return ok


def test_purpose_mapping():
    cases = {
        "digging": "excavator",
        "excavation": "excavator",
        "road leveling": "motor grader",
        "compaction": "road roller",
        "lifting": "crane",
        "transport": "dump truck",
    }
    ok = True
    for phrase, expect in cases.items():
        key = resolve_purpose_key(phrase)
        cats = map_purpose_to_categories(key or "")
        if not any(expect in c for c in cats):
            ok = False
            print(f"[FAIL] purpose map {phrase!r} -> {key} cats={cats}")
        else:
            print(f"[PASS] purpose map {phrase!r} -> {key} -> {cats[0]}")
    ok = ok and len(PURPOSE_TO_MACHINE) >= 6
    return ok


async def test_document_only_rag():
    sid = "stab_doc"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    rag_service.add_document_to_rag(DOC, session_id=sid)
    resp = await chatbot_response(
        sid, "what does the uploaded document say about machines?", database,
    )
    ok = _ctx(resp).get("assistant_mode") == "document_qa"
    print(f"[{'PASS' if ok else 'FAIL'}] Document explicit RAG | mode={_ctx(resp).get('assistant_mode')}")
    return ok


async def main():
    print("=" * 72)
    print("Brain Stabilization Tests")
    print("=" * 72)
    passed = failed = 0
    if test_purpose_mapping():
        passed += 1
    else:
        failed += 1
    for coro in [
        test_greeting_no_rag(),
        test_machine_search_no_rag(),
        test_vague_machine_no_dump(),
        test_recommendation_compaction_resume(),
        test_refund_no_rag_no_search(),
        test_document_only_rag(),
    ]:
        ok = await coro
        passed += int(ok)
        failed += int(not ok)
    print("=" * 72)
    print(f"Passed: {passed} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
