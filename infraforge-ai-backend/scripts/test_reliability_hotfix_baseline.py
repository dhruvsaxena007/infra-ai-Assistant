"""
Reliability hotfix baseline — mechanism-level routing, context, tool boundary.
Run: python scripts/test_reliability_hotfix_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AI_INTENT_MODE", "rules_first")
os.environ.setdefault("ENABLE_OPENAI", "false")


class Counter:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
        else:
            self.failed += 1
            msg = f"  [FAIL] {name}" + (f" — {detail}" if detail else "")
            print(msg)
            self.errors.append(msg)


def test_context_eligibility(c: Counter) -> None:
    from app.ai.context_routing_gate import (
        FAMILY_SEARCH_REFINEMENT,
        FAMILY_SUPPORT,
        classify_message_family,
        should_apply_previous_context,
        should_allow_reference_enrich,
        _CONTEXT_COMPARISON,
        _CONTEXT_MACHINE_SEARCH,
    )

    sup = classify_message_family(
        "i rented equipment and there is a technical problem with it",
        active_flow="machine_search",
    )
    c.record("support family for post-rent issue", sup["family"] == FAMILY_SUPPORT)
    c.record("support blocks previous context", sup["block_previous_search_context"])

    allowed, _ = should_apply_previous_context(
        FAMILY_SUPPORT, context_type=_CONTEXT_MACHINE_SEARCH,
    )
    c.record("machine context blocked for support", not allowed)

    ref = classify_message_family("show cheaper options", active_flow="machine_search")
    c.record("refinement family", ref["family"] == FAMILY_SEARCH_REFINEMENT)
    allowed2, _ = should_apply_previous_context(
        FAMILY_SEARCH_REFINEMENT, context_type=_CONTEXT_MACHINE_SEARCH,
        message_features=ref.get("features"),
    )
    c.record("machine context allowed for refinement", allowed2)

    cmp = classify_message_family("compare two brands or models", active_flow="machine_comparison")
    allowed3, _ = should_apply_previous_context(
        cmp["family"], active_flow="machine_comparison", context_type=_CONTEXT_COMPARISON,
    )
    c.record("comparison context for comparison flow", allowed3)

    gate = classify_message_family("you are a hopeless assistant", active_flow="idle")
    ok, reason = should_allow_reference_enrich(gate, message="problem in it", has_last_machines=True)
    c.record("reference enrich blocked for insult", not ok, reason)


def test_frustration_not_conversational(c: Counter) -> None:
    from app.ai.context_routing_gate import evaluate_routing_gate, FAMILY_FRUSTRATION
    from app.ai.universal_turn_engine import analyze_universal_turn

    gate = evaluate_routing_gate("you are a fool", active_flow="idle")
    c.record("fool maps to frustration family", gate["family"] == FAMILY_FRUSTRATION)

    turn = analyze_universal_turn("you are a fool", session_ctx={}, last_filters={"category": "excavator"})
    c.record("universal does not swallow insult as conversational", turn.get("shape") != "conversational")


def test_enrich_blocked(c: Counter) -> None:
    from app.ai.context_routing_gate import evaluate_routing_gate
    from app.ai.intent_signals import enrich_entities_from_context

    evaluate_routing_gate(
        "there is a technical problem in it",
        active_flow="machine_search",
    )
    out = enrich_entities_from_context(
        {},
        {"category": None},
        {"last_filters": {"category": "excavator", "city": "jaipur"}},
    )
    c.record("enrich skips when gate blocks", not out.get("machine_type") and not out.get("city"))


def test_reference_enrich_guard(c: Counter) -> None:
    from app.ai.context_routing_gate import evaluate_routing_gate
    from app.ai.conversation_context import analyze_contextual_turn

    evaluate_routing_gate(
        "there is a technical fault in it",
        active_flow="machine_search",
    )
    ctx = analyze_contextual_turn(
        "there is a technical fault in it",
        last_filters={"category": "excavator"},
        result_ctx={"last_machines": [{"category": "excavator", "name": "Test"}]},
    )
    c.record("reference enrich blocked on support-shaped message", ctx.get("turn_type") != "reference_enrich")


def test_false_claim_guard(c: Counter) -> None:
    from app.ai.response_safety_guard import apply_false_claim_guard, build_fact_constraints

    constraints = build_fact_constraints(intent="order_issue", known_context={})
    msg, applied = apply_false_claim_guard(
        "You've rented this machine and I started the return process for you.",
        constraints=constraints,
    )
    c.record("false rental claim stripped", applied)
    c.record("asks for booking when unconfirmed", "booking" in msg.lower() or "transaction" in msg.lower())


def test_sanitize_router_context(c: Counter) -> None:
    from app.ai.context_routing_gate import classify_message_family, sanitize_router_context

    gate = classify_message_family("payment failed for my booking", active_flow="machine_search")
    clean = sanitize_router_context(
        {"last_filters": {"category": "excavator"}, "collected_fields": {"city": "delhi"}},
        gate,
    )
    c.record("sanitized context clears filters", not clean.get("last_filters"))
    c.record("sanitized context clears collected city", not (clean.get("collected_fields") or {}).get("city"))


def test_normalization_catalog(c: Counter) -> None:
    from app.ai.message_normalizer import normalize_user_message

    n = normalize_user_message("excvator in delih")
    c.record("fuzzy category/city normalization", "excavator" in n.corrected.lower() and "delhi" in n.corrected.lower())


def test_city_inventory_family(c: Counter) -> None:
    from app.ai.context_routing_gate import FAMILY_CITY_INVENTORY, classify_message_family

    g = classify_message_family("what machines are available in pune", active_flow="idle")
    c.record("city inventory family detected", g["family"] == FAMILY_CITY_INVENTORY)


async def test_integration_support_no_search(c: Counter) -> None:
    from app.ai.assistant_router import handle_assistant_message
    from app.chatbot.chatbot_service import _save_last_filters, _persist_last_results

    sid = "rel_support_no_search"
    _save_last_filters(sid, {"category": "excavator", "city": "jaipur"})
    _persist_last_results(sid, [{"name": "X", "category": "excavator", "_id": "1"}], {"category": "excavator"})

    resp = await handle_assistant_message(
        sid,
        "i rented a machine but there is a technical problem in it",
        None,
    )
    data = resp.get("data") or {}
    machines = data.get("machines") or []
    intent = (data.get("context") or {}).get("intent") or ""
    c.record("support turn returns no machines", len(machines) == 0)
    c.record("support intent not machine_search", intent not in ("machine_search", "rent_machine"))


async def test_integration_profile_confirm(c: Counter) -> None:
    from app.ai.user_memory_profile import build_profile_hints, empty_user_profile

    profile = empty_user_profile(profile_id="t")
    profile["preferred_city"] = "jaipur"
    profile["_signals"] = {"city_counts": {"jaipur": 3}}
    hints = build_profile_hints(profile)
    c.record("profile city requires confirmation", hints.get("city_hint_requires_confirmation"))


def test_tool_boundary(c: Counter) -> None:
    from app.ai.safe_action_router import validate_tool_call
    from app.ai.tool_permission_matrix import TOOL_MONGODB_SEARCH

    for intent in ("order_issue", "frustration", "document_question", "refund_return", "unknown"):
        ok, reason = validate_tool_call(intent, TOOL_MONGODB_SEARCH)
        c.record(f"mongodb search blocked for {intent}", not ok, reason or "")


def test_flow_continuation_fields(c: Counter) -> None:
    from app.ai.conversation_state_manager import begin_turn, merge_incoming_turn

    state = begin_turn("flow_req_test")
    state["active_flow"] = "machine_requirement_collection"
    merge_incoming_turn(state, message="excavator", parsed={"category": "excavator"})
    merge_incoming_turn(state, message="jaipur", parsed={"city": "jaipur"})
    collected = state.get("collected_fields") or {}
    c.record("requirement collection keeps category", collected.get("category") == "excavator")
    c.record("requirement collection adds city", collected.get("city") == "jaipur")

    cmp_state = begin_turn("flow_cmp_test")
    cmp_state["active_flow"] = "machine_comparison"
    cmp_state["last_comparison_context"] = {"brands": ["jcb", "cat"], "category": "excavator"}
    merge_incoming_turn(
        cmp_state,
        message="for road work",
        parsed={"purpose": "road"},
        intent="machine_comparison",
    )
    ctx = cmp_state.get("last_comparison_context") or {}
    c.record("comparison preserves brands", "jcb" in (ctx.get("brands") or []))
    c.record("comparison keeps active flow", cmp_state.get("active_flow") == "machine_comparison")


def test_false_claim_selected_machine(c: Counter) -> None:
    from app.ai.response_safety_guard import apply_false_claim_guard, build_fact_constraints

    constraints = build_fact_constraints(
        intent="machine_search",
        known_context={"selected_machine": {"name": "Alpha", "id": "1"}, "booking_confirmed": False},
    )
    msg, applied = apply_false_claim_guard(
        "Your rental for Alpha is confirmed and I contacted the owner.",
        constraints=constraints,
    )
    c.record("selected machine not booked claim guarded", applied)
    c.record("no owner contact claim", "owner" not in msg.lower() or "share" in msg.lower())


def test_normalization_variants(c: Counter) -> None:
    from app.ai.message_normalizer import normalize_user_message

    cases = [
        ("excvator in delih", ("excavator", "delhi")),
        ("road rolar in jaipir", ("road roller", "jaipur")),
        ("crain hire in mumabi", ("crane", "mumbai")),
    ]
    for raw, (need_a, need_b) in cases:
        n = normalize_user_message(raw)
        low = n.corrected.lower()
        c.record(f"normalize variants: {raw[:24]}", need_a in low and need_b in low, n.corrected)


def test_city_inventory_wording(c: Counter) -> None:
    from app.ai.context_routing_gate import FAMILY_CITY_INVENTORY, classify_message_family

    for msg in (
        "list all machines in ahmedabad",
        "show equipment near kolkata",
        "what machines are available in lucknow",
    ):
        g = classify_message_family(msg, active_flow="idle")
        c.record(f"city inventory: {msg[:30]}", g["family"] == FAMILY_CITY_INVENTORY)


def test_debug_trace_fields(c: Counter) -> None:
    from app.ai.assistant_debug_trace import _empty_context_routing

    block = _empty_context_routing()
    required = (
        "current_intent_family",
        "context_eligibility_decision",
        "previous_context_used",
        "previous_context_blocked_reason",
        "reference_enrich_applied",
        "reference_enrich_blocked_reason",
        "active_flow_before",
        "tool_permission_checked",
        "selected_action",
        "selected_tool",
        "search_blocked_reason",
        "false_claim_guard_applied",
    )
    missing = [k for k in required if k not in block]
    c.record("debug trace schema complete", not missing, ", ".join(missing))


async def test_integration_frustration_no_search(c: Counter) -> None:
    from app.ai.assistant_router import handle_assistant_message
    from app.chatbot.chatbot_service import _save_last_filters

    sid = "rel_frustration_no_search"
    _save_last_filters(sid, {"category": "crane", "city": "mumbai"})
    resp = await handle_assistant_message(sid, "you are useless idiot bot", None)
    data = resp.get("data") or {}
    c.record("frustration returns no machines", len(data.get("machines") or []) == 0)


async def test_integration_document_no_search(c: Counter) -> None:
    from app.ai.assistant_router import handle_assistant_message

    sid = "rel_document_no_search"
    resp = await handle_assistant_message(sid, "what does the uploaded pdf document say", None)
    data = resp.get("data") or {}
    intent = (data.get("context") or {}).get("intent") or ""
    c.record("document intent not machine_search", intent not in ("machine_search", "rent_machine"))


async def run_async(c: Counter) -> None:
    await test_integration_support_no_search(c)
    await test_integration_profile_confirm(c)
    await test_integration_frustration_no_search(c)
    await test_integration_document_no_search(c)


def main() -> int:
    c = Counter()
    print("Phase R: Reliability hotfix tests\n")
    test_context_eligibility(c)
    test_frustration_not_conversational(c)
    test_enrich_blocked(c)
    test_reference_enrich_guard(c)
    test_false_claim_guard(c)
    test_false_claim_selected_machine(c)
    test_sanitize_router_context(c)
    test_tool_boundary(c)
    test_flow_continuation_fields(c)
    test_normalization_catalog(c)
    test_normalization_variants(c)
    test_city_inventory_family(c)
    test_city_inventory_wording(c)
    test_debug_trace_fields(c)
    asyncio.run(run_async(c))
    print(f"\nReliability hotfix: {c.passed} passed, {c.failed} failed\n")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
