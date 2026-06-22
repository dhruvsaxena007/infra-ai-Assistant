import logging
import os
import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.ai.rules_understanding import build_chat_input_metadata
from app.ai.voice_audio_validation import (
    safe_delete_file,
    save_upload_bounded,
    validate_audio_format,
    validate_audio_upload,
)
from app.ai.voice_transcription import transcribe_audio_file
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.session_usage_limits import (
    build_session_usage_payload,
    check_voice_allowed,
    consume_voice_message,
)
from app.core.config import settings
from app.database.mongodb import database
from app.utils.response import error_response, success_response

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = settings.AUDIO_UPLOAD_DIR

os.makedirs(UPLOAD_DIR, exist_ok=True)

_RETRY_MESSAGE = "I couldn't hear that clearly. Please try again."


def _voice_retry_response(*, stage: str, error: dict | None = None):
    return error_response(
        message=_RETRY_MESSAGE,
        error={"stage": stage, **(error or {})},
    )


async def _persist_and_transcribe(
    file: UploadFile,
    *,
    request_id: str,
) -> tuple[dict | None, dict | None]:
    """
    Save upload with validation, transcribe, always cleanup temp file.
    Returns (transcription_result, error_response).
    """
    file_path: str | None = None

    fmt = validate_audio_format(file)
    if not fmt.ok:
        return None, error_response(
            message="Unsupported audio format.",
            error={"stage": "validation", "reason": fmt.error},
        )

    try:
        file_path = os.path.join(UPLOAD_DIR, fmt.safe_filename or f"{uuid.uuid4()}.webm")

        written, save_err = await save_upload_bounded(file, file_path)
        if save_err == "file_too_large":
            return None, error_response(
                message="Audio file is too large.",
                error={"stage": "validation", "reason": "file_too_large"},
            )
        if written <= 0:
            return None, _voice_retry_response(
                stage="validation",
                error={"reason": "empty_file"},
            )

        validation = validate_audio_upload(file, size_bytes=written)
        if not validation.ok:
            return None, error_response(
                message="Unsupported audio format.",
                error={"stage": "validation", "reason": validation.error},
            )

        result = await transcribe_audio_file(file_path, request_id=request_id)
        if not result.get("success"):
            err = result.get("error", "transcription_failed")
            if err == "stt_timeout":
                return None, error_response(
                    message="Voice transcription timed out. Please try again.",
                    error={"stage": "transcription", "reason": "timeout"},
                )
            return None, error_response(
                message="Audio transcription failed. Please try again.",
                error={"stage": "transcription", "reason": "provider_error"},
            )

        return result, None
    finally:
        safe_delete_file(file_path)


async def _route_voice_to_chat(
    *,
    session_id: str,
    transcription_result: dict,
    selected_machine_id: str | None,
) -> dict:
    """Invoke chatbot_response exactly once with prepared routing text."""
    if settings.VOICE_PIPELINE_V2:
        voice_meta = transcription_result.get("voice_input") or {}
        if voice_meta.get("is_empty"):
            return _voice_retry_response(
                stage="transcription",
                error={"reason": "empty_transcript"},
            )
        original = voice_meta.get("original_transcription") or ""
        routing_text = voice_meta.get("routing_text") or original
        detected_language = voice_meta.get("detected_language") or "english"
        corrections = voice_meta.get("corrections") or []
    else:
        original = (
            transcription_result.get("original_text")
            or transcription_result.get("text")
            or ""
        )
        routing_text = (
            transcription_result.get("normalized_text")
            or transcription_result.get("text")
            or original
        )
        from app.ai.message_normalizer import normalize_user_message_async

        norm = await normalize_user_message_async(routing_text or "")
        routing_text = norm.corrected or routing_text
        detected_language = "hinglish"
        corrections = norm.corrections or []

    input_meta = build_chat_input_metadata(
        original_message=original,
        normalized_message=routing_text,
        working_message=routing_text,
    )
    if corrections:
        input_meta["corrections"] = corrections

    chatbot_result = await chatbot_response(
        session_id,
        routing_text,
        database,
        selected_machine_id=selected_machine_id,
    )

    chat_data = chatbot_result.get("data", {}) or {}

    chat_data["voice_input"] = {
        "original_transcription": original,
        "normalized_text": routing_text,
        "original_voice_text": original,
        "detected_language": detected_language,
        "corrections": corrections,
        "enhanced_query": input_meta.get("enhanced_query") or routing_text,
        "text_understanding": input_meta.get("text_understanding"),
    }

    if not chat_data.get("input"):
        chat_data["input"] = input_meta
    else:
        chat_data["input"] = {
            **chat_data["input"],
            **input_meta,
            "voice_original": original,
        }

    ctx = chat_data.get("context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    chat_data["context"] = {
        **ctx,
        "voice": True,
        "corrections": corrections or ctx.get("corrections"),
    }
    chat_data["session_usage"] = build_session_usage_payload(session_id)

    return success_response(
        message=chatbot_result.get("message"),
        data=chat_data,
    )


@router.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    """Upload audio file and convert speech to text only."""
    request_id = str(uuid.uuid4())[:8]
    result, err = await _persist_and_transcribe(file, request_id=request_id)
    if err:
        return err

    payload = {
        "text": result.get("text"),
        "original_transcription": result.get("original_text"),
    }
    if settings.VOICE_PIPELINE_V2:
        payload["voice_input"] = result.get("voice_input")
    else:
        payload["normalized_text"] = result.get("normalized_text")

    return success_response(
        message="Audio transcribed successfully",
        data=payload,
    )


@router.post("/voice/chat")
async def voice_chat(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    selected_machine_id: str = Form(default=""),
):
    """
    Upload voice file → transcribe → same /chat pipeline as text.
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return error_response(
            message="session_id is required",
            error={"stage": "validation", "field": "session_id"},
        )

    selected_id = (selected_machine_id or "").strip() or None
    request_id = str(uuid.uuid4())[:8]

    allowed, used, limit = check_voice_allowed(session_id)
    if not allowed:
        return error_response(
            message=(
                f"You've reached the voice message limit ({limit} per session). "
                "Start a new chat to continue."
            ),
            error={
                "stage": "session_limit_exceeded",
                "limit_type": "voice_message",
                "limit": limit,
                "used": used,
            },
        )

    ok, _, _ = consume_voice_message(session_id)
    if not ok:
        return error_response(
            message=(
                f"You've reached the voice message limit ({limit} per session). "
                "Start a new chat to continue."
            ),
            error={
                "stage": "session_limit_exceeded",
                "limit_type": "voice_message",
                "limit": limit,
                "used": used,
            },
        )

    result, err = await _persist_and_transcribe(
        file,
        request_id=request_id,
    )
    if err:
        return err

    return await _route_voice_to_chat(
        session_id=session_id,
        transcription_result=result,
        selected_machine_id=selected_id,
    )
