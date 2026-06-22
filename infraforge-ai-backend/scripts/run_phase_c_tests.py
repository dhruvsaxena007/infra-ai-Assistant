#!/usr/bin/env python3
"""Phase C regression tests (RAG inline, image safe mode, image context, panel safety)."""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.image_context_memory import save_image_context
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database
from app.ai import rag_service

HIGHWAY_DOC = """
Highway Project Equipment Guide
For highway construction projects, the following machines are typically required:
- Motor grader for road leveling
- Road roller for compaction
- Dump truck for material transport
- Crawler drill for foundation work where needed
Safety: all operators must wear PPE on site.
"""


def _mode(resp: dict) -> str:
    data = resp.get("data") or {}
    ctx = data.get("context") or {}
    return str(ctx.get("assistant_mode") or data.get("assistant_mode") or "")


def _machines(resp: dict) -> int:
    data = resp.get("data") or {}
    return len(data.get("machines") or [])


async def test_rag_no_upload():
    sid = "phasec_rag1"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(
        sid, "what does the uploaded document say about machines?", database,
    )
    ok = _mode(resp) == "document_qa" and _machines(resp) == 0
    ok = ok and "upload" in (resp.get("message") or "").lower()
    print(f"[{'PASS' if ok else 'FAIL'}] RAG before upload | mode={_mode(resp)}")
    return ok


async def test_rag_after_upload():
    sid = "phasec_rag2"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    rag_service.add_document_to_rag(HIGHWAY_DOC, session_id=sid)
    resp = await chatbot_response(
        sid, "What machines are needed for highway project?", database,
    )
    ok = _mode(resp) == "document_qa" and _machines(resp) == 0
    ok = ok and len((resp.get("data") or {}).get("answer") or resp.get("message") or "") > 20
    print(f"[{'PASS' if ok else 'FAIL'}] RAG after upload | mode={_mode(resp)}")
    return ok


def test_rag_empty_question():
    from app.ai.rag_service import ask_rag_question

    rag_service.clear_rag_for_tests()
    rag_service.add_document_to_rag("sample text about excavators")
    result = ask_rag_question("   ")
    ok = not result.get("success") and "required" in (result.get("message") or "").lower()
    print(f"[{'PASS' if ok else 'FAIL'}] RAG empty question | {result.get('message')}")
    return ok


async def test_image_non_machine_clarification():
    from app.api.routes.image_search import image_search

    fake_intent = {
        "match_type": "unknown",
        "machine_type": None,
        "intent_confidence": 0.05,
        "suggested_categories": ["excavator"],
        "message": "Not a machine",
    }
    fake_pipeline = {"success": False, "intent": fake_intent, "stage": "visual", "classification": {}}

    class FakeUpload:
        filename = "person.jpg"
        content_type = "image/jpeg"

        async def read(self):
            return b"\xff\xd8\xff\xe0" + b"\x00" * 128

    with patch("app.api.routes.image_search.classify_marketplace_image", return_value=fake_pipeline):
        with patch("app.api.routes.image_search.resize_image_if_needed", side_effect=lambda p: p):
            resp = await image_search(file=FakeUpload(), session_id="phasec_img1", message="")

    data = resp.get("data") or {}
    ok = data.get("assistant_mode") == "image_clarification"
    ok = ok and len(data.get("machines") or []) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] Non-machine image | mode={data.get('assistant_mode')}")
    return ok


async def test_image_low_confidence():
    from app.api.routes.image_search import image_search

    fake_intent = {
        "match_type": "exact",
        "machine_type": "excavator",
        "intent_confidence": 0.12,
        "confident": True,
        "suggested_categories": ["excavator"],
        "message": "Low confidence",
    }
    fake_pipeline = {"success": True, "intent": fake_intent, "stage": "yolo", "classification": {}}

    class FakeUpload:
        filename = "blur.jpg"
        content_type = "image/jpeg"

        async def read(self):
            return b"\xff\xd8\xff\xe0" + b"\x00" * 128

    with patch("app.api.routes.image_search.classify_marketplace_image", return_value=fake_pipeline):
        with patch("app.api.routes.image_search.resize_image_if_needed", side_effect=lambda p: p):
            resp = await image_search(file=FakeUpload(), session_id="phasec_img2", message="")

    data = resp.get("data") or {}
    ok = data.get("assistant_mode") == "image_clarification"
    ok = ok and len(data.get("machines") or []) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] Low-confidence image | mode={data.get('assistant_mode')}")
    return ok


async def test_image_context_followup():
    sid = "phasec_imgctx"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    save_image_context(sid, detected_machine_type="excavator", search_query="excavator")
    resp = await chatbot_response(sid, "is this available in Jaipur?", database)
    mode = _mode(resp)
    filters = (resp.get("data") or {}).get("filters") or {}
    cat = (filters.get("category") or "").lower()
    city = (filters.get("city") or "").lower()
    msg = (resp.get("message") or "").lower()
    ok = mode in ("search", "no_result", "machine_search", "clarification", "machine_availability")
    ok = ok or "search" in mode
    ok = ok and ("excavator" in cat or "excavator" in msg)
    ok = ok and (not city or city == "jaipur")
    print(f"[{'PASS' if ok else 'FAIL'}] Image context follow-up | mode={mode} cat={cat} city={city}")
    return ok


async def test_image_ref_no_context():
    sid = "phasec_imgnoctx"
    clear_conversation(sid)
    from app.chatbot.image_context_memory import clear_image_context

    clear_image_context(sid)
    resp = await chatbot_response(sid, "is this available in Jaipur?", database)
    mode = _mode(resp)
    ok = mode == "image_clarification" and _machines(resp) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] Image ref without context | mode={mode}")
    return ok


async def test_panel_clear_after_refund():
    sid = "phasec_panel1"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    await chatbot_response(sid, "crawler drill in Jaipur", database)
    resp = await chatbot_response(sid, "refund chahiye", database)
    ok = _machines(resp) == 0 and "refund" in _mode(resp)
    print(f"[{'PASS' if ok else 'FAIL'}] Panel clear after refund | mode={_mode(resp)} machines={_machines(resp)}")
    return ok


async def test_panel_clear_after_document():
    sid = "phasec_panel2"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    await chatbot_response(sid, "excavator in Jaipur", database)
    resp = await chatbot_response(
        sid, "what does the uploaded document say about machines?", database,
    )
    ok = _machines(resp) == 0 and _mode(resp) == "document_qa"
    print(f"[{'PASS' if ok else 'FAIL'}] Panel clear after document Q | mode={_mode(resp)}")
    return ok


async def main():
    print("=" * 72)
    print("Phase C Tests")
    print("=" * 72)
    cases = [
        ("RAG before upload", test_rag_no_upload()),
        ("RAG after upload", test_rag_after_upload()),
        ("Non-machine image", test_image_non_machine_clarification()),
        ("Low-confidence image", test_image_low_confidence()),
        ("Image context follow-up", test_image_context_followup()),
        ("Image ref without context", test_image_ref_no_context()),
        ("Panel clear after refund", test_panel_clear_after_refund()),
        ("Panel clear after document", test_panel_clear_after_document()),
    ]
    passed = failed = 0
    if test_rag_empty_question():
        passed += 1
    else:
        failed += 1
    for _label, coro in cases:
        ok = await coro
        passed += int(ok)
        failed += int(not ok)
    print("=" * 72)
    print(f"Passed: {passed} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
