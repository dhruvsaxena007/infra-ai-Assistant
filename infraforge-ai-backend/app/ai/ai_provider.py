"""
Unified AI provider facade — Groq/local by default, OpenAI optional.

All assistant features should route LLM/vision/transcription calls through this
module so OpenAI credits are never spent unless explicitly enabled in .env:

    AI_PROVIDER=groq
    ENABLE_OPENAI=false
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import settings

OPENAI_DISABLED_MSG = "OpenAI provider disabled"


def is_openai_enabled() -> bool:
    return settings.openai_usable


def is_groq_default() -> bool:
    return settings.AI_PROVIDER in ("groq", "local", "") or not settings.openai_usable


def _openai_blocked() -> dict[str, Any]:
    return {"success": False, "error": OPENAI_DISABLED_MSG, "provider": "openai"}


async def classify_with_ai(
    message: str,
    *,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Intent / text understanding via rules-first router; Groq only when flagged.
    OpenAI path reserved for later polish when ENABLE_OPENAI=true.
    """
    from app.ai.assistant_intent_router import classify_assistant_intent

    if settings.openai_usable and settings.USE_OPENAI_INTENT_PARSER:
        try:
            from app.ai.openai_parser import extract_intent

            parsed = await extract_intent(message)
            if parsed and any(parsed.get(k) for k in ("category", "city", "brand", "model")):
                return {
                    "success": True,
                    "provider": "openai",
                    "data": parsed,
                }
        except ValueError as exc:
            if OPENAI_DISABLED_MSG in str(exc):
                pass
            else:
                raise

    if settings.llm_intent_first:
        from app.ai.llm_intent_classifier import classify_intent_llm

        result = await classify_intent_llm(message, context=context)
        return {
            "success": True,
            "provider": result.get("layer") or "llm",
            "data": result,
        }

    result = await classify_assistant_intent(message, context)
    return {
        "success": True,
        "provider": result.get("layer") or "rules",
        "data": result,
    }


def generate_assistant_response(
    *,
    mode: str,
    question: str = "",
    context: str = "",
    machines: Optional[list] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate advisor or RAG prose. Defaults to deterministic/local paths."""
    mode = (mode or "").lower()

    if mode == "advisor":
        from app.ai.advisor_service import generate_machine_advice

        text = generate_machine_advice(
            kwargs.get("user_query") or question,
            machines or [],
        )
        provider = "groq" if settings.USE_GROQ_ADVISOR else "rules"
        return {"success": True, "provider": provider, "text": text}

    if mode == "rag":
        from app.ai.rag_service import generate_answer_from_context

        answer, provider = generate_answer_from_context(
            question,
            context,
            top_score=float(kwargs.get("top_score") or 0),
        )
        return {"success": True, "provider": provider, "text": answer}

    if settings.openai_usable:
        return _openai_blocked()

    return {
        "success": False,
        "error": "Unsupported assistant response mode",
        "provider": settings.AI_PROVIDER,
    }


def transcribe_audio(file_path: str) -> dict[str, Any]:
    """Speech-to-text — OpenAI Whisper or Groq Whisper based on AI_PROVIDER."""
    from app.core.ai_client import ai_transcribe_audio

    return ai_transcribe_audio(file_path)


def analyze_image(image_path: str) -> dict[str, Any]:
    """Image classification — OpenAI vision (optional) + local YOLO/CLIP fallback."""
    from app.core.ai_client import ai_vision_classify_machine
    from app.ai.image_classifier import classify_marketplace_image

    if settings.openai_usable and settings.USE_OPENAI_VISION:
        vision = ai_vision_classify_machine(image_path)
        if vision and vision.get("machine_type"):
            return {"success": True, "provider": "openai_vision", **vision}

    result = classify_marketplace_image(image_path)
    return {"success": True, "provider": "local", **result}
