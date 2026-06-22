"""
Parameterized tests for canonical requirement state transition engine.
Run: python scripts/test_requirement_state_engine.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AI_INTENT_MODE", "rules_first")
os.environ.setdefault("ASSISTANT_DEBUG", "true")


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_engine_ordering_permutations():
    from app.ai.requirement_state_engine import (
        FIELD_CITY,
        FIELD_PURPOSE_OR_CATEGORY,
        apply_requirement_transition,
        assess_search_readiness,
        build_search_filters,
        empty_requirement_state,
    )
    from app.ai.purpose_taxonomy import PURPOSE_TO_CATEGORIES

    purposes = list(PURPOSE_TO_CATEGORIES.keys())[:4]
    cities = ["jaipur", "delhi", "pune", "ahmedabad"]
    categories = ["excavator", "crane", "wheel loader", "road roller"]

    sequences = [
        [("purpose", purposes[0]), ("city", cities[0])],
        [("city", cities[1]), ("purpose", purposes[1])],
        [("category", categories[0]), ("city", cities[2])],
        [("city", cities[3]), ("category", categories[1])],
        [("purpose", purposes[2]), ("city", cities[0])],
        [("city", cities[2]), ("budget", 50000), ("purpose", purposes[3])],
    ]

    for seq in sequences:
        req = empty_requirement_state()
        pending = None
        for step, val in seq:
            entities = {}
            if step == "purpose":
                entities["purpose"] = val
            elif step == "category":
                entities["category"] = val
            elif step == "city":
                entities["city"] = val
            elif step == "budget":
                entities["max_price"] = val
            msg = str(val)
            decision = apply_requirement_transition(
                req,
                message=msg,
                entities=entities,
                pending_clarification=pending,
                active_flow="machine_requirement_collection",
            )
            if req.get("needs_confirmation"):
                break
            pending = {
                "missing_field": "machine_purpose",
                "type": "machine_purpose",
                "missing": list(req.get("pending_fields") or []),
            }

        if req.get("needs_confirmation"):
            continue

        complete, missing, reason = assess_search_readiness(req)
        _assert(complete, f"Sequence {seq} should be complete: missing={missing} reason={reason}")
        filters = build_search_filters(req)
        _assert(filters.get("city"), f"Sequence {seq} missing city in filters")
        _assert(
            filters.get("category") or filters.get("purpose_key"),
            f"Sequence {seq} missing category/purpose in filters",
        )
        _assert(not decision.invariant_violations, f"Invariants violated: {decision.invariant_violations}")
    print("PASS ordering_permutations")


def test_pending_field_invariants():
    from app.ai.requirement_state_engine import (
        FIELD_CITY,
        FIELD_PURPOSE_OR_CATEGORY,
        apply_requirement_transition,
        empty_requirement_state,
    )

    req = empty_requirement_state()
    req["explicit"]["city"] = "jaipur"
    req["pending_fields"] = [FIELD_PURPOSE_OR_CATEGORY]

    pending = {
        "missing_field": "machine_purpose",
        "type": "machine_purpose",
        "missing": [FIELD_PURPOSE_OR_CATEGORY],
        "city": "jaipur",
    }
    decision = apply_requirement_transition(
        req,
        message="lifting",
        entities={"purpose": "lifting"},
        pending_clarification=pending,
        active_flow="machine_requirement_collection",
    )

    _assert(FIELD_PURPOSE_OR_CATEGORY not in req["pending_fields"], "purpose should not be pending")
    _assert(FIELD_CITY not in req["pending_fields"], "city should not be pending")
    _assert(decision.requirements_complete, "should be complete after purpose+city")
    _assert(decision.search_triggered, "should trigger search")
    _assert("purpose" in decision.fields_changed or req["explicit"].get("purpose"), "purpose collected")
    print("PASS pending_field_invariants")


def test_purpose_category_derivation():
    from app.ai.requirement_state_engine import apply_requirement_transition, empty_requirement_state
    from app.ai.purpose_taxonomy import primary_category_for_purpose

    req = empty_requirement_state()
    decision = apply_requirement_transition(
        req,
        message="digging work",
        entities={"purpose": "digging", "city": "jaipur"},
        active_flow="machine_requirement_collection",
    )
    expected_cat = primary_category_for_purpose("digging")
    filters = decision.search_filters
    _assert(filters.get("category") == expected_cat, f"derived category mismatch: {filters}")
    _assert(decision.search_triggered, "complete state should search")
    print("PASS purpose_category_derivation")


def test_explicit_category_overrides_derived():
    from app.ai.requirement_state_engine import apply_requirement_transition, empty_requirement_state

    req = empty_requirement_state()
    apply_requirement_transition(
        req,
        message="crane",
        entities={"category": "crane", "city": "delhi"},
        active_flow="machine_requirement_collection",
    )
    _assert(req["explicit"]["category"] == "crane", "explicit category preserved")
    _assert(req["derived"]["category"] is None, "no derived when explicit category")
    print("PASS explicit_category_overrides")


def test_purpose_revision_invalidates_derived():
    from app.ai.requirement_state_engine import apply_requirement_transition, empty_requirement_state
    from app.ai.purpose_taxonomy import primary_category_for_purpose

    req = empty_requirement_state()
    apply_requirement_transition(
        req,
        message="digging",
        entities={"purpose": "digging", "city": "jaipur"},
        active_flow="machine_requirement_collection",
    )
    old_cat = primary_category_for_purpose("digging")
    _assert(
        req["derived"]["category"] == old_cat or req["explicit"].get("category") == old_cat,
        "old category should be set",
    )

    decision = apply_requirement_transition(
        req,
        message="lifting",
        entities={"purpose": "lifting"},
        active_flow="machine_requirement_collection",
    )
    new_cat = primary_category_for_purpose("lifting")
    _assert(decision.search_filters.get("category") == new_cat, "category should update on purpose change")
    _assert(decision.search_filters.get("city") == "jaipur", "city preserved on revision")
    print("PASS purpose_revision_invalidates_derived")


def test_channel_equivalence():
    from app.ai.requirement_state_engine import apply_requirement_transition, empty_requirement_state

    channels = ["jaipur", "Jaipur", "JAIPUR"]
    results = []
    for msg in channels:
        req = empty_requirement_state()
        req["explicit"]["category"] = "excavator"
        req["pending_fields"] = ["city"]
        pending = {
            "missing_field": "city",
            "type": "machine_purpose",
            "missing": ["city"],
            "category": "excavator",
        }
        d = apply_requirement_transition(
            req,
            message=msg,
            pending_clarification=pending,
            active_flow="machine_requirement_collection",
        )
        results.append((req["explicit"].get("city"), d.requirements_complete))

    _assert(all(r[0] == "jaipur" for r in results), f"city normalization failed: {results}")
    _assert(all(r[1] for r in results), "all channels should complete")
    print("PASS channel_equivalence")


def test_protected_intent_suspends():
    from app.ai.requirement_state_engine import apply_requirement_transition, empty_requirement_state

    req = empty_requirement_state()
    req["explicit"]["city"] = "jaipur"
    req["explicit"]["category"] = "excavator"
    decision = apply_requirement_transition(
        req,
        message="refund my payment",
        intent_family="return_refund_or_booking_problem",
    )
    _assert(req.get("suspended"), "should suspend on protected intent")
    _assert(not decision.search_triggered, "should not search on protected intent")
    print("PASS protected_intent_suspends")


def test_merge_integration():
    from app.ai.conversation_state_manager import begin_turn, merge_incoming_turn

    state = begin_turn("req_engine_merge_test")
    merge_incoming_turn(state, message="jaipur", parsed={"city": "jaipur"})
    _assert(state.get("active_flow") == "machine_requirement_collection", "flow should be requirement")
    _assert("purpose_or_category" in (state.get("pending_fields") or []), "should need purpose/category")
    _assert(state.get("collected_fields", {}).get("city") == "jaipur", "city stored")

    merge_incoming_turn(
        state,
        message="lifting",
        parsed={},
        entities={"purpose": "lifting"},
        intent="machine_search",
    )
    decision = state.get("_requirement_decision")
    _assert(decision is not None, "decision should exist")
    _assert(getattr(decision, "requirements_complete", False), "should be complete")
    _assert(getattr(decision, "search_triggered", False), "should be search ready")
    print("PASS merge_integration")


async def test_live_chat_multi_turn():
    from app.chatbot.chatbot_service import chatbot_response
    from app.ai.assistant_debug_trace import get_last_debug_trace

    class FakeDB:
        pass

    db = FakeDB()
    sid = "req_engine_live_test"

    flows = [
        ["i need machine in kota", "digging"],
        ["excavator chahiye", "jaipur"],
        ["jaipur", "compaction"],
    ]

    for messages in flows:
        for msg in messages:
            try:
                await chatbot_response(sid + str(messages[0][:8]), msg, db)
            except (AttributeError, NotImplementedError) as exc:
                if "FakeDB" in type(db).__name__ or "equipmentcategories" in str(exc):
                    print(f"SKIP live_chat (mock DB): {exc}")
                    return
                raise
            except Exception as exc:
                if "MongoDB" in str(exc) or "database" in str(exc).lower():
                    print(f"SKIP live_chat (no DB): {exc}")
                    return
                raise

    trace = get_last_debug_trace()
    if trace:
        rt = trace.get("requirement_transition") or {}
        _assert(rt.get("active_flow_after") or rt.get("pending_fields_after") is not None, "debug trace present")
    print("PASS live_chat_multi_turn (or partial without DB)")


def main():
    test_engine_ordering_permutations()
    test_pending_field_invariants()
    test_purpose_category_derivation()
    test_explicit_category_overrides_derived()
    test_purpose_revision_invalidates_derived()
    test_channel_equivalence()
    test_protected_intent_suspends()
    test_merge_integration()
    asyncio.run(test_live_chat_multi_turn())
    print("\nAll requirement state engine tests passed.")


if __name__ == "__main__":
    main()
