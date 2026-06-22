"""
Voice Phase V1 tests — reliability, isolation, parity, normalization.

Run:
  python scripts/test_voice_phase_v1.py
  VOICE_PIPELINE_V2=true python scripts/test_voice_phase_v1.py
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("AI_INTENT_MODE", "rules_first")
os.environ.setdefault("ENABLE_OPENAI", "false")


class Counter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        tag = "PASS" if ok else "FAIL"
        line = f"  [{tag}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
        if ok:
            self.passed += 1
        else:
            self.failed += 1


def test_voice_input_validation(c: Counter) -> None:
    from app.ai.voice_input import build_voice_input_result, validate_transcript

    for text in ("Jaipur", "JCB", "Yes", "Rent", "8000"):
        ok, _ = validate_transcript(text)
        c.check(f"valid short reply: {text!r}", ok)

    for text, reason in [("", "empty"), ("   ", "whitespace"), ("a", "single char")]:
        ok, code = validate_transcript(text)
        c.check(f"reject {reason!r}", not ok, code)

    empty = build_voice_input_result("")
    c.check("empty transcript flagged", empty.is_empty)

    en = build_voice_input_result("excavator in Jaipur under 8000")
    c.check("english routing preserves entities", "jaipur" in en.routing_text and "excavator" in en.routing_text)
    c.check("english language", en.detected_language == "english")

    hi = build_voice_input_result("जयपुर में JCB चाहिए")
    c.check("hindi detected", hi.detected_language in ("hindi", "hinglish"))
    c.check("original preserved", hi.original_transcription == "जयपुर में JCB चाहिए")
    c.check("hindi routing has jaipur/jcb", "jaipur" in hi.routing_text and "jcb" in hi.routing_text)

    hing = build_voice_input_result("mujhe jcb chahiye jaipur me")
    c.check("hinglish detected", hing.detected_language == "hinglish")


def test_normalization_idempotence(c: Counter) -> None:
    from app.ai.voice_input import normalize_transcribed_text

    samples = [
        "excavator in jaipur under 8000",
        "jcb 3dx rent mumbai",
        "Hyundai crane delhi",
    ]
    for s in samples:
        once = normalize_transcribed_text(s)
        twice = normalize_transcribed_text(once)
        c.check(f"idempotent: {s!r}", once == twice, f"{once!r}")


def test_audio_validation(c: Counter) -> None:
    from app.ai.voice_audio_validation import validate_audio_format, validate_audio_upload

    class FakeUpload:
        def __init__(self, filename, content_type):
            self.filename = filename
            self.content_type = content_type

    ok_webm = validate_audio_format(FakeUpload("x.webm", "audio/webm"))
    c.check("webm allowed", ok_webm.ok)

    bad = validate_audio_format(FakeUpload("x.exe", "application/octet-stream"))
    c.check("invalid mime rejected", not bad.ok)

    big = validate_audio_upload(FakeUpload("x.webm", "audio/webm"), size_bytes=50 * 1024 * 1024)
    c.check("oversized rejected", not big.ok)


def test_file_cleanup(c: Counter) -> None:
    from app.ai.voice_audio_validation import safe_delete_file

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    c.check("temp exists", os.path.isfile(path))
    safe_delete_file(path)
    c.check("temp deleted", not os.path.exists(path))


def test_transcription_timeout(c: Counter) -> None:
    import time
    from app.ai import voice_transcription as vt

    def slow(*_a, **_k):
        time.sleep(10)
        return {"success": True, "original_text": "x", "text": "x"}

    with patch.object(vt.settings, "VOICE_STT_TIMEOUT_SECONDS", 0.05), patch.object(
        vt.settings, "VOICE_PIPELINE_V2", True
    ), patch.object(vt, "_sync_transcribe", side_effect=slow):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            result = asyncio.run(vt.transcribe_audio_file(path, request_id="t1"))
            c.check("timeout returns error", not result.get("success") and result.get("error") == "stt_timeout")
        finally:
            os.remove(path)


async def test_concurrent_limit(c: Counter) -> None:
    from app.ai import voice_transcription as vt

    vt._transcription_semaphore = None

    with patch.object(vt.settings, "VOICE_MAX_CONCURRENT_TRANSCRIPTIONS", 1), patch.object(
        vt.settings, "VOICE_PIPELINE_V2", True
    ), patch.object(
        vt,
        "_sync_transcribe",
        return_value={"success": True, "original_text": "jcb jaipur", "text": "jcb jaipur"},
    ):
        fd1, p1 = tempfile.mkstemp(suffix=".wav")
        fd2, p2 = tempfile.mkstemp(suffix=".wav")
        os.close(fd1)
        os.close(fd2)
        try:
            t1 = asyncio.create_task(vt.transcribe_audio_file(p1, request_id="a"))
            await asyncio.sleep(0.05)
            t2 = asyncio.create_task(vt.transcribe_audio_file(p2, request_id="b"))
            r1, r2 = await asyncio.gather(t1, t2)
            c.check("both transcriptions complete", r1.get("success") and r2.get("success"))
        finally:
            for p in (p1, p2):
                if os.path.exists(p):
                    os.remove(p)


def test_no_raw_speech_in_logs(c: Counter) -> None:
    from app.ai.voice_transcription import _redact_for_log

    redacted = _redact_for_log("this is secret user speech content")
    c.check("log redacts content", "secret" not in redacted and "len=" in redacted)


def test_chat_isolation(c: Counter) -> None:
    """POST /chat must not import voice processing modules."""
    import importlib

    chatbot_mod = importlib.import_module("app.api.routes.chatbot")
    source = open(chatbot_mod.__file__, encoding="utf-8").read()
    for token in (
        "voice_transcription",
        "voice_input",
        "voice_audio_validation",
        "transcribe_audio_file",
        "validate_audio",
    ):
        c.check(f"/chat route avoids {token}", token not in source)


async def test_voice_single_chatbot_call(c: Counter) -> None:
    from app.api.routes import voice as voice_routes

    fake_chat = AsyncMock(
        return_value={
            "message": "ok",
            "data": {"context": {"intent": "search"}, "filters": {}},
        }
    )

    voice_input = {
        "original_transcription": "excavator in jaipur",
        "routing_text": "excavator in jaipur",
        "detected_language": "english",
        "corrections": [],
        "is_empty": False,
    }

    with patch.object(voice_routes.settings, "VOICE_PIPELINE_V2", True), patch.object(
        voice_routes,
        "transcribe_audio_file",
        new=AsyncMock(
            return_value={
                "success": True,
                "original_text": "excavator in jaipur",
                "text": "excavator in jaipur",
                "voice_input": voice_input,
            }
        ),
    ), patch.object(voice_routes, "chatbot_response", new=fake_chat):
        resp = await voice_routes._route_voice_to_chat(
            session_id="sess-v1",
            transcription_result={
                "success": True,
                "voice_input": voice_input,
            },
            selected_machine_id="m1",
        )
        c.check("voice chat success", resp.get("success") is True)
        c.check("chatbot called once", fake_chat.await_count == 1)
        c.check(
            "selected_machine forwarded",
            fake_chat.await_args.kwargs.get("selected_machine_id") == "m1",
        )


def test_routing_parity_fields(c: Counter) -> None:
    """Same transcript should yield same parse features (catalog-driven)."""
    from app.ai.query_parser import parse_query

    catalog_queries = [
        "excavator in jaipur under 8000",
        "jcb 3dx rent mumbai",
        "Hyundai crane in delhi",
        "road roller pune",
        "volvo wheel loader bangalore",
    ]
    for q in catalog_queries:
        from app.ai.voice_input import build_voice_input_result

        vi = build_voice_input_result(q)
        p_text = parse_query(q)
        p_voice = parse_query(vi.routing_text)
        same = (
            p_text.get("category") == p_voice.get("category")
            and p_text.get("city") == p_voice.get("city")
            and p_text.get("brand") == p_voice.get("brand")
            and p_text.get("max_price") == p_voice.get("max_price")
            and p_text.get("listing_type") == p_voice.get("listing_type")
        )
        c.check(f"parity parse: {q!r}", same, str(p_text))


def main() -> int:
    c = Counter()
    print("\n=== Voice Phase V1 Tests ===")
    print(f"VOICE_PIPELINE_V2={os.getenv('VOICE_PIPELINE_V2', 'false')}\n")

    test_voice_input_validation(c)
    test_normalization_idempotence(c)
    test_audio_validation(c)
    test_file_cleanup(c)
    test_transcription_timeout(c)
    asyncio.run(test_concurrent_limit(c))
    test_no_raw_speech_in_logs(c)
    test_chat_isolation(c)
    asyncio.run(test_voice_single_chatbot_call(c))
    test_routing_parity_fields(c)

    print(f"\nVoice V1: {c.passed} passed, {c.failed} failed\n")
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
