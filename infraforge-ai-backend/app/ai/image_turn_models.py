"""
Image turn result models for IMG-1 pipeline integration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

ImageIntent = Literal[
    "exact_match",
    "similar_category",
    "identify_only",
    "availability_search",
    "unclear",
    "non_machine",
    "low_confidence",
    "unsupported",
]

SearchMode = Literal[
    "exact_requested",
    "similar_category",
    "category_search",
    "identify_only",
    "none",
]

# Clarification chips shown when category is confident but user intent is unclear.
IMAGE_INTENT_CLARIFICATION_CHIPS = [
    "Exact same machine",
    "Similar machines",
    "Just identify this machine",
]

IMAGE_INTENT_CLARIFICATION_CHIPS_HI = [
    "Bilkul same machine",
    "Similar machines dikhao",
    "Bas identify karo",
]

_CHIP_INTENT_MAP: dict[str, str] = {}
for _chip, _intent in (
    ("Exact same machine", "exact_match"),
    ("Similar machines", "similar_category"),
    ("Just identify this machine", "identify_only"),
    ("Bilkul same machine", "exact_match"),
    ("Similar machines dikhao", "similar_category"),
    ("Bas identify karo", "identify_only"),
):
    _CHIP_INTENT_MAP[re.sub(r"\s+", " ", _chip.strip().lower())] = _intent


def normalize_image_chip_label(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_image_clarification_chip(text: str) -> bool:
    return normalize_image_chip_label(text) in _CHIP_INTENT_MAP


def image_chip_to_intent(text: str) -> str | None:
    return _CHIP_INTENT_MAP.get(normalize_image_chip_label(text))


def all_image_clarification_chips() -> list[str]:
    return list(IMAGE_INTENT_CLARIFICATION_CHIPS) + list(IMAGE_INTENT_CLARIFICATION_CHIPS_HI)


@dataclass
class ImageTurnResult:
    upload_id: str
    original_filename: str
    detected_category: str | None
    detected_brand: str | None
    detected_model: str | None
    suggested_categories: list[str]
    visual_features: dict[str, Any]
    classifier_used: str
    confidence: float
    image_intent: str
    needs_clarification: bool
    clarification_question: str | None
    should_search: bool
    search_mode: str
    safe_user_message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context_dict(self) -> dict[str, Any]:
        """Serializable subset for image_context_memory."""
        return {
            "upload_id": self.upload_id,
            "detected_category": self.detected_category,
            "detected_machine_type": self.detected_category,
            "detected_brand": self.detected_brand,
            "detected_model": self.detected_model,
            "suggested_categories": list(self.suggested_categories),
            "confidence": self.confidence,
            "classifier_used": self.classifier_used,
            "image_intent": self.image_intent,
            "search_mode": self.search_mode,
            "search_query": self.detected_category,
            "awaiting_image_choice": self.needs_clarification,
            "pending_image_intent": (
                "similar_category"
                if self.image_intent == "unclear"
                else self.image_intent
            ),
        }

    def to_response_metadata(self) -> dict[str, Any]:
        """Image metadata merged into standard chat payloads."""
        return {
            "upload_id": self.upload_id,
            "detected_machine_type": self.detected_category,
            "detected_machine_display": self.metadata.get("display_label"),
            "detected_brand": self.detected_brand,
            "detected_model": self.detected_model,
            "suggested_categories": self.suggested_categories,
            "category_scores": self.metadata.get("category_scores"),
            "intent_confidence": self.confidence,
            "confidence": self.confidence,
            "classifier": self.classifier_used,
            "classifier_used": self.classifier_used,
            "image_intent": self.image_intent,
            "search_mode": self.search_mode,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "yolo_model_loaded": self.metadata.get("yolo_model_loaded", False),
            "predictions": self.metadata.get("predictions"),
            "image_context_saved": bool(self.detected_category),
            "match_type": self._legacy_match_type(),
        }

    def _legacy_match_type(self) -> str:
        if self.needs_clarification:
            return "image_clarification"
        if self.image_intent == "non_machine":
            return "unknown"
        if self.image_intent == "low_confidence":
            return "image_clarification"
        if self.image_intent == "exact_match":
            return "exact_requested"
        if self.detected_category:
            return "category"
        return "unknown"
