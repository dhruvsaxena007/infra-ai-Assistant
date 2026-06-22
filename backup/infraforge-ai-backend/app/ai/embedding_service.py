"""
Shared SentenceTransformer singleton — load once on first use.
Optional background warm-up on server start (see WARMUP_EMBEDDING_ON_STARTUP).
"""

from __future__ import annotations

import threading

from app.core.config import settings

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None
_model_lock = threading.Lock()
_warmup_started = False


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(_MODEL_NAME)
    return _model


def is_model_ready() -> bool:
    return _model is not None


def warmup_embeddings_background() -> None:
    """Load the embedding model in a daemon thread (non-blocking startup)."""
    global _warmup_started
    if _warmup_started or not settings.WARMUP_EMBEDDING_ON_STARTUP:
        return
    _warmup_started = True

    def _run() -> None:
        try:
            generate_embedding("infraforge warmup")
            print("[embedding_service] Background warm-up complete")
        except Exception as exc:
            print(f"[embedding_service] Background warm-up failed: {exc}")

    threading.Thread(target=_run, name="embedding-warmup", daemon=True).start()


def generate_embedding(text: str) -> list:
    """Encode text to a list of floats (API/JSON safe)."""
    text = (text or "").strip() or " "
    embedding = _get_model().encode(text, show_progress_bar=False)
    return embedding.tolist()
