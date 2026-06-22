"""
Resolve user intent for an image turn (IMG-1).

Structural rules for English / Hinglish / Hindi — not phrase-list-only matching.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.ai.category_mapping import category_label
from app.ai.query_parser import parse_query
from app.ai.image_turn_models import (
    IMAGE_INTENT_CLARIFICATION_CHIPS,
    IMAGE_INTENT_CLARIFICATION_CHIPS_HI,
    ImageTurnResult,
)
from app.ai.yolo_classification_service import yolo_model_available
from app.core.config import settings

# --- Structural intent detectors ------------------------------------------------

_RE_EXACT = re.compile(
    r"(?i)\b("
    r"exact(?:\s+same)?|same\s+(?:machine|listing|one|photo|pic|wala|wali)|"
    r"bilkul\s+same|yehi\s+machine|wahi\s+machine|same\s+chahiye|"
    r"isi\s+listing|exact\s+match"
    r")\b",
)

_RE_SIMILAR = re.compile(
    r"(?i)\b("
    r"similar|same\s+type|isi\s+type|aisi\s+machine|jaisi|"
    r"similar\s+(?:machine|dikhao|machines)|milti\s+julti|"
    r"is\s+type\s+ki|type\s+ki\s+machine"
    r")\b",
)

_RE_IDENTIFY = re.compile(
    r"(?i)\b("
    r"what\s+is\s+this|identify|ye\s+kya|yeh\s+kya|kya\s+machine|"
    r"kya\s+hai|batado|batao|bata\s+do|machine\s+kya\s+hai|"
    r"ye\s+konsi|yeh\s+konsi|konsi\s+machine"
    r")\b",
)

_RE_AVAILABILITY = re.compile(
    r"(?i)\b("
    r"available|availability|milega|milegi|milti|milta|"
    r"chahiye|dikhao|dikha\s+do|search\s+karo|find"
    r")\b",
)

_RE_NON_MACHINE_HINT = re.compile(
    r"(?i)\b(person|face|food|cat|dog|car|bike|selfie|screenshot)\b",
)


def _normalize_classifier(stage: str | None, intent: dict | None) -> str:
    raw = ((intent or {}).get("classifier") or stage or "unknown").lower()
    if "yolo" in raw:
        return "yolo"
    if "mobilenet" in raw:
        return "mobilenet"
    if "clip" in raw and "opencv" in raw:
        return "clip_opencv"
    if "clip" in raw:
        return "clip"
    if "opencv" in raw:
        return "opencv"
    if raw == "visual":
        return "clip_opencv"
    return raw.split("+")[0] if raw else "unknown"


def _is_non_machine(pipeline: dict, intent: dict) -> bool:
    if not pipeline.get("success"):
        reason = (pipeline.get("fallback_reason") or "").lower()
        if reason in ("no_classifier_match",):
            return True
    match_type = (intent.get("match_type") or "").lower()
    if match_type == "unknown":
        return True
    if match_type == "broad" and not intent.get("machine_type"):
        return True
    msg = (intent.get("message") or "").lower()
    if "screenshot" in msg or "not a machine" in msg:
        return True
    return False


def _is_low_confidence(intent: dict, confidence: float) -> bool:
    threshold = settings.IMAGE_SEARCH_CONFIDENCE_THRESHOLD
    if confidence < threshold:
        return True
    machine_type = intent.get("machine_type") or intent.get("search_query")
    if not machine_type or str(machine_type).lower() in ("unknown", "other", "misc"):
        return True
    if intent.get("match_type") in ("unknown", "broad") and not intent.get("confident"):
        return True
    return False


def _detect_text_intent(user_text: str) -> str | None:
    text = (user_text or "").strip()
    if not text:
        return None
    if _RE_IDENTIFY.search(text):
        return "identify_only"
    if _RE_EXACT.search(text):
        return "exact_match"
    if _RE_SIMILAR.search(text):
        return "similar_category"
    if _RE_AVAILABILITY.search(text):
        return "availability_search"
    # Bare city or budget follow-ups without explicit intent → availability/search continuation
    parsed = parse_query(text)
    if parsed.get("city") or parsed.get("max_price") or parsed.get("listing_type"):
        return "availability_search"
    return None


def detect_image_text_intent(user_text: str) -> str | None:
    """Public wrapper for text-only image follow-up intent (chat path)."""
    return _detect_text_intent(user_text)


def build_image_followup_reply(
    session_id: str,
    user_text: str,
    *,
    lang: str = "en",
) -> dict | None:
    """
    When user continues an image flow via /chat (not /image-search), handle
    exact-match honesty and identify-only without searching.
    """
    from app.chatbot.image_context_memory import get_image_context

    ctx = get_image_context(session_id)
    if not ctx:
        return None

    intent = _detect_text_intent(user_text)
    category = ctx.get("detected_category") or ctx.get("detected_machine_type")
    if not category:
        return None

    if intent == "exact_match":
        return {
            "message": _exact_match_message(category, lang),
            "assistant_mode": "image_clarification",
            "suggestions": _clarification_chips(lang),
            "should_search": False,
        }
    if intent == "identify_only":
        conf = float(ctx.get("confidence") or 0)
        display = category_label(category)
        conf_word = "high" if conf >= 0.55 else "medium"
        msg = (
            f"Is image me machine {display} jaisi lag rahi hai. Confidence {conf_word} hai."
            if lang == "hi"
            else f"This image looks like a {display} (confidence: {conf_word})."
        )
        return {
            "message": msg,
            "assistant_mode": "image_clarification",
            "suggestions": _clarification_chips(lang),
            "should_search": False,
        }
    return None
    text = (user_text or "").strip()
    if not text:
        return None
    if _RE_IDENTIFY.search(text):
        return "identify_only"
    if _RE_EXACT.search(text):
        return "exact_match"
    if _RE_SIMILAR.search(text):
        return "similar_category"
    if _RE_AVAILABILITY.search(text):
        return "availability_search"
    # Bare city or budget follow-ups without explicit intent → availability/search continuation
    parsed = parse_query(text)
    if parsed.get("city") or parsed.get("max_price") or parsed.get("listing_type"):
        return "availability_search"
    return None


def _clarification_question(category: str, lang_hint: str = "en") -> str:
    display = category_label(category)
    if lang_hint == "hi":
        return (
            f"Ye {display} jaisi machine lag rahi hai. "
            f"Aapko exact same machine/listing chahiye ya similar {display} machines?"
        )
    return (
        f"This looks like a {display}. "
        "Do you want the exact same machine/listing, or similar machines of this type?"
    )


def _clarification_chips(lang_hint: str = "en") -> list[str]:
    if lang_hint == "hi":
        return list(IMAGE_INTENT_CLARIFICATION_CHIPS_HI)
    return list(IMAGE_INTENT_CLARIFICATION_CHIPS)


def _lang_hint(user_text: str) -> str:
    if re.search(r"[\u0900-\u097F]", user_text or ""):
        return "hi"
    lowered = (user_text or "").lower()
    if any(w in lowered for w in ("chahiye", "dikhao", "kya", "hai", "milega", "mujhe")):
        return "hi"
    return "en"


def _build_search_message(
    category: str,
    *,
    image_intent: str,
    user_text: str,
) -> str:
    display = category_label(category)
    parsed = parse_query(user_text or "")
    city = parsed.get("city")
    budget = parsed.get("max_price")
    listing_type = parsed.get("listing_type")

    parts = [category]
    if city:
        parts.append(f"in {city}")
    if budget:
        parts.append(f"under {int(budget)}")
    if listing_type:
        parts.append(listing_type)

    if image_intent == "similar_category":
        if not user_text.strip():
            return f"similar {display} machines"
        if "similar" not in user_text.lower():
            return f"similar {display} {' '.join(parts[1:])}".strip()
    return " ".join(parts)


def _exact_match_message(category: str, lang: str) -> str:
    display = category_label(category)
    if lang == "hi":
        return (
            f"Image se exact same listing confirm karna abhi possible nahi hai. "
            f"Main isi type ki similar {display} machines dikha sakta hoon, "
            "ya agar brand/model pata ho to aur close match dhoondh sakta hoon."
        )
    return (
        f"I cannot confirm the exact same listing from this image alone yet, "
        f"but I can search very similar {display} machines. "
        "If you know the brand or model, tell me for a closer match."
    )


def resolve_image_turn(
    *,
    pipeline: dict[str, Any],
    user_text: str = "",
    session_id: str = "",
    original_filename: str = "",
    upload_id: str | None = None,
) -> ImageTurnResult:
    """
    Map classifier output + optional caption into a canonical ImageTurnResult.
    """
    _ = session_id  # reserved for conversation-state hints in IMG-2
    intent = pipeline.get("intent") or {}
    clf = pipeline.get("classification") or {}
    upload_id = upload_id or str(uuid.uuid4())
    user_text = (user_text or "").strip()
    lang = _lang_hint(user_text)

    category = intent.get("machine_type") or intent.get("search_query")
    if category:
        category = str(category).strip().lower()
    confidence = float(intent.get("intent_confidence") or 0)
    classifier_used = _normalize_classifier(pipeline.get("stage"), intent)
    suggested = list(intent.get("suggested_categories") or [])
    if category and category not in suggested:
        suggested = [category, *suggested]

    visual_features = {
        "category_scores": intent.get("category_scores") or {},
        "predictions": intent.get("predictions") or clf.get("predictions") or [],
        "confident": bool(intent.get("confident")),
        "pipeline_stage": pipeline.get("stage"),
        "fallback_reason": pipeline.get("fallback_reason"),
    }

    meta = {
        "display_label": intent.get("display_label") or (category_label(category) if category else None),
        "category_scores": intent.get("category_scores"),
        "predictions": visual_features["predictions"],
        "yolo_model_loaded": yolo_model_available(),
        "pipeline_success": pipeline.get("success"),
        "fallback_reason": pipeline.get("fallback_reason"),
    }

    base = dict(
        upload_id=upload_id,
        original_filename=original_filename or "upload",
        detected_category=category,
        detected_brand=None,
        detected_model=None,
        suggested_categories=suggested,
        visual_features=visual_features,
        classifier_used=classifier_used,
        confidence=confidence,
    )

    # Non-machine -----------------------------------------------------------
    if _is_non_machine(pipeline, intent) or (
        user_text and _RE_NON_MACHINE_HINT.search(user_text) and confidence < 0.5
    ):
        msg = (
            "Ye construction machine jaisi image nahi lag rahi. "
            "Main InfraForge par construction machines search karne me help kar sakta hoon."
            if lang == "hi"
            else (
                "This does not look like construction equipment. "
                "I can help you search construction machines on InfraForge."
            )
        )
        return ImageTurnResult(
            **base,
            image_intent="non_machine",
            needs_clarification=True,
            clarification_question=msg,
            should_search=False,
            search_mode="none",
            safe_user_message=msg,
            metadata=meta,
        )

    # Low confidence --------------------------------------------------------
    if _is_low_confidence(intent, confidence):
        msg = (
            "Image clear nahi hai, isliye main wrong machine search nahi karunga. "
            "Please clearer photo upload karein ya machine type bata dein."
            if lang == "hi"
            else (
                "This image is not clear enough, so I will not search the wrong machines. "
                "Please upload a clearer photo or tell me the machine type."
            )
        )
        return ImageTurnResult(
            **{**base, "detected_category": None},
            image_intent="low_confidence",
            needs_clarification=True,
            clarification_question=msg,
            should_search=False,
            search_mode="none",
            safe_user_message=msg,
            metadata=meta,
        )

    text_intent = _detect_text_intent(user_text)
    image_intent = text_intent or "unclear"

    # Image only — category confident, intent unclear -----------------------
    if not user_text and category and settings.IMAGE_SEARCH_REQUIRE_CLARIFICATION_FOR_UNCLEAR_INTENT:
        q = _clarification_question(category, lang)
        return ImageTurnResult(
            **base,
            image_intent="unclear",
            needs_clarification=True,
            clarification_question=q,
            should_search=False,
            search_mode="none",
            safe_user_message=q,
            metadata={**meta, "clarification_chips": _clarification_chips(lang)},
        )

    # Exact match requested -------------------------------------------------
    if image_intent == "exact_match":
        msg = _exact_match_message(category or "machine", lang)
        chips = _clarification_chips(lang)
        return ImageTurnResult(
            **base,
            image_intent="exact_match",
            needs_clarification=True,
            clarification_question=msg,
            should_search=False,
            search_mode="exact_requested",
            safe_user_message=msg,
            metadata={**meta, "clarification_chips": chips},
        )

    # Identify only ---------------------------------------------------------
    if image_intent == "identify_only":
        display = category_label(category) if category else "machine"
        conf_word = "high" if confidence >= 0.55 else "medium"
        msg = (
            f"Is image me machine {display} jaisi lag rahi hai. Confidence {conf_word} hai. "
            "Agar chaho to main similar machines search kar sakta hoon."
            if lang == "hi"
            else (
                f"This image looks like a {display} (confidence: {conf_word}). "
                "I have not searched yet — ask me to find similar machines if you want."
            )
        )
        return ImageTurnResult(
            **base,
            image_intent="identify_only",
            needs_clarification=False,
            clarification_question=None,
            should_search=False,
            search_mode="identify_only",
            safe_user_message=msg,
            metadata={**meta, "clarification_chips": _clarification_chips(lang)},
        )

    # Similar / availability / default search -------------------------------
    if image_intent in ("similar_category", "availability_search", "unclear"):
        if image_intent == "unclear" and category:
            # Text present but no clear intent — ask clarification
            q = _clarification_question(category, lang)
            return ImageTurnResult(
                **base,
                image_intent="unclear",
                needs_clarification=True,
                clarification_question=q,
                should_search=False,
                search_mode="none",
                safe_user_message=q,
                metadata={**meta, "clarification_chips": _clarification_chips(lang)},
            )

        search_mode = (
            "similar_category" if image_intent == "similar_category" else "category_search"
        )
        search_msg = _build_search_message(
            category or "",
            image_intent=image_intent,
            user_text=user_text,
        )
        if image_intent == "similar_category":
            lead = (
                f"Theek hai — main similar {category_label(category)} machines dikha raha hoon."
                if lang == "hi"
                else f"Searching similar {category_label(category)} machines."
            )
        else:
            lead = search_msg

        return ImageTurnResult(
            **base,
            image_intent=image_intent,
            needs_clarification=False,
            clarification_question=None,
            should_search=True,
            search_mode=search_mode,
            safe_user_message=search_msg,
            metadata={**meta, "assistant_lead": lead},
        )

    # Fallback — unsupported category boundary ------------------------------
    msg = (
        "Could not map this image to a supported machine category. "
        "Try a clearer photo or search by text."
    )
    return ImageTurnResult(
        **base,
        image_intent="unsupported",
        needs_clarification=True,
        clarification_question=msg,
        should_search=False,
        search_mode="none",
        safe_user_message=msg,
        metadata=meta,
    )
