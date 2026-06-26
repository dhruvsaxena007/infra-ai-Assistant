"""
Voice transcription facade — single entry point for /voice/transcribe and /voice/chat.

Runs blocking Groq Whisper in a thread pool with timeout and concurrency limits.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from app.ai.voice_input import build_transcription_prompt, build_voice_input_result
from app.core.config import settings

logger = logging.getLogger(__name__)

_transcription_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _transcription_semaphore
    if _transcription_semaphore is None:
        _transcription_semaphore = asyncio.Semaphore(
            max(1, settings.VOICE_MAX_CONCURRENT_TRANSCRIPTIONS)
        )
    return _transcription_semaphore


def _redact_for_log(text: str, max_len: int = 24) -> str:
    t = (text or "").strip()
    if not t:
        return "<empty>"
    if len(t) <= max_len:
        return f"<len={len(t)}>"
    return f"<len={len(t)}>"


def _sync_transcribe(audio_file_path: str, *, language_hint: Optional[str]) -> dict[str, Any]:
    """Blocking Whisper call — run only inside asyncio.to_thread."""
    from app.core.ai_client import ai_transcribe_audio

    return ai_transcribe_audio(
        audio_file_path,
        language_hint=language_hint,
        prompt=build_transcription_prompt(),
    )


def _legacy_sync_transcribe(audio_file_path: str) -> dict[str, Any]:
    """Legacy path — Hindi bias + voice_service normalization (rollback)."""
    from app.ai.voice_service import transcribe_audio_legacy

    return transcribe_audio_legacy(audio_file_path)


async def transcribe_audio_file(
    audio_file_path: str,
    *,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Canonical async transcription facade.
    Returns dict with success, original_text, and optional voice_input (V2).
    """
    rid = request_id or str(uuid.uuid4())[:8]

    async with _get_semaphore():
        try:
            if settings.VOICE_PIPELINE_V2:
                language_hint = (settings.VOICE_STT_LANGUAGE_HINT or "").strip() or None
                raw = await asyncio.wait_for(
                    asyncio.to_thread(
                        _sync_transcribe,
                        audio_file_path,
                        language_hint=language_hint,
                    ),
                    timeout=settings.VOICE_STT_TIMEOUT_SECONDS,
                )
            else:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(_legacy_sync_transcribe, audio_file_path),
                    timeout=settings.VOICE_STT_TIMEOUT_SECONDS,
                )
        except asyncio.TimeoutError:
            logger.warning("voice.stt_timeout request_id=%s", rid)
            return {"success": False, "error": "stt_timeout", "request_id": rid}
        except Exception as exc:
            logger.warning(
                "voice.stt_error request_id=%s error_type=%s",
                rid,
                type(exc).__name__,
            )
            return {"success": False, "error": "stt_provider_error", "request_id": rid}

    if not raw.get("success"):
        return raw

    original = (raw.get("original_text") or raw.get("text") or "").strip()
    logger.info(
        "voice.stt_ok request_id=%s transcript=%s pipeline_v2=%s",
        rid,
        _redact_for_log(original),
        settings.VOICE_PIPELINE_V2,
    )

    if settings.VOICE_PIPELINE_V2:
        voice_input = build_voice_input_result(original)
        return {
            "success": True,
            "original_text": voice_input.original_transcription,
            "text": voice_input.routing_text or original,
            "voice_input": voice_input.to_dict(),
            "request_id": rid,
        }

    return {
        "success": True,
        "original_text": raw.get("original_text") or raw.get("text"),
        "text": raw.get("text"),
        "normalized_text": raw.get("normalized_text"),
        "request_id": rid,
    }
