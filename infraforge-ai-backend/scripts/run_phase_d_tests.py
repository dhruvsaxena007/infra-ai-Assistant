#!/usr/bin/env python3
"""Phase D production-hardening tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import rag_service
from app.ai.message_normalizer import normalize_user_message
from app.ai.yolo_classification_service import yolo_model_available
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database

DOC_A = "Session A policy: Highway projects require motor grader and road roller."
DOC_B = "Session B policy: Warehouse projects require forklift only."


def _mode(resp: dict) -> str:
    data = resp.get("data") or {}
    return str((data.get("context") or {}).get("assistant_mode") or data.get("assistant_mode") or "")


def _machines(resp: dict) -> int:
    return len((resp.get("data") or {}).get("machines") or [])


async def test_yolo_missing_safe():
    with patch("app.ai.yolo_classification_service.yolo_model_available", return_value=False):
        from app.ai.image_classifier import classify_marketplace_image
        import tempfile
        import os

        # tiny valid png header bytes
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
            b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(png)
            result = classify_marketplace_image(path)
        finally:
            os.unlink(path)
    ok = isinstance(result, dict) and "success" in result
    print(f"[{'PASS' if ok else 'FAIL'}] YOLO missing safe fallback | success_key={ok}")
    return ok


async def test_session_rag_isolation():
    rag_service.clear_rag_for_tests()
    sid_a = "phase_d_rag_a"
    sid_b = "phase_d_rag_b"
    clear_conversation(sid_a)
    clear_conversation(sid_b)
    rag_service.add_document_to_rag(DOC_A, session_id=sid_a)
    ans_a = rag_service.ask_rag_question("What machines for highway project?", session_id=sid_a)
    ans_b = rag_service.ask_rag_question("What machines for highway project?", session_id=sid_b)
    ok = ans_a.get("success") and ans_a.get("rag_scope") == "session"
    ok = ok and not ans_b.get("success") and ans_b.get("rag_scope") == "none"
    print(f"[{'PASS' if ok else 'FAIL'}] Session RAG isolation | A={ans_a.get('success')} B={ans_b.get('success')}")
    return ok


async def test_legacy_global_rag():
    rag_service.clear_rag_for_tests()
    rag_service.add_document_to_rag("Global legacy document about excavators in mining.")
    ans = rag_service.ask_rag_question("excavators in mining")
    ok = ans.get("success") and ans.get("rag_scope") == "global"
    print(f"[{'PASS' if ok else 'FAIL'}] Legacy global RAG | scope={ans.get('rag_scope')}")
    return ok


async def test_refund_no_search():
    sid = "phase_d_refund"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "refund chahiye", database)
    ok = _machines(resp) == 0 and "refund" in _mode(resp)
    print(f"[{'PASS' if ok else 'FAIL'}] refund no search | mode={_mode(resp)}")
    return ok


async def test_payment_no_search():
    sid = "phase_d_payment"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "payment failed", database)
    ok = _machines(resp) == 0 and "payment" in _mode(resp)
    print(f"[{'PASS' if ok else 'FAIL'}] payment no search | mode={_mode(resp)}")
    return ok


def test_normalization_typos():
    cases = [
        ("exavator in jaypur under 5000", "excavator", "jaipur"),
        ("dump truk delhi", "dump truck", "delhi"),
        ("road rolar pune", "road roller", "pune"),
    ]
    ok = True
    for raw, cat, city in cases:
        norm = normalize_user_message(raw)
        low = norm.corrected.lower()
        if cat not in low or city not in low:
            ok = False
            print(f"[FAIL] normalize {raw!r} -> {norm.corrected!r}")
        else:
            print(f"[PASS] normalize {raw!r} -> {norm.corrected!r}")
    return ok


async def test_refund_not_fuzzy_search():
    sid = "phase_d_refund2"
    clear_conversation(sid)
    rag_service.clear_rag_for_tests()
    resp = await chatbot_response(sid, "refund chahiye", database)
    ok = _machines(resp) == 0
    print(f"[{'PASS' if ok else 'FAIL'}] refund not fuzzy search | machines={_machines(resp)}")
    return ok


async def test_groq_semantic_fallback():
    from app.ai.semantic_turn_classifier import classify_turn_semantically

    with patch("app.core.groq_client.groq_chat_completion", return_value=None):
        result = await classify_turn_semantically("refund chahiye")
    ok = result is None
    print(f"[{'PASS' if ok else 'FAIL'}] Groq semantic failure returns None | result={result}")
    return ok


async def test_advisor_groq_fallback():
    from app.ai.advisor_service import generate_machine_advice

    machines = [
        {"name": "JCB 3DX", "category": "backhoe loader", "city": "jaipur", "price_per_day": 5000,
         "availability_status": "available", "rating": 4.2, "specifications": {"condition": "used"}},
        {"name": "JCB 3DX Pro", "category": "backhoe loader", "city": "jaipur", "price_per_day": 4500,
         "availability_status": "available", "rating": 4.0, "specifications": {"condition": "used"}},
        {"name": "Loader X", "category": "backhoe loader", "city": "jaipur", "price_per_day": 4800,
         "availability_status": "available", "rating": 3.9, "specifications": {"condition": "used"}},
    ]
    with patch("app.core.config.settings.USE_GROQ_ADVISOR", True):
        with patch("app.ai.advisor_service.groq_chat_completion", return_value=None):
            out = generate_machine_advice("jcb in jaipur", machines, exact_match_found=True)
    ok = out.get("success") and out.get("source") == "rules"
    print(f"[{'PASS' if ok else 'FAIL'}] Advisor Groq fallback | source={out.get('source')}")
    return ok


def test_voice_metadata_shape():
    from app.ai.rules_understanding import build_chat_input_metadata

    meta = build_chat_input_metadata(
        original_message="Jaipur me excavator chahiye",
        normalized_message="Jaipur me excavator chahiye",
    )
    ok = bool(meta.get("enhanced_query")) and meta.get("text_understanding") is not None
    print(f"[{'PASS' if ok else 'FAIL'}] Voice/text metadata shape | keys={list(meta.keys())}")
    return ok


async def main():
    print("=" * 72)
    print("Phase D Tests")
    print("=" * 72)
    print(f"[info] yolo_model_available={yolo_model_available()}")
    passed = failed = 0
    sync_tests = [
        test_normalization_typos(),
        test_voice_metadata_shape(),
    ]
    for ok in sync_tests:
        passed += int(ok)
        failed += int(not ok)

    async_tests = [
        test_yolo_missing_safe(),
        test_session_rag_isolation(),
        test_legacy_global_rag(),
        test_refund_no_search(),
        test_payment_no_search(),
        test_refund_not_fuzzy_search(),
        test_groq_semantic_fallback(),
        test_advisor_groq_fallback(),
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
