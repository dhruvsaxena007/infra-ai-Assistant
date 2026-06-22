"""
Phase 7 — LLM-first intent understanding baseline tests.

Run: python scripts/test_llm_intent_baseline.py
With debug: ASSISTANT_DEBUG=true AI_INTENT_MODE=llm_first python scripts/test_llm_intent_baseline.py
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
os.environ.setdefault("ENABLE_OPENAI", "false")
os.environ.setdefault("AI_PROVIDER", "groq")

from app.ai.intent_classifier import classify_intent  # noqa: E402
from app.ai.llm_intent_classifier import classify_intent_llm, _call_llm_classifier_raw  # noqa: E402
from app.ai.intent_entity_validator import validate_llm_classification  # noqa: E402
from app.ai.intent_schema import empty_rich_payload, to_legacy_classification  # noqa: E402
from app.ai.safe_action_router import resolve_action_decision, action_decision_to_router_action  # noqa: E402
from app.ai.intent_action_router import ACTION_MACHINE_SEARCH, ACTION_CLARIFY, ACTION_SUPPORT  # noqa: E402
from app.core.config import settings  # noqa: E402


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


def _valid_llm_payload(**overrides) -> dict:
    base = empty_rich_payload(layer="llm")
    base.update({
        "intent": "machine_search",
        "confidence": 0.91,
        "language": "english",
        "user_sentiment": "neutral",
        "assistant_mode": "machine_search",
        "response_goal": "show_machine_results",
        "requires_clarification": False,
        "should_search_machines": True,
        "entities": {
            "user": {"name": None},
            "machine": {"category": "excavator", "brand": None, "brands": [], "model": None, "purpose": None, "listing_type": None, "rent_type": None, "condition": None},
            "location": {"city": "jaipur", "state": None, "nearby_allowed": False},
            "commercial": {"budget": None, "budget_type": None, "currency": "INR", "price_max": None, "price_min": None},
            "support": {"issue_category": None, "issue_subcategory": None, "order_id": None, "booking_id": None, "transaction_id": None, "payment_method": None, "amount": None},
            "document": {"document_reference": False, "document_type": None, "question_about_document": False},
            "image": {"image_reference": False, "detected_machine_hint": None},
        },
        "missing_fields": [],
        "search_filters": {"category": "excavator", "city": "jaipur"},
    })
    base.update(overrides)
    return base


async def test_valid_llm_primary(c: Counter) -> None:
    payload = _valid_llm_payload()
    validated = validate_llm_classification(payload, "need digger in Jaipur site")
    legacy = to_legacy_classification({**validated, "layer": "llm", "intent_source": "llm"})
    with mock.patch("app.ai.llm_intent_classifier._cache_get", return_value=None):
        with mock.patch("app.ai.llm_intent_classifier._deterministic_fast_path", return_value=None):
            with mock.patch(
                "app.ai.llm_intent_classifier._call_llm_classifier_raw",
                new=mock.AsyncMock(return_value=(legacy, None)),
            ):
                result = await classify_intent_llm("need digger in Jaipur site", context={})
    c.record(
        "valid LLM JSON used as primary",
        result.get("intent_source") == "llm" or result.get("layer") == "llm",
        f"intent={result.get('intent')} layer={result.get('layer')} source={result.get('intent_source')}",
    )
    c.record("search allowed with category+city", bool(result.get("should_search_machines")))


async def test_invalid_json_rules_fallback(c: Counter) -> None:
    with mock.patch("app.ai.llm_intent_classifier._cache_get", return_value=None):
        with mock.patch("app.ai.llm_intent_classifier._deterministic_fast_path", return_value=None):
            with mock.patch(
                "app.ai.llm_intent_classifier._call_llm_classifier_raw",
                new=mock.AsyncMock(return_value=(None, "invalid_json_or_provider_error")),
            ):
                result = await classify_intent_llm("payment failed", context={})
    c.record(
        "invalid JSON falls back to rules",
        result.get("layer") == "rules_fallback" or result.get("intent_source") == "rules_fallback",
        f"layer={result.get('layer')} intent={result.get('intent')}",
    )


async def test_low_confidence_fallback(c: Counter) -> None:
    with mock.patch("app.ai.llm_intent_classifier._cache_get", return_value=None):
        with mock.patch("app.ai.llm_intent_classifier._deterministic_fast_path", return_value=None):
            with mock.patch(
                "app.ai.llm_intent_classifier._call_llm_classifier_raw",
                new=mock.AsyncMock(return_value=(None, "low_confidence")),
            ):
                result = await classify_intent_llm("maybe something", context={})
    c.record("low confidence uses rules fallback", result.get("intent_source") == "rules_fallback")


async def test_forbidden_tool_blocked(c: Counter) -> None:
    payload = _valid_llm_payload(intent="payment_issue", should_search_machines=True, confidence=0.9)
    payload["entities"]["machine"]["category"] = None
    payload["entities"]["location"]["city"] = None
    validated = validate_llm_classification(payload, "payment failed")
    legacy = to_legacy_classification(validated)
    decision = resolve_action_decision(legacy, {}, message="payment failed")
    action = action_decision_to_router_action(decision, legacy)
    c.record("payment blocks machine search", not decision.get("should_search_machines"))
    c.record("payment routes support/clarify", action.get("action") in (ACTION_SUPPORT, ACTION_CLARIFY))


async def test_brand_query_routing(c: Counter) -> None:
    payload = _valid_llm_payload(
        intent="machine_brand_query",
        should_search_machines=False,
        confidence=0.88,
        assistant_mode="clarification",
    )
    payload["entities"]["machine"]["category"] = "road roller"
    validated = validate_llm_classification(payload, "which brands of road roller")
    legacy = to_legacy_classification(validated)
    decision = resolve_action_decision(legacy, {"last_filters": {}}, message="which brands of road roller")
    c.record("brand query permission passed", decision.get("permission_passed") is not False)
    c.record(
        "brand inventory action selected",
        "brand" in str(decision.get("selected_action") or "") or decision.get("allowed_tool") == "mongodb_brand_inventory",
        str(decision.get("selected_action")),
    )


async def test_frustration_no_search(c: Counter) -> None:
    payload = _valid_llm_payload(intent="frustration", user_sentiment="frustrated", should_search_machines=True)
    validated = validate_llm_classification(payload, "this is useless")
    legacy = to_legacy_classification(validated)
    decision = resolve_action_decision(legacy, {}, message="this is useless")
    action = action_decision_to_router_action(decision, legacy)
    c.record("frustration blocks search", not decision.get("should_search_machines"))
    c.record("frustration recovery action", decision.get("selected_action") == "recovery_response" or action.get("response_goal") == "frustration_recovery")


async def test_shadow_mode_uses_rules(c: Counter) -> None:
    from app.ai.llm_intent_classifier import classify_intent_llm_shadow_compare

    legacy = to_legacy_classification(_valid_llm_payload())
    with mock.patch(
        "app.ai.llm_intent_classifier._call_llm_classifier_raw",
        new=mock.AsyncMock(return_value=(legacy, None)),
    ):
        orig_mode = settings.AI_INTENT_MODE
        try:
            settings.AI_INTENT_MODE = "llm_shadow"
            rules, llm = await classify_intent_llm_shadow_compare("hello", context={})
            routed = await classify_intent("hello", context={})
        finally:
            settings.AI_INTENT_MODE = orig_mode
    c.record("shadow routes with rules", routed.get("intent_source") == "rules_shadow")
    c.record("shadow still captures LLM side", bool(llm.get("intent") or llm.get("llm_intent")))


async def test_config_defaults(c: Counter) -> None:
    default_mode = (os.getenv("AI_INTENT_MODE") or "rules_first").strip().lower()
    c.record("production default is rules_first unless configured", default_mode in ("rules_first", "llm_first", "llm_shadow"))
    c.record("OpenAI not usable without ENABLE_OPENAI", not settings.openai_usable)
    c.record("llm_intent_first only when mode set", settings.llm_intent_first == (default_mode in ("llm_first", "llm-first", "llm")))


async def test_llm_intent_schema_fields(c: Counter) -> None:
    payload = _valid_llm_payload()
    validated = validate_llm_classification(payload, "excavator jaipur")
    legacy = to_legacy_classification(validated)
    for key in ("response_goal", "validation_notes", "search_filters", "rich", "user_sentiment"):
        c.record(f"legacy carries {key}", key in legacy, str(legacy.get(key))[:40])


async def main() -> int:
    c = Counter()
    print("Phase 7 — LLM-first intent baseline")
    await test_config_defaults(c)
    await test_valid_llm_primary(c)
    await test_invalid_json_rules_fallback(c)
    await test_low_confidence_fallback(c)
    await test_forbidden_tool_blocked(c)
    await test_brand_query_routing(c)
    await test_frustration_no_search(c)
    await test_shadow_mode_uses_rules(c)
    await test_llm_intent_schema_fields(c)
    print(f"\nPhase 7 totals: {c.passed} passed, {c.failed} failed")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
