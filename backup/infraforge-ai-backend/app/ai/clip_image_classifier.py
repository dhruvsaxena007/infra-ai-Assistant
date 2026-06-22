"""
CLIP-based zero-shot image classification for construction equipment.

Uses sentence-transformers (clip-ViT-B-32) — no TensorFlow required.
Lazy-loaded; text prompts for all canonical categories are encoded once.
"""

from __future__ import annotations

import importlib.util
import threading
from functools import lru_cache
from typing import Any

from app.ai.category_mapping import category_label

_CLIP_MODEL_NAME = "clip-ViT-B-32"
_CLIP_WEIGHT = 1.35

# Focused set for fast zero-shot (covers common user uploads).
_CLIP_CATEGORIES: tuple[str, ...] = (
    "wheel loader",
    "backhoe loader",
    "excavator",
    "bulldozer",
    "dump truck",
    "road roller",
    "motor grader",
    "crane",
    "hydra crane",
    "truck mounted crane",
    "concrete mixer",
    "concrete mixer truck",
    "concrete pump",
    "crawler drill",
    "drill rig",
    "forklift",
    "telehandler",
    "mobile crusher",
    "air compressor",
    "compactor",
    "asphalt paver",
    "boom lift",
    "scissor lift",
    "articulated hauler",
)

_model = None
_prompt_embeddings: dict[str, Any] | None = None
_lock = threading.Lock()
_warmup_started = False

# Rich prompts improve zero-shot accuracy vs a single label.
_CATEGORY_PROMPTS: dict[str, list[str]] = {
    "wheel loader": [
        "a photo of a yellow wheel loader front end loader construction machine",
        "wheel loader with large front bucket on a construction site",
    ],
    "backhoe loader": [
        "a photo of a JCB backhoe loader construction machine",
        "backhoe loader with front loader bucket and rear digger arm",
    ],
    "excavator": [
        "a photo of a hydraulic excavator digger on tracks",
        "crawler excavator construction machine with digging arm",
    ],
    "bulldozer": [
        "a photo of a bulldozer crawler dozer with front blade",
    ],
    "dump truck": [
        "a photo of a dump truck tipper dumper construction vehicle",
        "heavy duty mining dump truck haul truck",
    ],
    "road roller": [
        "a photo of a road roller steam roller compactor on asphalt",
    ],
    "motor grader": [
        "a photo of a motor grader road grading machine",
    ],
    "crane": [
        "a photo of a construction crane with long boom",
        "tower crane or crawler crane at a building site",
    ],
    "hydra crane": [
        "a photo of a mobile truck crane hydra crane on a street",
        "truck mounted mobile crane with telescopic boom",
    ],
    "concrete mixer": [
        "a photo of a concrete mixer cement mixer truck drum",
    ],
    "concrete pump": [
        "a photo of a concrete pump truck with boom pipeline",
    ],
    "crawler drill": [
        "a photo of a crawler drill rig piling machine",
        "drilling rig construction equipment tall mast",
    ],
    "forklift": [
        "a photo of a forklift warehouse lifting machine",
    ],
    "telehandler": [
        "a photo of a telehandler telescopic handler construction lift",
    ],
    "mobile crusher": [
        "a photo of a mobile stone crusher screening plant",
    ],
    "air compressor": [
        "a photo of a portable air compressor construction equipment",
    ],
    "compactor": [
        "a photo of a soil compactor vibratory roller",
    ],
    "asphalt paver": [
        "a photo of an asphalt paver road paving machine",
    ],
    "boom lift": [
        "a photo of a boom lift aerial work platform",
    ],
    "scissor lift": [
        "a photo of a scissor lift elevated work platform",
    ],
}


def _default_prompt(category: str) -> str:
    label = category_label(category)
    return f"a photo of a {label} construction equipment machine"


def clip_available() -> bool:
    if importlib.util.find_spec("sentence_transformers") is None:
        return False
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def _build_prompt_embeddings():
    global _prompt_embeddings
    if _prompt_embeddings is not None:
        return _prompt_embeddings

    from sentence_transformers import SentenceTransformer
    import numpy as np

    model = _get_clip_model()
    embeddings: dict[str, Any] = {}

    for category in _CLIP_CATEGORIES:
        prompts = _CATEGORY_PROMPTS.get(category) or [_default_prompt(category)]
        text_emb = model.encode(prompts, show_progress_bar=False, normalize_embeddings=True)
        if len(text_emb.shape) == 1:
            text_emb = text_emb.reshape(1, -1)
        embeddings[category] = np.asarray(text_emb, dtype=np.float32)

    _prompt_embeddings = embeddings
    return embeddings


def _get_clip_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(_CLIP_MODEL_NAME)
    return _model


def warmup_clip_background() -> None:
    """Optional background warm-up (non-blocking)."""
    global _warmup_started
    if _warmup_started or not clip_available():
        return
    _warmup_started = True

    def _run() -> None:
        try:
            _build_prompt_embeddings()
            print("[clip] Background warm-up complete")
        except Exception as exc:
            print(f"[clip] Background warm-up failed: {exc}")

    threading.Thread(target=_run, name="clip-warmup", daemon=True).start()


@lru_cache(maxsize=48)
def clip_category_scores(image_path: str) -> dict[str, float]:
    """
    Zero-shot CLIP similarity scores per canonical category (0–1 scale).
    Returns {} when CLIP is unavailable or the image cannot be read.
    """
    if not clip_available() or not image_path:
        return {}

    try:
        import numpy as np
        from PIL import Image

        model = _get_clip_model()
        prompt_emb = _build_prompt_embeddings()

        with Image.open(image_path) as pil:
            pil = pil.convert("RGB")
            pil.thumbnail((512, 512))
            img_emb = model.encode(pil, show_progress_bar=False, normalize_embeddings=True)
        img_emb = np.asarray(img_emb, dtype=np.float32).reshape(-1)

        scores: dict[str, float] = {}
        for category, text_matrix in prompt_emb.items():
            sims = text_matrix @ img_emb
            best = float(np.max(sims)) if sims.size else 0.0
            if best > 0.12:
                scores[category] = round(best * _CLIP_WEIGHT, 4)

        return scores
    except Exception as exc:
        print(f"[clip] classify failed: {exc}")
        return {}
