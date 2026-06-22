#!/usr/bin/env python3
"""IMG-1 image search phase tests (19 backend cases)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chatbot.chatbot_service import chatbot_response, reset_session_state
from app.chatbot.image_context_memory import (
    clear_image_context,
    get_image_context,
    save_image_context,
)
from app.chatbot.memory import clear_conversation
from app.database.mongodb import database

PASS = FAIL = 0


def ok(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}" + (f" | {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f" | {detail}" if detail else ""))


def _fake_pipeline(
    *,
    category: str = "excavator",
    confidence: float = 0.82,
    success: bool = True,
    match_type: str = "exact",
) -> dict:
    return {
        "success": success,
        "stage": "visual",
        "intent": {
            "match_type": match_type,
            "machine_type": category if category else None,
            "search_query": category,
            "intent_confidence": confidence,
            "confident": confidence >= 0.35,
            "suggested_categories": [category] if category else [],
            "classifier": "clip+opencv",
            "display_label": category.title() if category else None,
        },
        "classification": {},
    }


class FakeUpload:
    def __init__(
        self,
        filename: str = "machine.jpg",
        data: bytes | None = None,
        content_type: str = "image/jpeg",
    ):
        self.filename = filename
        self.content_type = content_type
        self._data = data or b"\xff\xd8\xff\xe0" + b"\x00" * 128

    async def read(self):
        return self._data


async def _call_image_search(
    *,
    message: str = "",
    session_id: str = "img1_test",
    pipeline: dict | None = None,
):
    from app.api.routes import image_search as img_route

    pipeline = pipeline or _fake_pipeline()
    chat_mock = AsyncMock(
        return_value={
            "success": True,
            "message": "Found machines",
            "data": {
                "machines": [{"_id": "1", "name": "Excavator A"}],
                "assistant_mode": "search",
                "filters": {"category": "excavator"},
            },
        }
    )
    with patch.object(img_route, "classify_marketplace_image", return_value=pipeline):
        with patch.object(img_route, "chatbot_response", new=chat_mock):
            resp = await img_route.image_search(
                file=FakeUpload(),
                session_id=session_id,
                message=message,
            )
    return resp, chat_mock


def test_resolver_cases() -> None:
    from app.ai.image_turn_resolver import resolve_image_turn

    print("\n1. Resolver / intent rules")
    turn = resolve_image_turn(
        pipeline=_fake_pipeline(),
        user_text="",
        session_id="r1",
        original_filename="x.jpg",
    )
    ok("image only -> clarification", turn.needs_clarification and not turn.should_search)

    turn = resolve_image_turn(
        pipeline=_fake_pipeline(),
        user_text="similar machines",
        session_id="r2",
    )
    ok("similar -> search", turn.image_intent == "similar_category" and turn.should_search)

    turn = resolve_image_turn(
        pipeline=_fake_pipeline(),
        user_text="exact same machine",
        session_id="r3",
    )
    ok("exact -> no fake search", turn.image_intent == "exact_match" and not turn.should_search)

    turn = resolve_image_turn(
        pipeline=_fake_pipeline(),
        user_text="available in Jaipur",
        session_id="r4",
    )
    ok("availability -> search", turn.image_intent == "availability_search" and turn.should_search)
    ok("availability includes city", "jaipur" in turn.safe_user_message.lower())

    turn = resolve_image_turn(
        pipeline=_fake_pipeline(confidence=0.12),
        user_text="",
        session_id="r5",
    )
    ok("low confidence -> no search", turn.image_intent == "low_confidence" and not turn.should_search)

    turn = resolve_image_turn(
        pipeline=_fake_pipeline(category="", confidence=0.0, success=False, match_type="unknown"),
        user_text="",
        session_id="r6",
    )
    ok("non-machine -> no search", turn.image_intent == "non_machine" and not turn.should_search)

    turn = resolve_image_turn(
        pipeline=_fake_pipeline(category="unsupported_xyz_cat"),
        user_text="ye kya machine hai",
        session_id="r7",
    )
    ok("identify only", turn.image_intent == "identify_only" and not turn.should_search)


async def test_route_integration() -> None:
    print("\n2. /image-search adapter")
    clear_image_context("img1_ctx")
    resp, chat_mock = await _call_image_search(session_id="img1_ctx", message="")
    data = resp.get("data") or {}
    ok("confident image only -> clarification", data.get("assistant_mode") == "image_clarification")
    ok("no machines on clarification", len(data.get("machines") or []) == 0)
    ok("chatbot not called for clarification", chat_mock.await_count == 0)

    resp, chat_mock = await _call_image_search(message="similar machines", session_id="img1_sim")
    ok("similar uses chatbot", chat_mock.await_count == 1)
    ok("similar pipeline message", "excavator" in (chat_mock.await_args.args[1] or "").lower())

    resp, chat_mock = await _call_image_search(message="exact same", session_id="img1_ex")
    ok("exact honest response", chat_mock.await_count == 0)
    ok("exact mentions cannot confirm", "exact" in (resp.get("message") or "").lower() or "possible nahi" in (resp.get("message") or "").lower())

    resp, chat_mock = await _call_image_search(message="available in Jaipur", session_id="img1_city")
    ok("city search via chatbot", chat_mock.await_count == 1)
    ok("city in query", "jaipur" in (chat_mock.await_args.args[1] or "").lower())

    from app.api.routes import image_search as img_route

    source = open(img_route.__file__, encoding="utf-8").read()
    ok("no direct Mongo import in route", "search_category_with_fallback" not in source)


def test_image_context_memory() -> None:
    print("\n3. Image context memory")
    sid = "img1_mem"
    clear_image_context(sid)
    save_image_context(
        sid,
        full_context={
            "upload_id": "u1",
            "detected_category": "excavator",
            "detected_machine_type": "excavator",
            "confidence": 0.8,
            "classifier_used": "clip_opencv",
            "image_intent": "unclear",
            "search_mode": "none",
            "suggested_categories": ["excavator"],
            "search_query": "excavator",
        },
    )
    ctx = get_image_context(sid)
    ok("context saved", bool(ctx and ctx.get("detected_category") == "excavator"))
    ok("has expiry", bool(ctx and ctx.get("expires_at")))

    reset_session_state(sid)
    ok("reset clears context", get_image_context(sid) is None)

    save_image_context(sid, detected_machine_type="crane", upload_id="a")
    save_image_context(
        sid,
        full_context={
            "upload_id": "b",
            "detected_category": "excavator",
            "detected_machine_type": "excavator",
            "confidence": 0.9,
            "classifier_used": "yolo",
            "image_intent": "unclear",
            "search_mode": "none",
            "suggested_categories": ["excavator"],
            "search_query": "excavator",
        },
    )
    ctx2 = get_image_context(sid)
    ok("new upload replaces", ctx2 and ctx2.get("upload_id") == "b")


async def test_chat_overrides_and_safety() -> None:
    print("\n4. Chat follow-ups / safety")
    sid = "img1_follow"
    clear_conversation(sid)
    clear_image_context(sid)
    save_image_context(sid, detected_machine_type="excavator", search_query="excavator")

    resp = await chatbot_response(sid, "crane in delhi", database)
    filters = (resp.get("data") or {}).get("filters") or {}
    cat = (filters.get("category") or "").lower()
    ok("explicit category overrides image", "crane" in cat or "crane" in (resp.get("message") or "").lower())

    sid2 = "img1_support"
    clear_conversation(sid2)
    save_image_context(sid2, detected_machine_type="excavator", search_query="excavator")
    resp = await chatbot_response(sid2, "refund chahiye", database)
    mode = ((resp.get("data") or {}).get("context") or {}).get("assistant_mode") or (resp.get("data") or {}).get("assistant_mode")
    ok("support after image no search", "refund" in str(mode) and len((resp.get("data") or {}).get("machines") or []) == 0)

    sid3 = "img1_oot"
    clear_conversation(sid3)
    save_image_context(sid3, detected_machine_type="excavator", search_query="excavator")
    resp = await chatbot_response(sid3, "what is the weather today", database)
    machines = len((resp.get("data") or {}).get("machines") or [])
    ok("off-topic after image", machines == 0)


def test_validation_and_cleanup() -> None:
    print("\n5. Validation / cleanup")
    from app.ai.image_validation import cleanup_image_path, validate_image_format

    bad = b""
    res = validate_image_format(FakeUpload(data=bad), bad)
    ok("empty rejected", not res.ok)

    huge = b"\xff\xd8\xff" + b"x" * (9 * 1024 * 1024)
    res = validate_image_format(FakeUpload(), huge)
    ok("oversized rejected", not res.ok)

    res = validate_image_format(FakeUpload(content_type="application/pdf"), b"\xff\xd8\xff" + b"x" * 20)
    ok("invalid mime rejected", not res.ok)

    path = os.path.join(ROOT, "uploads", "image_search", "_img1_cleanup_test.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\xff\xd8\xff")
    cleanup_image_path(path)
    ok("temp deleted", not os.path.isfile(path))


async def test_single_response_shape() -> None:
    print("\n6. Single image+text response")
    resp, chat_mock = await _call_image_search(message="similar machines", session_id="img1_one")
    ok("one image+text call", chat_mock.await_count == 1)
    ok("standard success envelope", resp.get("success") is True and "data" in resp)


def test_regression_imports() -> None:
    print("\n7. Regression smoke (import)")
    ok("voice test module", Path(ROOT / "scripts/test_voice_phase_v1.py").is_file())
    ok("phase11 module", Path(ROOT / "scripts/test_reliability_phase11_baseline.py").is_file())


async def main() -> int:
    print("=" * 60)
    print("IMG-1 Image Search Phase Tests")
    print("=" * 60)
    test_resolver_cases()
    await test_route_integration()
    test_image_context_memory()
    await test_chat_overrides_and_safety()
    test_validation_and_cleanup()
    await test_single_response_shape()
    test_regression_imports()
    print("=" * 60)
    print(f"PASSED: {PASS}  FAILED: {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
