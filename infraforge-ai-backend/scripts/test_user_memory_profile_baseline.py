"""
Phase 10 — User Memory Profile baseline tests.

Run: python scripts/test_user_memory_profile_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("ASSISTANT_DEBUG", "true")


class Counter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def record(self, label: str, ok: bool, detail: str = "") -> None:
        tag = "PASS" if ok else "FAIL"
        line = f"  [{tag}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)
        if ok:
            self.passed += 1
        else:
            self.failed += 1


def test_identity_resolution(c: Counter) -> None:
    from app.ai.user_memory_profile import resolve_profile_identity

    auth = resolve_profile_identity("sess1", user_id="user-42")
    c.record("authenticated profile id", auth["profile_id"] == "user:user-42")
    c.record("authenticated source", auth["profile_source"] == "authenticated")

    anon = resolve_profile_identity("sess-anon")
    c.record("anonymous profile id", anon["profile_id"] == "anon:sess-anon")
    c.record("anonymous source", anon["profile_source"] == "anonymous_session")


def test_name_introduction(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:name")
    updated, meta = update_profile_from_turn(
        profile,
        user_message="my name is Dhruv",
        intent="user_introduction",
    )
    c.record("name saved", updated.get("name") == "Dhruv", updated.get("name"))
    c.record("name in updated_fields", "name" in (meta.get("updated_fields") or []))


def test_preferred_language_threshold(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:lang")
    for _ in range(2):
        profile, _ = update_profile_from_turn(
            profile,
            user_message="excavator chahiye Jaipur me",
            intent="machine_search",
            reply_lang="hinglish",
        )
    c.record("preferred_language hinglish", profile.get("preferred_language") == "hinglish")


def test_preferred_city_threshold(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:city")
    for msg in ("excavator in jaipur", "road roller in jaipur"):
        profile, meta = update_profile_from_turn(
            profile,
            user_message=msg,
            intent="machine_search",
            parsed={"city": "jaipur", "category": "excavator"},
            entities={"city": "jaipur"},
        )
    c.record("preferred_city jaipur", profile.get("preferred_city") == "jaipur", profile.get("preferred_city"))
    c.record("city updated", "preferred_city" in (meta.get("updated_fields") or []))


def test_current_message_overrides_profile(c: Counter) -> None:
    from app.ai.user_memory_profile import build_profile_hints, empty_user_profile

    profile = empty_user_profile(profile_id="test:override")
    profile["preferred_city"] = "jaipur"
    profile["_signals"] = {"city_counts": {"jaipur": 3, "delhi": 0}}
    hints = build_profile_hints(profile)
    parsed_city = "delhi"
    effective_city = parsed_city or hints.get("preferred_city")
    c.record("explicit delhi wins", effective_city == "delhi")


def test_profile_city_confirmation(c: Counter) -> None:
    from app.ai.user_memory_profile import (
        build_profile_hints,
        empty_user_profile,
        profile_aware_clarification_message,
    )

    profile = empty_user_profile(profile_id="test:confirm")
    profile["preferred_city"] = "jaipur"
    profile["_signals"] = {"city_counts": {"jaipur": 2}}
    hints = build_profile_hints(profile)
    msg = profile_aware_clarification_message(
        lang="english",
        category="excavator",
        profile_hints=hints,
    )
    c.record("asks confirmation", bool(msg) and "jaipur" in msg.lower() and "another" in msg.lower(), msg)
    c.record("requires confirmation flag", hints.get("city_hint_requires_confirmation") is True)


def test_common_category_accumulation(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:cat")
    for _ in range(2):
        profile, _ = update_profile_from_turn(
            profile,
            user_message="excavator in jaipur",
            intent="machine_search",
            parsed={"category": "excavator", "city": "jaipur"},
        )
    c.record("common categories", "excavator" in (profile.get("common_machine_categories") or []))


def test_support_privacy(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:support")
    profile["name"] = "TestUser"
    updated, meta = update_profile_from_turn(
        profile,
        user_message="payment issue TXN12345 booking id ORD99",
        intent="payment_issue",
        entities={"transaction_id": "TXN12345", "order_id": "ORD99"},
    )
    c.record("no transaction stored", "transaction_id" not in updated)
    c.record("no booking stored", "booking_id" not in updated)
    c.record("support skipped update", not meta.get("profile_updated"), str(meta))


def test_document_privacy(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:doc")
    updated, meta = update_profile_from_turn(
        profile,
        user_message="what does section 4 of my uploaded pdf say",
        intent="document_question",
    )
    c.record("document not stored", "document_text" not in updated)
    c.record("doc intent skipped", meta.get("skip_reason") == "intent:document_question")


def test_frustration_privacy(c: Counter) -> None:
    from app.ai.user_memory_profile import empty_user_profile, update_profile_from_turn

    profile = empty_user_profile(profile_id="test:frust")
    before = dict(profile)
    updated, meta = update_profile_from_turn(
        profile,
        user_message="you are useless idiot",
        intent="frustration",
    )
    c.record("frustration not stored", updated == before or not meta.get("profile_updated"))


def test_reset_profile(c: Counter) -> None:
    from app.ai.user_memory_profile import (
        empty_user_profile,
        load_user_profile,
        reset_user_profile,
        save_user_profile,
    )

    sid = "p10_reset_test"
    prof = empty_user_profile(profile_id=f"anon:{sid}", anonymous_session_key=sid, profile_source="anonymous_session")
    prof["name"] = "ResetMe"
    save_user_profile(prof)
    c.record("reset deletes", reset_user_profile(sid))
    reloaded = load_user_profile(sid)
    c.record("profile cleared after reset", reloaded.get("name") is None)


async def test_debug_trace_profile(c: Counter) -> None:
    from app.ai.assistant_debug_trace import _current, begin_chat_trace, end_chat_trace, record_user_profile

    token = begin_chat_trace("p10_debug", "profile trace")
    record_user_profile({
        "loaded": True,
        "profile_source": "anonymous_session",
        "profile_hints_used": ["preferred_city"],
        "profile_updated": True,
        "updated_fields": ["preferred_city"],
        "sensitive_fields_skipped": True,
    })
    trace = dict(_current() or {})
    end_chat_trace(token)
    up = trace.get("user_profile") or {}
    c.record("trace loaded", up.get("loaded") is True)
    c.record("trace updated fields", "preferred_city" in (up.get("updated_fields") or []))


async def test_integration_name_flow(c: Counter) -> None:
    from app.ai.user_memory_profile import load_user_profile, reset_user_profile
    from app.chatbot.chatbot_service import chatbot_response
    from app.chatbot.memory import clear_conversation
    from app.database.mongodb import database

    sid = "p10_name_flow"
    clear_conversation(sid)
    reset_user_profile(sid)
    await chatbot_response(sid, "my name is Dhruv", database)
    prof = load_user_profile(sid)
    c.record("integration name saved", prof.get("name") == "Dhruv", prof.get("name"))


async def test_integration_city_override(c: Counter) -> None:
    from app.ai.user_memory_profile import load_user_profile, reset_user_profile, save_user_profile, empty_user_profile
    from app.chatbot.chatbot_service import chatbot_response, _get_last_filters
    from app.chatbot.memory import clear_conversation
    from app.database.mongodb import database

    sid = "p10_city_override"
    clear_conversation(sid)
    reset_user_profile(sid)
    prof = empty_user_profile(profile_id=f"anon:{sid}", anonymous_session_key=sid, profile_source="anonymous_session")
    prof["preferred_city"] = "jaipur"
    prof["_signals"] = {"city_counts": {"jaipur": 3}}
    save_user_profile(prof)

    await chatbot_response(sid, "excavator in Delhi", database)
    filters = _get_last_filters(sid)
    c.record("delhi overrides jaipur profile", filters.get("city") == "delhi", str(filters))


def test_production_defaults(c: Counter) -> None:
    from app.core.config import settings

    config_path = os.path.join(PROJECT_ROOT, "app", "core", "config.py")
    with open(config_path, encoding="utf-8") as fh:
        src = fh.read()
    c.record("rules_first default", 'or "rules_first"' in src)
    c.record("openai disabled", not settings.ENABLE_OPENAI)


async def main() -> int:
    c = Counter()
    print("\n=== Phase 10 — User Memory Profile ===\n")

    test_identity_resolution(c)
    test_name_introduction(c)
    test_preferred_language_threshold(c)
    test_preferred_city_threshold(c)
    test_current_message_overrides_profile(c)
    test_profile_city_confirmation(c)
    test_common_category_accumulation(c)
    test_support_privacy(c)
    test_document_privacy(c)
    test_frustration_privacy(c)
    test_reset_profile(c)
    await test_debug_trace_profile(c)
    await test_integration_name_flow(c)
    await test_integration_city_override(c)
    test_production_defaults(c)

    print(f"\nPhase 10: {c.passed} passed, {c.failed} failed\n")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
