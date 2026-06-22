"""
Thin adapter: POST /image-search → validate → classify → resolve → chatbot_response().

No direct MongoDB search bypassing the canonical assistant pipeline.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.ai.image_classifier import classify_marketplace_image
from app.ai.image_turn_models import IMAGE_INTENT_CLARIFICATION_CHIPS
from app.ai.image_turn_resolver import resolve_image_turn
from app.ai.image_validation import (
    cleanup_image_path,
    resize_image_if_needed,
    save_validated_image,
    validate_image_format,
)
from app.ai.yolo_classification_service import yolo_model_available
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.image_context_memory import save_image_context
from app.chatbot.session_usage_limits import (
    build_session_usage_payload,
    check_image_search_allowed,
    consume_image_search,
)
from app.database.mongodb import database
from app.utils.response import error_response, success_response

router = APIRouter()


def _friendly_validation_error(code: str) -> str:
    if code == "empty_file":
        return "Please upload a non-empty image file."
    if code == "file_too_large":
        return "Image is too large. Please upload a smaller photo (max 8 MB)."
    if code.startswith("invalid_mime"):
        return "Invalid image format. Please use JPG, PNG, or WebP."
    if code == "invalid_image_data":
        return "Could not read this image. Please upload a valid JPG, PNG, or WebP file."
    return "Invalid image upload."


def _clarification_suggestions(turn) -> list[str]:
    chips = turn.metadata.get("clarification_chips")
    if chips:
        return list(chips)
    return list(IMAGE_INTENT_CLARIFICATION_CHIPS)


def _merge_chat_with_image(chat_resp: dict, turn, *, user_caption: str = "", session_id: str = "") -> dict:
    """Attach image metadata to a standard chatbot_response envelope."""
    if not chat_resp.get("success"):
        return chat_resp

    data = dict(chat_resp.get("data") or {})
    img_meta = turn.to_response_metadata()
    data.update(img_meta)
    if session_id.strip():
        data["session_usage"] = build_session_usage_payload(session_id)
    data["assistant_mode"] = data.get("assistant_mode") or (
        "image_search" if turn.should_search else "image_clarification"
    )
    data["image_turn"] = {
        "upload_id": turn.upload_id,
        "image_intent": turn.image_intent,
        "search_mode": turn.search_mode,
        "user_caption": user_caption or None,
    }
    ctx = dict(data.get("context") or {})
    ctx["image_intent"] = turn.image_intent
    ctx["search_mode"] = turn.search_mode
    ctx["classifier_used"] = turn.classifier_used
    ctx["image_confidence"] = turn.confidence
    data["context"] = ctx

    message = chat_resp.get("message") or turn.safe_user_message
    lead = turn.metadata.get("assistant_lead")
    if lead and turn.should_search and lead not in message:
        message = f"{lead}\n\n{message}"

    return success_response(message=message, data=data)


def _clarification_only_response(turn, *, session_id: str) -> dict:
    if session_id.strip() and turn.detected_category:
        save_image_context(session_id.strip(), full_context=turn.to_context_dict())

    suggestions = _clarification_suggestions(turn)
    msg = turn.clarification_question or turn.safe_user_message
    data = turn.to_response_metadata()
    data.update({
        "results": [],
        "machines": [],
        "search_status": {
            "exact_match": False,
            "fallback_used": False,
            "fallback_reason": turn.metadata.get("fallback_reason") or "image_clarification",
        },
        "assistant_mode": "image_clarification",
        "suggestions": suggestions,
        "image_context_saved": bool(session_id.strip() and turn.detected_category),
    })
    if session_id.strip():
        data["session_usage"] = build_session_usage_payload(session_id)
    return success_response(message=msg, data=data)


@router.post("/image-search")
async def image_search(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    message: str = Form(default=""),
):
    """
    Upload image (+ optional caption) → classify → resolve intent → canonical pipeline.
    """
    upload_id = str(uuid.uuid4())
    file_path: str | None = None
    user_caption = (message if isinstance(message, str) else "") or ""
    sid = session_id.strip()

    if sid:
        allowed, used, limit = check_image_search_allowed(sid)
        if not allowed:
            return error_response(
                message=(
                    f"You've reached the image search limit ({limit} per session). "
                    "Start a new chat to continue."
                ),
                error={
                    "stage": "session_limit_exceeded",
                    "limit_type": "image_search",
                    "limit": limit,
                    "used": used,
                },
            )
        ok, _, _ = consume_image_search(sid)
        if not ok:
            return error_response(
                message=(
                    f"You've reached the image search limit ({limit} per session). "
                    "Start a new chat to continue."
                ),
                error={
                    "stage": "session_limit_exceeded",
                    "limit_type": "image_search",
                    "limit": limit,
                    "used": used,
                },
            )

    try:
        raw = await file.read()
        validation = validate_image_format(file, raw)
        if not validation.ok:
            return error_response(
                message=_friendly_validation_error(validation.error or "invalid"),
                error={"stage": "validation", "code": validation.error},
            )

        file_path = save_validated_image(validation.file_bytes, validation.safe_filename or f"{upload_id}.jpg")
        file_path = resize_image_if_needed(file_path)

        pipeline = classify_marketplace_image(file_path)
        turn = resolve_image_turn(
            pipeline=pipeline,
            user_text=user_caption,
            session_id=session_id,
            original_filename=file.filename or "upload",
            upload_id=upload_id,
        )

        sid = session_id.strip()

        if turn.detected_category and turn.image_intent not in ("non_machine", "low_confidence"):
            if sid:
                save_image_context(sid, full_context=turn.to_context_dict())

        if turn.needs_clarification and not turn.should_search:
            return _clarification_only_response(turn, session_id=session_id)

        if turn.should_search and sid:
            search_message = turn.safe_user_message
            if user_caption and user_caption.lower() not in search_message.lower():
                search_message = f"{search_message} {user_caption}".strip()

            chat_resp = await chatbot_response(sid, search_message, database)
            return _merge_chat_with_image(chat_resp, turn, user_caption=user_caption, session_id=sid)

        # identify_only / unsupported without search
        return _clarification_only_response(turn, session_id=session_id)

    except Exception:
        return error_response(
            message=(
                "I could not process this image right now. "
                "Try a clearer machine photo or search by text."
            ),
            error={"stage": "processing"},
        )
    finally:
        cleanup_image_path(file_path)
