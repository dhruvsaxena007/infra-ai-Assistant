"""
YOLOv8/YOLO11 image classification (local, trained on InfraForge listing photos).

Train with: python scripts/train_yolo_classifier.py
Set YOLO_MODEL_PATH in .env to the exported best.pt weights.
"""

from __future__ import annotations

import os
import re
import threading

from app.ai.category_mapping import (
    CANONICAL_CATEGORIES,
    canonicalize_category,
    category_label,
    marketplace_category_to_canonical,
)

from app.core.config import settings

# Training export may include a catch-all folder — never use for search
_REJECT_LABELS = frozenset({"unknown", "other", "misc", "general", "n_a", "na"})

_model = None
_model_lock = threading.Lock()
_class_names: list[str] = []

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def resolve_yolo_model_path() -> str:
    path = (settings.YOLO_MODEL_PATH or "").strip()
    if not path:
        return ""
    if not os.path.isabs(path):
        path = os.path.join(_PROJECT_ROOT, path)
    return path


def warmup_yolo_background() -> None:
    """Load YOLO weights in background so first /image-search is faster."""
    if not yolo_model_available():
        return

    def _run() -> None:
        try:
            _get_model()
            print("[yolo] Background warm-up complete")
        except Exception as exc:
            print(f"[yolo] Background warm-up failed: {exc}")

    threading.Thread(target=_run, name="yolo-warmup", daemon=True).start()


def yolo_model_available() -> bool:
    path = resolve_yolo_model_path()
    return bool(path and os.path.isfile(path))


def _get_model():
    global _model, _class_names
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from ultralytics import YOLO

            _model = YOLO(resolve_yolo_model_path())
            names = getattr(_model, "names", None) or {}
            if isinstance(names, dict):
                _class_names = [names[i] for i in sorted(names.keys())]
            elif isinstance(names, list):
                _class_names = list(names)
    return _model


def _as_float(value) -> float:
    """Convert torch/numpy scalars to Python float."""
    if value is None:
        return 0.0
    if hasattr(value, "item"):
        return float(value.item())
    return float(value)


def _as_int_list(value) -> list[int]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        return [int(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [int(x) for x in value]
    return [int(value)]


def _as_float_list(value) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        return [float(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    return [float(value)]


def is_valid_machine_category(category: str | None) -> bool:
    if not category:
        return False
    lowered = str(category).strip().lower().replace("_", " ")
    if lowered in _REJECT_LABELS:
        return False
    if lowered in CANONICAL_CATEGORIES:
        return True
    return bool(canonicalize_category(lowered) or marketplace_category_to_canonical(lowered))


def _dir_to_canonical(dirname: str) -> str:
    """Map training folder name back to canonical category (spaces restored)."""
    if not dirname:
        return ""
    lowered = dirname.replace("_", " ").strip().lower()
    if lowered in _REJECT_LABELS:
        return ""
    canonical = canonicalize_category(lowered) or marketplace_category_to_canonical(lowered)
    return canonical or ""


def _pick_best_prediction(
    names: dict,
    top5_idx: list[int],
    top5_conf: list[float],
) -> tuple[str, float, str, list[dict]]:
    """Skip unknown/invalid YOLO classes; pick highest valid confidence."""
    predictions = []
    ranked = sorted(zip(top5_idx, top5_conf), key=lambda x: x[1], reverse=True)

    for idx, conf in ranked:
        raw_label = names.get(int(idx), str(idx)) if isinstance(names, dict) else str(idx)
        canonical = _dir_to_canonical(str(raw_label))
        predictions.append({
            "label": str(raw_label),
            "canonical_category": canonical or None,
            "confidence": float(conf),
        })
        if is_valid_machine_category(canonical):
            return canonical, float(conf), str(raw_label), predictions

    if predictions:
        best = predictions[0]
        return (
            best.get("canonical_category") or "",
            float(best.get("confidence") or 0),
            str(best.get("label") or ""),
            predictions,
        )
    return "", 0.0, "", predictions


def classify_machine_image_yolo(image_path: str, *, min_confidence: float = 0.12):
    """
    Classify using fine-tuned YOLO classify weights.
    Returns None when model file is missing (caller should fallback).
    """
    if not yolo_model_available():
        return None

    try:
        model = _get_model()
        results = model(image_path, verbose=False)
        if results is None or len(results) == 0:
            return {"success": False, "error": "empty YOLO result"}

        result = results[0]
        probs = getattr(result, "probs", None)
        if probs is None:
            return {"success": False, "error": "YOLO result has no probabilities"}

        names = result.names or getattr(model, "names", {})
        top5_idx = _as_int_list(getattr(probs, "top5", None))
        top5_conf = _as_float_list(getattr(probs, "top5conf", None))
        if not top5_idx:
            top5_idx = [int(_as_float(getattr(probs, "top1", 0)))]
            top5_conf = [_as_float(getattr(probs, "top1conf", 0))]

        canonical, top_conf, raw_label, predictions = _pick_best_prediction(
            names if isinstance(names, dict) else {},
            top5_idx,
            top5_conf,
        )

        success = is_valid_machine_category(canonical) and top_conf >= min_confidence

        return {
            "success": success,
            "classifier": "yolo",
            "machine_type": canonical or None,
            "top_confidence": top_conf,
            "confident": success,
            "predictions": predictions,
            "raw_top_label": raw_label,
            "display_label": category_label(canonical) if canonical else "Unknown",
        }

    except Exception as exc:
        return {"success": False, "error": str(exc), "classifier": "yolo"}
