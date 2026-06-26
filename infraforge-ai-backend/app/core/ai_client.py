"""
Unified AI client — routes chat, speech-to-text, and vision to OpenAI or Groq.

When AI_PROVIDER=openai and ENABLE_OPENAI=true, paid OpenAI APIs are used.
Otherwise Groq/local paths remain the default.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import settings

_openai_client: Any = None
_groq_client: Any = None


def using_openai() -> bool:
    return bool(settings.openai_usable)


def _openai_model(override: Optional[str] = None) -> str:
    return (override or settings.OPENAI_CHAT_MODEL or "gpt-4o-mini").strip()


def _get_openai_client() -> Any:
    global _openai_client
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing")
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _get_groq_client() -> Any:
    global _groq_client
    if _groq_client is None:
        from groq import Groq

        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


def ai_chat_completion(
    *,
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0,
    tag: str = "ai_chat",
    max_tokens: Optional[int] = None,
) -> Optional[Any]:
    """Chat completion — OpenAI when enabled, else Groq. Returns None on failure."""
    if using_openai():
        try:
            kwargs: dict[str, Any] = {
                "model": _openai_model(model if model and not model.startswith("llama") else None),
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return _get_openai_client().chat.completions.create(**kwargs)
        except Exception as exc:
            print(f"[{tag}] openai failed: {exc}")
            return None

    if not settings.GROQ_API_KEY:
        return None
    try:
        timeout = max(5.0, float(settings.GROQ_TIMEOUT_SECONDS or 20))
        groq_model = model or "llama-3.3-70b-versatile"
        if groq_model.startswith("gpt-"):
            groq_model = "llama-3.3-70b-versatile"
        return _get_groq_client().chat.completions.create(
            model=groq_model,
            messages=messages,
            temperature=temperature,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"[{tag}] groq failed: {exc}")
        return None


def ai_transcribe_audio(
    audio_file_path: str,
    *,
    language_hint: Optional[str] = None,
    prompt: str = "",
) -> dict[str, Any]:
    """Speech-to-text — OpenAI whisper-1 or Groq whisper-large-v3."""
    if using_openai():
        try:
            kwargs: dict[str, Any] = {
                "model": settings.OPENAI_WHISPER_MODEL or "whisper-1",
                "temperature": 0,
            }
            if language_hint:
                kwargs["language"] = language_hint
            if prompt:
                kwargs["prompt"] = prompt
            with open(audio_file_path, "rb") as audio_file:
                transcription = _get_openai_client().audio.transcriptions.create(
                    file=audio_file,
                    **kwargs,
                )
            text = (transcription.text or "").strip()
            return {
                "success": True,
                "original_text": text,
                "text": text,
                "provider": "openai",
            }
        except Exception as exc:
            print(f"[ai_transcribe] openai failed: {exc}")
            return {"success": False, "error": "stt_provider_error", "provider": "openai"}

    if not settings.GROQ_API_KEY:
        return {"success": False, "error": "stt_no_provider", "provider": "none"}

    try:
        kwargs = {
            "model": "whisper-large-v3",
            "temperature": 0,
        }
        if language_hint:
            kwargs["language"] = language_hint
        if prompt:
            kwargs["prompt"] = prompt
        with open(audio_file_path, "rb") as audio_file:
            transcription = _get_groq_client().audio.transcriptions.create(
                file=audio_file,
                **kwargs,
            )
        text = (transcription.text or "").strip()
        return {
            "success": True,
            "original_text": text,
            "text": text,
            "provider": "groq",
        }
    except Exception as exc:
        print(f"[ai_transcribe] groq failed: {exc}")
        return {"success": False, "error": "stt_provider_error", "provider": "groq"}


def ai_vision_classify_machine(image_path: str) -> Optional[dict[str, Any]]:
    """
    Optional OpenAI vision assist for image search final testing.
    Returns classifier-shaped dict or None on failure/disabled.
    """
    if not using_openai() or not settings.USE_OPENAI_VISION:
        return None

    import base64
    import json
    from pathlib import Path

    path = Path(image_path)
    if not path.is_file():
        return None

    suffix = path.suffix.lower().lstrip(".") or "jpeg"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    if mime not in ("jpeg", "jpg", "png", "webp", "gif"):
        mime = "jpeg"

    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        prompt = (
            "You classify construction/heavy equipment photos for an Indian marketplace. "
            "Return ONLY JSON: "
            '{"category":"excavator|backhoe loader|crane|road roller|wheel loader|dump truck|bulldozer|motor grader|unknown",'
            '"brand":"visible brand if readable else empty",'
            '"model":"visible model if readable else empty",'
            '"confidence":0.0,"display_label":"short label","message":"one line for user"}'
        )
        response = _get_openai_client().chat.completions.create(
            model=settings.OPENAI_VISION_MODEL or "gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            temperature=0,
            max_tokens=300,
        )
        raw = (response.choices[0].message.content or "").strip()
        from app.ai.text_understanding_service import extract_json_from_text

        data = extract_json_from_text(raw)
        category = str(data.get("category") or "unknown").strip().lower()
        brand = str(data.get("brand") or "").strip()
        model = str(data.get("model") or "").strip()
        conf = float(data.get("confidence") or 0.5)
        display = str(data.get("display_label") or category).strip()
        if brand and brand.lower() not in display.lower():
            display = f"{brand} {display}".strip()
        return {
            "match_type": "exact" if category != "unknown" else "unknown",
            "machine_type": category if category != "unknown" else None,
            "detected_brand": brand or None,
            "detected_model": model or None,
            "search_query": category if category != "unknown" else "",
            "suggested_categories": [category] if category != "unknown" else [],
            "intent_confidence": round(conf, 4),
            "confident": conf >= 0.55,
            "message": str(data.get("message") or f"Detected: {display}"),
            "classifier": "openai_vision",
            "predictions": [{"label": category, "confidence": conf}],
            "display_label": display,
        }
    except Exception as exc:
        print(f"[ai_vision] openai failed: {exc}")
        return None
