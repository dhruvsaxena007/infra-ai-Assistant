"""
Lightweight response memory — avoids repetition and supports natural follow-ups.

Stored inside session_context (and optionally user profile when user_id exists).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

MEMORY_KEY = "response_memory"
USER_MEMORY_KEY = "user_response_memory"

MAX_RECENT = 12


def empty_response_memory() -> dict[str, Any]:
    return {
        "recent_intents": [],
        "recent_response_goals": [],
        "recent_response_signatures": [],
        "recent_messages_summary": [],
        "pending_fields": [],
        "last_machine_search": {},
        "last_support_issue": {},
        "preferred_language": None,
    }


def get_response_memory(session_context: dict[str, Any]) -> dict[str, Any]:
    mem = session_context.get(MEMORY_KEY)
    if not isinstance(mem, dict):
        return empty_response_memory()
    base = empty_response_memory()
    base.update(mem)
    return base


def _summarize_message(message: str, max_len: int = 80) -> str:
    text = re.sub(r"\s+", " ", (message or "").strip())
    return text[:max_len]


def compute_response_signature(message: str, response_goal: str = "") -> str:
    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())[:200]
    raw = f"{response_goal}|{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def record_response_memory(
    session_context: dict[str, Any],
    *,
    intent: str,
    response_goal: str,
    message: str,
    response_signature: str = "",
    pending_fields: Optional[list[str]] = None,
    machine_search: Optional[dict] = None,
    support_issue: Optional[dict] = None,
    language: Optional[str] = None,
) -> dict[str, Any]:
    """Return updated session_context with memory recorded."""
    mem = get_response_memory(session_context)
    sig = response_signature or compute_response_signature(message, response_goal)
    summary = _summarize_message(message)

    for key, val in (
        ("recent_intents", intent),
        ("recent_response_goals", response_goal),
        ("recent_response_signatures", sig),
        ("recent_messages_summary", summary),
    ):
        items = list(mem.get(key) or [])
        items.append(val)
        mem[key] = items[-MAX_RECENT:]

    if pending_fields is not None:
        mem["pending_fields"] = pending_fields
    if machine_search:
        mem["last_machine_search"] = machine_search
    if support_issue:
        mem["last_support_issue"] = support_issue
    if language:
        mem["preferred_language"] = language

    # Legacy variant tracking (backward compat)
    recent_variants = list(session_context.get("recent_variant_ids") or [])
    recent_variants.append(sig)
    turn_count = int(session_context.get("turn_count") or 0) + 1

    return {
        **session_context,
        MEMORY_KEY: mem,
        "recent_variant_ids": recent_variants[-MAX_RECENT:],
        "turn_count": turn_count,
    }


def record_user_preference_memory(
    user_profile: dict[str, Any],
    *,
    user_id: str,
    name: Optional[str] = None,
    language: Optional[str] = None,
    city: Optional[str] = None,
    machine_interest: Optional[str] = None,
    response_signature: str = "",
) -> dict[str, Any]:
    """Lightweight cross-session preference (no secrets/payment data)."""
    profile = dict(user_profile or {})
    mem = dict(profile.get(USER_MEMORY_KEY) or {})
    mem["user_id"] = user_id
    if name:
        mem["name"] = name
    if language:
        mem["preferred_language"] = language
    if city:
        mem["last_known_city"] = city
    if machine_interest:
        interests = list(mem.get("common_machine_interest") or [])
        if machine_interest not in interests:
            interests.append(machine_interest)
        mem["common_machine_interest"] = interests[-8:]
    if response_signature:
        sigs = list(mem.get("recent_response_signatures") or [])
        sigs.append(response_signature)
        mem["recent_response_signatures"] = sigs[-MAX_RECENT:]
    profile[USER_MEMORY_KEY] = mem
    return profile
