from __future__ import annotations

from typing import Any, Optional

from groq import Groq

from app.core.config import settings

client = Groq(api_key=settings.GROQ_API_KEY)


def groq_chat_completion(
    *,
    messages: list[dict[str, str]],
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0,
    tag: str = "groq",
) -> Optional[Any]:
    """
    Safe Groq chat call — returns None on failure (rate limit, timeout, etc.).
    Callers must fall back to rules/local logic.
    """
    if not settings.GROQ_API_KEY:
        return None
    try:
        timeout = max(5.0, float(settings.GROQ_TIMEOUT_SECONDS or 20))
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"[{tag}] groq failed: {exc}")
        return None
