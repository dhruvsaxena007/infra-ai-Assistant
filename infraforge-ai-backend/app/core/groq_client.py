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
    Safe chat call — OpenAI when AI_PROVIDER=openai, else Groq.
    Returns None on failure (rate limit, timeout, etc.).
    """
    from app.core.ai_client import ai_chat_completion

    return ai_chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        tag=tag,
    )
