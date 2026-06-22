import os
import re
import uuid

from fastapi import APIRouter, UploadFile, File, Form

from app.ai.category_search_fallback import search_category_with_fallback
from app.ai.category_mapping import category_label
from app.ai.image_classifier import classify_marketplace_image
from app.ai.yolo_classification_service import yolo_model_available
from app.chatbot.image_context_memory import save_image_context
from app.database.mongodb import database
from app.utils.response import success_response, error_response

router = APIRouter()

from app.core.config import settings

UPLOAD_DIR = settings.IMAGE_SEARCH_UPLOAD_DIR

ALLOWED_IMAGE_EXTENSIONS = [
    "jpg",
    "jpeg",
    "png",
    "webp",
]

os.makedirs(UPLOAD_DIR, exist_ok=True)

_TECHNICAL_ERROR = re.compile(
    r"(no module named|importerror|modulenotfound|traceback|exception)",
    re.I,
)


def _friendly_message(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text or _TECHNICAL_ERROR.search(text):
        return (
            "I could not identify the machine in this photo. "
            "Try a clearer side view, or search by text (e.g. crane in Jaipur)."
        )
    return text


def _top_category_from_scores(scores: dict | None) -> str | None:
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda x: float(x[1] or 0), reverse=True)
    if not ranked:
        return None
    cat, score = ranked[0]
    if float(score or 0) < 0.08:
        return None
    return cat


@router.post("/image-search")
async def image_search(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
):
    """
    Upload image → YOLO (InfraForge-trained) or MobileNet fallback → marketplace search.
    """

    if not file.filename:
        return error_response(
            message="Image file is required",
            error={"stage": "validation"},
        )

    file_extension = file.filename.split(".")[-1].lower()

    if file_extension not in ALLOWED_IMAGE_EXTENSIONS:
        return error_response(
            message="Invalid image format",
            error={
                "stage": "validation",
                "allowed_formats": ALLOWED_IMAGE_EXTENSIONS,
            },
        )

    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
    except Exception as e:
        return error_response(
            message="Failed to save uploaded image",
            error={"stage": "file_save", "details": str(e)},
        )

    pipeline = classify_marketplace_image(file_path)
    intent = pipeline.get("intent") or {}
    clf = pipeline.get("classification") or {}

    if not pipeline.get("success"):
        rescue = _top_category_from_scores(intent.get("category_scores"))
        if rescue:
            intent = {
                "match_type": "exact",
                "machine_type": rescue,
                "search_query": rescue,
                "suggested_categories": [rescue],
                "category_scores": intent.get("category_scores"),
                "intent_confidence": intent.get("intent_confidence") or 0.12,
                "confident": False,
                "message": f"Best guess: {category_label(rescue)} (moderate confidence).",
                "classifier": intent.get("classifier") or pipeline.get("stage", "visual"),
                "display_label": category_label(rescue),
            }
            pipeline = {"success": True, "intent": intent, "stage": pipeline.get("stage", "visual")}
        else:
            return success_response(
                message=_friendly_message(
                    pipeline.get("error") or intent.get("message")
                ),
                data={
                    "match_type": "image_clarification",
                    "detected_machine_type": None,
                    "detected_machine_display": None,
                    "search_query": None,
                    "suggested_categories": [
                        "excavator", "backhoe loader", "crane", "road roller",
                        "dump truck", "crawler drill", "motor grader", "wheel loader",
                        "hydra crane", "concrete mixer",
                    ],
                    "category_scores": intent.get("category_scores"),
                    "intent_confidence": float(intent.get("intent_confidence") or 0),
                    "classifier": intent.get("classifier") or pipeline.get("stage"),
                    "yolo_model_loaded": yolo_model_available(),
                    "predictions": clf.get("predictions") or intent.get("predictions"),
                    "results": [],
                    "machines": [],
                    "search_status": {
                        "exact_match": False,
                        "fallback_used": False,
                        "fallback_reason": "low_image_confidence",
                    },
                    "image_context_saved": False,
                    "assistant_mode": "image_clarification",
                },
            )

    intent = pipeline["intent"]
    predictions = intent.get("predictions") or clf.get("predictions", [])

    search_query = intent.get("search_query")
    detected_type = intent.get("machine_type") or search_query
    if not detected_type and intent.get("match_type") == "broad":
        suggested = intent.get("suggested_categories") or []
        detected_type = suggested[0] if suggested else _top_category_from_scores(
            intent.get("category_scores")
        )
        search_query = detected_type

    display_label = intent.get("display_label") or (
        category_label(detected_type) if detected_type else None
    )

    confidence = float(intent.get("intent_confidence") or 0)
    has_detection = bool(detected_type) and intent.get("match_type") != "unknown"

    if not has_detection:
        top = _top_category_from_scores(intent.get("category_scores"))
        if top:
            detected_type = top
            search_query = top
            display_label = category_label(top)
            has_detection = True
            intent["confident"] = False
            intent["message"] = (
                f"Best guess: {display_label} — showing closest matches."
            )

    if not has_detection:
        clarification_msg = (
            "I could not confidently detect the machine type. "
            "Pick a category below or search by text (e.g. wheel loader in Jaipur)."
        )
        return success_response(
            message=clarification_msg,
            data={
                "match_type": "image_clarification",
                "detected_machine_type": None,
                "detected_machine_display": None,
                "search_query": None,
                "suggested_categories": intent.get("suggested_categories") or [
                    "excavator", "backhoe loader", "crane", "road roller",
                    "dump truck", "crawler drill", "motor grader", "wheel loader",
                    "hydra crane", "concrete mixer",
                ],
                "category_scores": intent.get("category_scores"),
                "intent_confidence": confidence,
                "classifier": intent.get("classifier") or pipeline.get("stage"),
                "yolo_model_loaded": yolo_model_available(),
                "predictions": predictions,
                "results": [],
                "machines": [],
                "search_status": {
                    "exact_match": False,
                    "fallback_used": False,
                    "fallback_reason": "low_image_confidence",
                },
                "image_context_saved": False,
                "assistant_mode": "image_clarification",
            },
        )

    # Image category must not inherit stale chat category from session memory.
    city = None
    clean_results, search_meta = await search_category_with_fallback(
        database,
        detected_type,
        city=city,
        limit=5,
    )

    if session_id.strip() and detected_type:
        save_image_context(
            session_id.strip(),
            detected_machine_type=detected_type,
            suggested_categories=intent.get("suggested_categories", []),
            search_query=search_query,
        )

    message = intent.get("message")
    if search_meta.get("fallback_reason"):
        message = f"{message}\n\n{search_meta['fallback_reason']}"
    elif not clean_results:
        message = (
            f"Detected {display_label}, but no listings found right now. "
            "Try another city in chat (e.g. dump truck in Jaipur)."
        )

    return success_response(
        message=message,
        data={
            "match_type": intent.get("match_type"),
            "detected_machine_type": intent.get("machine_type"),
            "detected_machine_display": display_label,
            "search_query": search_query,
            "suggested_categories": intent.get("suggested_categories", []),
            "category_scores": intent.get("category_scores"),
            "intent_confidence": intent.get("intent_confidence"),
            "classifier": intent.get("classifier") or pipeline.get("stage"),
            "yolo_model_loaded": yolo_model_available(),
            "predictions": predictions,
            "results": clean_results,
            "machines": clean_results,
            "search_status": search_meta,
            "image_context_saved": bool(session_id.strip() and detected_type),
            "assistant_mode": "image_search",
        },
    )
