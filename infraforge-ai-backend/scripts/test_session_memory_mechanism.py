"""
Generalized session memory + purpose revision tests (not phrase-specific patches).
Run: python scripts/test_session_memory_mechanism.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AI_INTENT_MODE", "rules_first")
os.environ.setdefault("DOMAIN_INTELLIGENCE_MODE", "hybrid")


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_purpose_revision_overrides_stale_category():
    from app.ai.session_requirement_context import enrich_parsed_from_session

    parsed = enrich_parsed_from_session(
        "machine need for digging in jaipur on rent under 20k",
        {"city": "jaipur", "max_price": 20000, "listing_type": "rent"},
        last_filters={"category": "dump truck", "city": "jaipur"},
        session_collected={"category": "dump truck", "city": "jaipur", "purpose": "transport"},
    )
    _assert(parsed.get("purpose_key") == "digging", f"purpose={parsed.get('purpose_key')}")
    _assert(
        parsed.get("category") in ("excavator", "backhoe loader"),
        f"category should be digging machine, got {parsed.get('category')}",
    )
    print("PASS purpose_revision_overrides_stale_category")


def test_broad_vague_skipped_when_session_has_context():
    from app.chatbot.assistant_intelligence import is_broad_vague_query

    collected = {"city": "jaipur", "purpose": "transport"}
    _assert(
        not is_broad_vague_query(
            "i need a truck for transporting sand",
            session_collected=collected,
        ),
        "should not treat as broad vague when session has city",
    )
    _assert(
        not is_broad_vague_query("i need", session_collected=collected),
        "bare i need should not reset when session has partial state",
    )
    print("PASS broad_vague_skipped_when_session_has_context")


def test_requirement_engine_purpose_revision():
    from app.ai.requirement_state_engine import (
        apply_requirement_transition,
        build_search_filters,
        empty_requirement_state,
    )

    req = empty_requirement_state()
    req["explicit"] = {"purpose": "transport", "category": "dump truck", "city": "jaipur"}
    req["derived"] = {"category": "dump truck"}
    req["provenance"] = {"purpose": "user_explicit", "category": "user_explicit", "city": "user_explicit"}

    decision = apply_requirement_transition(
        req,
        message="machine need for digging in jaipur on rent under 20k",
        parsed={"city": "jaipur", "max_price": 20000, "listing_type": "rent"},
    )
    filters = build_search_filters(req)
    _assert(req["explicit"].get("purpose") == "digging", f"purpose={req['explicit'].get('purpose')}")
    _assert(
        filters.get("category") in ("excavator", "backhoe loader"),
        f"search category={filters.get('category')}",
    )
    _assert(decision.search_triggered or filters.get("city"), "should be searchable state")
    print("PASS requirement_engine_purpose_revision")


def test_typo_purpose_gidding():
    from app.chatbot.assistant_intelligence import resolve_purpose_key

    _assert(resolve_purpose_key("gidding") == "digging", "gidding should fuzzy-match digging")
    print("PASS typo_purpose_gidding")


def test_sanitize_display_name():
    from app.ai.assistant_brain import sanitize_display_name

    _assert(sanitize_display_name("Null") is None, "Null should be sanitized away")
    _assert(sanitize_display_name("Dhruv") == "Dhruv", "valid name should remain")
    print("PASS sanitize_display_name")


def test_unsupported_service_hybrid():
    from app.ai.domain_intelligence_gateway import interpret_domain_rules

    interp = interpret_domain_rules("i want to rent a bike")
    _assert(
        interp.response_mode in ("unsupported_service", "unrelated_redirect"),
        f"mode={interp.response_mode}",
    )
    print("PASS unsupported_service_hybrid")


def test_fresh_broad_clears_stale_requirement_state():
    from app.ai.context_routing_gate import evaluate_routing_gate, set_current_gate
    from app.ai.conversation_state_manager import (
        empty_conversation_state,
        merge_incoming_turn,
    )
    from app.ai.requirement_state_engine import build_search_filters

    state = empty_conversation_state("test_fresh_broad")
    state["collected_fields"]["category"] = "road roller"
    state["collected_fields"]["city"] = "delhi"
    state["last_search_filters"] = {"category": "road roller", "city": "delhi"}
    state["active_flow"] = "machine_search"

    gate = evaluate_routing_gate("I want a machine", active_flow=state["active_flow"])
    set_current_gate(gate)
    merge_incoming_turn(state, message="I want a machine")

    decision = state.get("_requirement_decision")
    _assert(decision is not None, "requirement decision missing")
    _assert(not decision.search_triggered, "broad vague must not trigger search")
    _assert(
        decision.reason in ("missing_purpose_or_category", "missing_city"),
        f"reason={decision.reason}",
    )
    filters = build_search_filters(state.get("_requirement_decision").state_after or {})
    _assert(not filters.get("category"), f"stale category leaked: {filters}")
    _assert(not filters.get("city"), f"stale city leaked: {filters}")
    print("PASS fresh_broad_clears_stale_requirement_state")


def main():
    test_purpose_revision_overrides_stale_category()
    test_broad_vague_skipped_when_session_has_context()
    test_requirement_engine_purpose_revision()
    test_fresh_broad_clears_stale_requirement_state()
    test_typo_purpose_gidding()
    test_sanitize_display_name()
    test_unsupported_service_hybrid()
    print("\nALL SESSION MEMORY MECHANISM TESTS PASSED")


if __name__ == "__main__":
    main()
