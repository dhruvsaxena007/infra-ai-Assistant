"""
Voice-input processing — voice boundary only.

Produces a canonical VoiceInputResult before routing into chatbot_response().
Text /chat must never import this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.chatbot.language import detect_query_language
from app.ai.transcript_normalizer import normalize_transcribed_text


@dataclass
class VoiceInputResult:
    original_transcription: str
    routing_text: str
    detected_language: str
    corrections: list[str] = field(default_factory=list)
    is_empty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_transcription": self.original_transcription,
            "routing_text": self.routing_text,
            "detected_language": self.detected_language,
            "corrections": self.corrections,
            "is_empty": self.is_empty,
        }


_MEANINGFUL_TOKEN_RE = re.compile(r"[A-Za-z0-9\u0900-\u097F₹]+")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _is_repetitive_hallucination(text: str) -> bool:
    tokens = re.findall(r"\w+", text.lower())
    if len(tokens) < 4:
        return False
    unique = set(tokens)
    if len(unique) <= 2 and len(tokens) >= 6:
        return True
    if len(tokens) >= 8 and len(unique) / len(tokens) < 0.25:
        return True
    return False


def validate_transcript(original: str) -> tuple[bool, str]:
    """
    Structural validation — no phrase-specific rejection rules.
    Returns (ok, reason_code).
    """
    text = (original or "").strip()
    if not text:
        return False, "empty"
    if not _MEANINGFUL_TOKEN_RE.search(text):
        return False, "whitespace_only"
    tokens = _MEANINGFUL_TOKEN_RE.findall(text)
    if len(tokens) == 1 and len(tokens[0]) <= 1:
        return False, "too_short"
    if _is_repetitive_hallucination(text):
        return False, "repetitive"
    return True, ""


def build_voice_input_result(original_transcription: str) -> VoiceInputResult:
    """
    Single voice-boundary normalization before chatbot_response().
    Language is detected from the original before transliteration.
    """
    original = (original_transcription or "").strip()
    detected = detect_query_language(original)

    ok, _reason = validate_transcript(original)
    if not ok:
        return VoiceInputResult(
            original_transcription=original,
            routing_text="",
            detected_language=detected,
            corrections=[],
            is_empty=True,
        )

    corrections: list[str] = []
    preserve_devanagari = detected == "hindi" and bool(_DEVANAGARI_RE.search(original))
    routing = normalize_transcribed_text(
        original,
        strip_unmapped_non_latin=not preserve_devanagari,
    )

    if routing != original.lower().strip() and routing:
        corrections.append("voice_transliteration")

    if not routing:
        routing = original

    return VoiceInputResult(
        original_transcription=original,
        routing_text=routing,
        detected_language=detected,
        corrections=corrections,
        is_empty=False,
    )


def build_transcription_prompt() -> str:
    """Catalog-driven vocabulary hint for Whisper — no hardcoded test phrases."""
    try:
        from app.ai.category_mapping import CANONICAL_CATEGORIES, KNOWN_BRANDS

        categories = ", ".join(CANONICAL_CATEGORIES[:12])
        brands = ", ".join(KNOWN_BRANDS[:10])
    except Exception:
        categories = "excavator, crane, road roller, backhoe loader"
        brands = "JCB, Volvo, Caterpillar, Komatsu"

    return (
        "Transcribe construction equipment marketplace speech accurately. "
        "Use Devanagari for Hindi, Latin for English or Hinglish. "
        "Do NOT use Urdu or Arabic script. "
        f"Categories: {categories}. Brands: {brands}."
    )
