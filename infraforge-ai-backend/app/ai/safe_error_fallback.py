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


def _is_database_failure(exc: Exception | None) -> bool:
    if not exc:
        return False
    err = str(exc).lower()
    needles = (
        "nonetype", "equipmentcategories", "mongodb", "connection",
        "server selection", "timeout", "econnrefused", "network",
    )
    return any(n in err for n in needles)


def infer_recoverable_stage(
    user_message: str,
    exc: Exception | None = None,
) -> tuple[str, str]:
    """Map failed turn to a recoverable pipeline stage + intent."""
    text = (user_message or "").strip()

    try:
        from app.ai.suggestion_action_resolver import is_suggestion_chip, resolve_suggestion_chip

        if is_suggestion_chip(text):
            hint = (resolve_suggestion_chip(text) or {}).get("intent_hint")
            if hint == "support":
                return "support", "support_request"
            if hint == "machine_search":
                return "machine_search", "machine_search"
            if hint == "recommendation":
                return "recommendation", "machine_recommendation"
            if hint == "comparison":
                return "comparison", "comparison_request"
    except Exception:
        pass

    try:
        from app.ai.capability_registry import (
            has_marketplace_action_signal,
            has_support_action_signal,
        )
        from app.ai.query_parser import parse_query

        if has_support_action_signal(text):
            return "support", "support_request"
        parsed = parse_query(text)
        if has_marketplace_action_signal(text) or parsed.get("category") or parsed.get("city"):
            return "machine_search", "machine_search"
    except Exception:
        pass

    try:
        from app.ai.semantic_turn_gateway import _SUPPORT_RE, _RECOMMENDATION_RE

        if _SUPPORT_RE.search(text):
            return "support", "support_request"
        if _RECOMMENDATION_RE.search(text):
            return "recommendation", "machine_recommendation"
    except Exception:
        pass

    if _is_database_failure(exc):
        return "machine_search", "machine_search"

    return "unknown", "unknown"


def build_recoverable_exception_response(
    *,
    user_message: str,
    exc: Exception | None = None,
    lang: str = "english",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Success envelope with useful reply when the pipeline threw."""
    rid = request_id or _request_id()
    stage, intent = infer_recoverable_stage(user_message, exc)
    log_safe_error(
        request_id=rid,
        stage=stage,
        intent=intent,
        exc=exc,
        message=user_message,
    )

    if stage == "support":
        from app.ai.support_response_service import build_response

        resp = build_response("support_request", lang=lang, message=user_message)
        return success_response(
            message=resp["message"],
            data={
                "machines": [],
                "assistant_mode": resp.get("assistant_mode", "support"),
                "suggestions": resp.get("suggestions") or ["Contact support", "Raise Request"],
                "handover": resp.get("handover"),
                "context": {
                    "intent": "support_request",
                    "response_mode": "safe_recoverable_fallback",
                    "request_id": rid,
                    "stage": stage,
                    "recoverable": True,
                },
            },
        )

    return build_safe_fallback_success(
        stage=stage,
        intent=intent,
        assistant_mode=(
            "machine_search" if stage == "machine_search" else "clarification"
        ),
        user_message=user_message,
        lang=lang,
        request_id=rid,
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
    """Structured API response — recoverable intents return success, not red errors."""
    rid = request_id or _request_id()
    inferred_stage, inferred_intent = infer_recoverable_stage(user_message, exc)
    use_stage = stage if stage and stage != "assistant_router" else inferred_stage
    use_intent = intent or inferred_intent

    if use_stage in ("support", "machine_search", "recommendation", "comparison"):
        return build_recoverable_exception_response(
            user_message=user_message,
            exc=exc,
            lang=lang,
            request_id=rid,
        )

    log_safe_error(
        request_id=rid,
        stage=use_stage,
        intent=use_intent,
        exc=exc,
        message=user_message,
    )
    msg = fallback_message_for_stage(use_stage, lang=lang, user_message=user_message)
    return error_response(
        message=msg,
        error={
            "request_id": rid,
            "stage": use_stage,
            "intent": use_intent,
            "recoverable": True,
        },
    )
