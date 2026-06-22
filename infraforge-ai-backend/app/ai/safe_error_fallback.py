"""
Safe Error Fallback — graceful user-facing errors with structured logging.

Replaces generic "Something went wrong" for understandable input.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.utils.response import error_response, success_response


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def log_safe_error(
    *,
    request_id: str,
    stage: str,
    intent: str | None = None,
    exc: Exception | None = None,
    message: str = "",
) -> None:
    detail = str(exc) if exc else ""
    print(
        f"[safe_error] request_id={request_id}",
        f"stage={stage}",
        f"intent={intent or 'unknown'}",
        f"msg={message[:80]!r}",
        f"error={detail[:200]}",
    )


def fallback_message_for_stage(
    stage: str,
    *,
    lang: str = "english",
    user_message: str = "",
) -> str:
    """User-friendly fallback by pipeline stage — never expose raw errors."""
    if stage == "semantic_gateway":
        return (
            "I understood your question but had trouble processing it fully. "
            "Could you rephrase or try a shorter message?"
        )
    if stage == "machine_search":
        if lang == "hindi":
            return "Machine search abhi complete nahi ho paya. City ya machine type phir se batayein."
        if lang == "hinglish":
            return "Search abhi complete nahi hua. City ya machine type dubara batayein."
        return "I couldn't complete the machine search right now. Please try again with city and machine type."

    if stage == "support":
        return (
            "I can help with support — please share your booking ID or describe the issue, "
            "and I'll guide you through the next steps."
        )

    if stage == "comparison":
        return (
            "I can compare equipment brands for you. Which two brands or machine types "
            "would you like to compare?"
        )

    if stage == "recommendation":
        return (
            "Tell me what work you need the machine for and which city — "
            "I'll recommend the best options."
        )

    if stage == "memory_answer":
        return (
            "I don't have your name saved yet. You can tell me by saying "
            "'my name is ...' and I'll remember it for this session."
        )

    if lang == "hindi":
        return "Kuch technical issue aaya. Thodi der baad dubara try karein ya apna sawal alag tarike se likhein."
    if lang == "hinglish":
        return "Thoda technical issue aa gaya. Dubara try karo ya sawal thoda clearly likho."
    return (
        "Something didn't work as expected. Please try again — "
        "or rephrase your question about machines, rentals, or support."
    )


def build_safe_error_response(
    *,
    stage: str,
    exc: Exception | None = None,
    intent: str | None = None,
    user_message: str = "",
    lang: str = "english",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Structured error response for API — no raw exception in user message."""
    rid = request_id or _request_id()
    log_safe_error(
        request_id=rid,
        stage=stage,
        intent=intent,
        exc=exc,
        message=user_message,
    )
    msg = fallback_message_for_stage(stage, lang=lang, user_message=user_message)
    return error_response(
        message=msg,
        error={
            "request_id": rid,
            "stage": stage,
            "intent": intent,
            "recoverable": True,
        },
    )


def build_safe_fallback_success(
    *,
    stage: str,
    intent: str,
    assistant_mode: str,
    user_message: str = "",
    lang: str = "english",
    suggestions: list[str] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Graceful in-band fallback as success envelope (not HTTP error)."""
    rid = request_id or _request_id()
    msg = fallback_message_for_stage(stage, lang=lang, user_message=user_message)
    return success_response(
        message=msg,
        data={
            "advisor_message": msg,
            "machines": [],
            "assistant_mode": assistant_mode,
            "context": {
                "intent": intent,
                "response_mode": "safe_error_fallback",
                "request_id": rid,
                "stage": stage,
            },
            "suggestions": suggestions or ["Search Machine", "Contact support", "Ask recommendation"],
        },
    )
