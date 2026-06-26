"""
Unified image classification: YOLO → MobileNet (optional) → CLIP + OpenCV.

Never surfaces raw import errors (e.g. missing TensorFlow on Python 3.14).
"""

from __future__ import annotations

import importlib.util
from typing import Any

from app.ai.image_classification_service import classify_machine_image
from app.ai.image_intent_service import (
    extract_machine_search_intent,
    should_accept_classification,
)
from app.ai.image_preprocess import classification_variants, cleanup_temp
from app.ai.yolo_classification_service import (
    classify_machine_image_yolo,
    is_valid_machine_category,
    yolo_model_available,
)
from app.ai.category_mapping import category_label
from app.core.config import settings

_YOLO_HIGH_CONF = 0.38
_FRIENDLY_FAILURE = (
    "I could not identify the machine in this photo. "
    "Try a clearer side view of the equipment, or search by text "
    "(e.g. wheel loader in Jaipur)."
)


def _tensorflow_available() -> bool:
    return importlib.util.find_spec("tensorflow") is not None


def _intent_from_detection(
    category: str,
    *,
    classifier: str,
    conf: float,
    predictions: list,
    confident: bool,
    category_scores: dict | None = None,
) -> dict[str, Any]:
    display = category_label(category)
    msg = f"Detected machine type: {display}"
    if not confident:
        msg += " (moderate confidence — add city in chat to refine)."
    return {
        "match_type": "exact",
        "machine_type": category,
        "search_query": category,
        "suggested_categories": [category],
        "category_scores": category_scores or {category: conf},
        "intent_confidence": round(conf, 4),
        "confident": confident,
        "message": msg,
        "classifier": classifier,
        "predictions": predictions,
        "display_label": display,
    }


def _best_visual_intent(image_path: str) -> tuple[dict[str, Any], str]:
    """CLIP + OpenCV across full frame and center crop."""
    best_intent: dict[str, Any] = {}
    best_path = image_path
    best_conf = -1.0

    for path, is_temp in classification_variants(image_path):
        try:
            intent = extract_machine_search_intent([], image_path=path)
            conf = float(intent.get("intent_confidence") or 0)
            if intent.get("match_type") != "unknown" and conf > best_conf:
                best_conf = conf
                best_intent = intent
                best_path = path
        finally:
            if is_temp:
                cleanup_temp(path, True)

    return best_intent, best_path


def _best_mobilenet_intent(image_path: str) -> tuple[dict, dict, str]:
    best_intent: dict = {}
    best_clf: dict = {}
    best_path = image_path
    best_conf = -1.0

    for path, is_temp in classification_variants(image_path):
        try:
            clf = classify_machine_image(path)
            if not clf.get("success"):
                continue
            preds = clf.get("predictions", [])
            intent = extract_machine_search_intent(preds, image_path=path)
            conf = float(intent.get("intent_confidence") or 0)
            if intent.get("match_type") != "unknown" and conf > best_conf:
                best_conf = conf
                best_intent = intent
                best_clf = clf
                best_path = path
        finally:
            if is_temp:
                cleanup_temp(path, True)

    return best_intent, best_clf, best_path


def _merge_yolo_into_intent(intent: dict, yolo: dict) -> dict:
    if is_valid_machine_category(intent.get("machine_type")):
        return intent

    for pred in yolo.get("predictions") or []:
        cat = pred.get("canonical_category")
        if is_valid_machine_category(cat):
            conf = float(pred.get("confidence") or 0)
            return _intent_from_detection(
                cat,
                classifier="yolo",
                conf=conf,
                predictions=yolo.get("predictions", []),
                confident=conf >= 0.12,
            )
    return intent


def _log_classify(
    *,
    stage: str,
    intent: dict,
    success: bool,
    fallback_reason: str | None = None,
) -> None:
    clf = (intent.get("classifier") or stage or "unknown").lower()
    cat = intent.get("machine_type") or intent.get("search_query")
    conf = float(intent.get("intent_confidence") or 0)
    print(
        "[image_classify]",
        f"classifier_used={clf}",
        f"confidence={conf:.4f}",
        f"detected_category={cat!r}",
        f"success={success}",
        f"fallback_reason={fallback_reason or 'none'}",
    )


def _failure_payload(
    *,
    stage: str,
    intent: dict,
    error: str,
    fallback_reason: str,
) -> dict[str, Any]:
    _log_classify(stage=stage, intent=intent, success=False, fallback_reason=fallback_reason)
    return {
        "success": False,
        "stage": stage,
        "intent": intent,
        "error": error,
        "fallback_reason": fallback_reason,
    }


def _success_payload(
    *,
    stage: str,
    intent: dict,
    classification: dict | None = None,
    variant_path: str | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    _log_classify(stage=stage, intent=intent, success=True, fallback_reason=fallback_reason)
    return {
        "success": True,
        "stage": stage,
        "classification": classification or {},
        "intent": intent,
        "variant_path": variant_path,
        "fallback_reason": fallback_reason,
    }


def classify_marketplace_image(image_path: str) -> dict[str, Any]:
    if settings.openai_usable and settings.USE_OPENAI_VISION:
        from app.core.ai_client import ai_vision_classify_machine

        vision = ai_vision_classify_machine(image_path)
        category = vision.get("machine_type") if vision else None
        if vision and is_valid_machine_category(category):
            return _success_payload(
                stage="openai_vision",
                intent=vision,
                classification={
                    "provider": "openai_vision",
                    "predictions": vision.get("predictions", []),
                },
            )

    use_yolo = settings.IMAGE_CLASSIFIER in ("auto", "yolo")
    use_mobilenet = settings.IMAGE_CLASSIFIER in ("auto", "mobilenet")
    tf_ok = _tensorflow_available()
    yolo: dict | None = None

    # --- 1) YOLO (trained weights) ------------------------------------------------
    if use_yolo and yolo_model_available():
        best_yolo: dict = {}
        best_yolo_conf = -1.0
        for path, is_temp in classification_variants(image_path):
            try:
                attempt = classify_machine_image_yolo(path) or {}
                cat = attempt.get("machine_type")
                c = float(attempt.get("top_confidence") or 0)
                if is_valid_machine_category(cat) and c > best_yolo_conf:
                    best_yolo_conf = c
                    best_yolo = attempt
            finally:
                if is_temp:
                    cleanup_temp(path, True)

        yolo = best_yolo or classify_machine_image_yolo(image_path) or {}
        category = yolo.get("machine_type")
        conf = float(yolo.get("top_confidence") or 0)
        if is_valid_machine_category(category) and conf >= _YOLO_HIGH_CONF:
            return _success_payload(
                stage="yolo",
                intent=_intent_from_detection(
                    category,
                    classifier="yolo",
                    conf=conf,
                    predictions=yolo.get("predictions", []),
                    confident=True,
                ),
                classification=yolo,
            )

        if settings.IMAGE_CLASSIFIER == "yolo" and not use_mobilenet:
            visual_intent, _ = _best_visual_intent(image_path)
            if is_valid_machine_category(visual_intent.get("machine_type")):
                visual_intent["classifier"] = visual_intent.get("classifier", "clip+opencv")
                return _success_payload(stage="visual", intent=visual_intent)

    # --- 2) MobileNet + visual ensemble (when TensorFlow installed) ---------------
    intent_mv: dict = {}
    clf_mv: dict = {}
    if use_mobilenet and tf_ok:
        intent_mv, clf_mv, used_path = _best_mobilenet_intent(image_path)
        if intent_mv.get("match_type") != "unknown" and is_valid_machine_category(
            intent_mv.get("machine_type")
        ):
            if yolo:
                intent_mv = _merge_yolo_into_intent(intent_mv, yolo)
            intent_mv["classifier"] = intent_mv.get("classifier", "mobilenet+visual")
            intent_mv["predictions"] = clf_mv.get("predictions", [])
            intent_mv["display_label"] = category_label(intent_mv["machine_type"])
            return _success_payload(
                stage="mobilenet",
                intent=intent_mv,
                classification=clf_mv,
                variant_path=used_path if used_path != image_path else None,
            )

        clf = classify_machine_image(image_path)
        if clf.get("success"):
            predictions = clf.get("predictions", [])
            if should_accept_classification(predictions, image_path=image_path):
                intent = intent_mv if intent_mv else extract_machine_search_intent(
                    predictions, image_path=image_path
                )
                intent["classifier"] = intent.get("classifier", "mobilenet+visual")
                intent["predictions"] = predictions
                if yolo:
                    intent = _merge_yolo_into_intent(intent, yolo)
                if is_valid_machine_category(intent.get("machine_type")):
                    intent["display_label"] = category_label(intent["machine_type"])
                    return _success_payload(
                        stage="mobilenet",
                        intent=intent,
                        classification=clf,
                    )

    # --- 3) CLIP + OpenCV (always available — Python 3.14 safe) -------------------
    visual_intent, used_path = _best_visual_intent(image_path)
    if is_valid_machine_category(visual_intent.get("machine_type")):
        visual_intent["display_label"] = category_label(visual_intent["machine_type"])
        if yolo and not visual_intent.get("confident"):
            visual_intent = _merge_yolo_into_intent(visual_intent, yolo)
        return _success_payload(
            stage="visual",
            intent=visual_intent,
            variant_path=used_path if used_path != image_path else None,
        )

    # YOLO low-confidence fallback
    if yolo and is_valid_machine_category(yolo.get("machine_type")):
        cat = yolo["machine_type"]
        conf = float(yolo.get("top_confidence") or 0)
        return _success_payload(
            stage="yolo",
            intent=_intent_from_detection(
                cat,
                classifier="yolo",
                conf=conf,
                predictions=yolo.get("predictions", []),
                confident=conf >= 0.12,
            ),
            classification=yolo,
        )

    # Broad / ambiguous visual match — clarification only (no machine search)
    if visual_intent.get("match_type") == "broad":
        visual_intent["display_label"] = None
        visual_intent["machine_type"] = None
        return _failure_payload(
            stage="visual",
            intent=visual_intent,
            error=visual_intent.get("message") or _FRIENDLY_FAILURE,
            fallback_reason="ambiguous_broad_match",
        )

    if visual_intent:
        return _failure_payload(
            stage="visual",
            intent=visual_intent,
            error=visual_intent.get("message") or _FRIENDLY_FAILURE,
            fallback_reason="low_confidence_visual",
        )

    return _failure_payload(
        stage="visual",
        intent={},
        error=_FRIENDLY_FAILURE,
        fallback_reason="no_classifier_match",
    )
