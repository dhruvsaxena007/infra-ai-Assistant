"""
MobileNetV2 image classification — lazy-loaded on first classify request.
"""

from __future__ import annotations

import threading

import numpy as np

_model = None
_model_lock = threading.Lock()

# ImageNet top-1 is often low for industrial photos; intent layer uses top-5.
TOP_K_PREDICTIONS = 5
# Soft floor — real gate is image_intent_service intent score
DEFAULT_CONFIDENCE_THRESHOLD = 0.12


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2
            except ImportError as exc:
                raise ImportError(
                    "TensorFlow is not installed. On Python 3.14 use YOLO/OpenCV only, "
                    "or install Python 3.12 and run: pip install -r requirements-ml-extras.txt"
                ) from exc
            _model = MobileNetV2(weights="imagenet")
    return _model


def classify_machine_image(
    image_path: str,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
):
    """
    Classify an image. TensorFlow loads only on the first call.
    Returns top-K ImageNet labels; `confident` is a soft MobileNet flag only.
    """
    try:
        from tensorflow.keras.applications.mobilenet_v2 import (
            decode_predictions,
            preprocess_input,
        )
        from tensorflow.keras.preprocessing import image as keras_image

        img = keras_image.load_img(image_path, target_size=(224, 224))
        img_array = keras_image.img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        img_array = preprocess_input(img_array)

        model = _load_model()
        predictions = model.predict(img_array, verbose=0)
        decoded = decode_predictions(predictions, top=TOP_K_PREDICTIONS)[0]

        results = []
        for item in decoded:
            results.append({
                "label": item[1],
                "confidence": float(item[2]),
            })

        top_confidence = results[0]["confidence"] if results else 0.0
        confident = top_confidence >= confidence_threshold

        return {
            "success": True,
            "predictions": results,
            "top_confidence": top_confidence,
            "confident": confident,
            "confidence_threshold": confidence_threshold,
        }

    except ImportError:
        return {
            "success": False,
            "error": "tensorflow_unavailable",
        }
    except Exception:
        return {
            "success": False,
            "error": "mobilenet_classification_failed",
        }
