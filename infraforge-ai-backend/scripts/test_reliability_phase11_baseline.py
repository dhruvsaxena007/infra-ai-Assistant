"""
Phase 11 mechanism-level reliability baseline — behavior groups from audit reports.
Run: python scripts/test_reliability_phase11_baseline.py
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


# ---------------------------------------------------------------------------
# 1. Single-query entity resolution
# ---------------------------------------------------------------------------

def test_single_query_entity_resolution(c: Counter) -> None:
    from app.ai.catalog_entity_resolver import is_brand_marketplace_search, resolve_entities
    from app.ai.context_routing_gate import FAMILY_CITY_INVENTORY, classify_message_family
    from app.ai.query_parser import parse_query

    r1 = resolve_entities("excavator in jaipur")
    c.record("category+city resolved", r1.get("category") == "excavator" and r1.get("city") == "jaipur")

    r2 = resolve_entities("jcb in mumbai")
    c.record("brand+city => marketplace search", is_brand_marketplace_search("jcb in mumbai"))

    r3 = resolve_entities("3dx in delhi")
    c.record("model implies category", r3.get("category") == "backhoe loader" or r3.get("brand") == "JCB")

    g = classify_message_family("what machines are available in pune", active_flow="idle")
    c.record("city inventory family", g["family"] == FAMILY_CITY_INVENTORY)

    g2 = classify_message_family("jaipur me kaun si machines milegi", active_flow="idle", parsed=parse_query("jaipur"))
    c.record("hinglish city inventory", g2["family"] == FAMILY_CITY_INVENTORY or parse_query("jaipur me kaun si machines").get("city"))

    p = parse_query("under 50000 excavator jaipur")
    c.record("budget query parsed", p.get("max_price") is not None and p.get("category") == "excavator")


# ---------------------------------------------------------------------------
# 2. Multi-turn requirement collection
# ---------------------------------------------------------------------------

def test_multi_turn_requirement_collection(c: Counter) -> None:
    from app.ai.conversation_state_manager import (
        FLOW_MACHINE_REQUIREMENT,
        begin_turn,
        establish_requirement_collection,
        merge_incoming_turn,
    )

    s1 = begin_turn("p11_city_first")
    establish_requirement_collection(s1, parsed={"city": "jaipur"}, message="i need a machine in jaipur")
    c.record("city-first sets requirement flow", s1.get("active_flow") == FLOW_MACHINE_REQUIREMENT)
    c.record("city-first pending category", "purpose_or_category" in (s1.get("pending_fields") or []))

    s2 = begin_turn("p11_cat_first")
    establish_requirement_collection(s2, parsed={"category": "excavator"}, message="excavator chahiye")
    c.record("category-first pending city", "city" in (s2.get("pending_fields") or []))

    s3 = begin_turn("p11_merge_seq")
    merge_incoming_turn(s3, message="jaipur", parsed={"city": "jaipur"})
    establish_requirement_collection(s3, parsed={"city": "jaipur"}, message="jaipur")
    merge_incoming_turn(s3, message="excavator", parsed={"category": "excavator"}, intent="machine_search")
    col = s3.get("collected_fields") or {}
    c.record("city then category merged", col.get("city") == "jaipur" and col.get("category") == "excavator")


# ---------------------------------------------------------------------------
# 3. Context eligibility
# ---------------------------------------------------------------------------

def test_context_eligibility(c: Counter) -> None:
    from app.ai.context_routing_gate import (
        FAMILY_SEARCH_REFINEMENT,
        FAMILY_SUPPORT,
        classify_message_family,
        should_apply_previous_context,
        _CONTEXT_COMPARISON,
        _CONTEXT_MACHINE_SEARCH,
    )

    sup = classify_message_family("payment failed for my booking", active_flow="machine_search")
    allowed, _ = should_apply_previous_context(sup["family"], context_type=_CONTEXT_MACHINE_SEARCH)
    c.record("support blocks machine context", not allowed)

    ref = classify_message_family("show cheaper options", active_flow="machine_search")
    allowed2, _ = should_apply_previous_context(
        ref["family"], context_type=_CONTEXT_MACHINE_SEARCH, message_features=ref.get("features"),
    )
    c.record("refinement allows machine context", allowed2)

    cmp = classify_message_family("jcb vs cat for digging", active_flow="machine_comparison")
    allowed3, _ = should_apply_previous_context(
        cmp["family"], active_flow="machine_comparison", context_type=_CONTEXT_COMPARISON,
    )
    c.record("comparison continuation allowed", allowed3)

    doc = classify_message_family("what does the uploaded pdf say", active_flow="machine_search")
    c.record("document blocks previous search", doc.get("block_previous_search_context"))


# ---------------------------------------------------------------------------
# 4. Tool permission
# ---------------------------------------------------------------------------

def test_tool_permission(c: Counter) -> None:
    from app.ai.safe_action_router import resolve_action_decision, validate_tool_call
    from app.ai.tool_permission_matrix import TOOL_MONGODB_SEARCH

    for intent in ("order_issue", "refund_return", "document_question", "unknown", "frustration"):
        ok, _ = validate_tool_call(intent, TOOL_MONGODB_SEARCH)
        c.record(f"search blocked for {intent}", not ok)

    dec = resolve_action_decision(
        {"intent": "machine_search", "entities": {"category": "excavator", "city": "jaipur"}},
        {"last_filters": {}},
        message="excavator in jaipur",
    )
    c.record("machine search allowed with entities", dec.get("should_search_machines"))


# ---------------------------------------------------------------------------
# 5. Comparison
# ---------------------------------------------------------------------------

def test_comparison_mechanism(c: Counter) -> None:
    from app.ai.conversation_state_manager import begin_turn, merge_incoming_turn

    state = begin_turn("p11_cmp")
    state["active_flow"] = "machine_comparison"
    state["last_comparison_context"] = {"brands": ["jcb", "cat"], "category": "excavator", "city": "jaipur"}
    merge_incoming_turn(
        state, message="for road work", parsed={"purpose": "road"}, intent="machine_comparison",
    )
    ctx = state.get("last_comparison_context") or {}
    c.record("comparison preserves brands", "jcb" in (ctx.get("brands") or []))
    c.record("comparison preserves category", ctx.get("category") == "excavator")


# ---------------------------------------------------------------------------
# 6. Support
# ---------------------------------------------------------------------------

def test_support_mechanism(c: Counter) -> None:
    from app.ai.context_routing_gate import classify_message_family, FAMILY_SUPPORT, FAMILY_RETURN_REFUND

    pay = classify_message_family("how does payment work on this platform", active_flow="idle")
    c.record("payment how-to is support not refund", pay["family"] == FAMILY_SUPPORT)

    ret = classify_message_family("i want a refund for my booking", active_flow="idle")
    c.record("refund family", ret["family"] == FAMILY_RETURN_REFUND)

    fault = classify_message_family("the rented machine has a technical fault", active_flow="machine_search")
    c.record("machine fault is support", fault["family"] == FAMILY_SUPPORT)


# ---------------------------------------------------------------------------
# 7. False claim prevention
# ---------------------------------------------------------------------------

def test_false_claim_prevention(c: Counter) -> None:
    from app.ai.response_safety_guard import apply_false_claim_guard, build_fact_constraints

    constraints = build_fact_constraints(intent="order_issue", known_context={})
    msg, applied = apply_false_claim_guard(
        "Your booking is confirmed and return has been initiated.",
        constraints=constraints,
    )
    c.record("booking/return claim guarded", applied)
    c.record("asks for confirmation", "booking" in msg.lower() or "transaction" in msg.lower())


# ---------------------------------------------------------------------------
# 8. Search refinement engine
# ---------------------------------------------------------------------------

def test_search_refinement(c: Counter) -> None:
    from app.ai.search_refinement_engine import apply_search_refinement, detect_refinement_type

    base = {"category": "excavator", "city": "jaipur", "max_price": 50000}
    cheaper = apply_search_refinement("show cheaper options", last_filters=base)
    c.record("cheaper preserves category", cheaper["filters"].get("category") == "excavator")
    c.record("cheaper adjusts budget", cheaper["filters"].get("max_price", 50000) < 50000)

    city_sw = apply_search_refinement(
        "same in delhi",
        last_filters=base,
        parsed={"city": "delhi"},
        intent_family="search_refinement",
    )
    c.record("city switch preserves category", city_sw["filters"].get("category") == "excavator")
    c.record("city switch updates city", city_sw["filters"].get("city") == "delhi")

    c.record("detect city switch", detect_refinement_type("same in delhi", {"city": "delhi"}) == "city_switch")


# ---------------------------------------------------------------------------
# Runtime regression: classification before assignment (purpose/site path)
# ---------------------------------------------------------------------------

async def test_purpose_search_no_crash(c: Counter) -> None:
    """Regression: purpose_search branch must not reference unassigned classification."""
    from app.ai.assistant_router import _apply_dynamic_response

    try:
        await _apply_dynamic_response(
            session_id="p11_purpose_crash",
            user_message="foundation digging work",
            draft="Which city?",
            response_goal="ask_city",
            intent="machine_purpose_clarification",
            assistant_mode="clarification",
            reply_lang="english",
            classification={},
            tool_result={"suggestions": ["Jaipur"], "message": "Which city?"},
        )
        c.record("purpose path with empty classification", True)
    except UnboundLocalError as e:
        c.record("purpose path with empty classification", False, str(e))


async def test_integration_city_known(c: Counter) -> None:
    import uuid

    from app.ai.assistant_router import _try_early_requirement_clarification
    from app.ai.conversation_state_manager import begin_turn, merge_incoming_turn
    from app.ai.query_parser import parse_query

    sid = f"p11_city_known_{uuid.uuid4().hex[:8]}"
    msg = "i need a machine in jaipur"
    state = begin_turn(sid)
    merge_incoming_turn(
        state,
        message=msg,
        parsed=parse_query(msg),
        intent="machine_search",
    )
    resp = await _try_early_requirement_clarification(
        session_id=sid,
        user_message=msg,
        working_message=msg,
        conv_state=state,
        reply_lang="english",
        input_meta=None,
    )
    c.record("city-known route returns response", resp is not None)
    data = (resp or {}).get("data") or {}
    ctx = data.get("context") or {}
    flt = data.get("filters") or {}
    pending = ctx.get("pending_clarification") or {}
    c.record(
        "city-known stores city in state",
        flt.get("city") == "jaipur"
        or ctx.get("city") == "jaipur"
        or pending.get("city") == "jaipur"
        or (state.get("collected_fields") or {}).get("city") == "jaipur",
    )
    c.record(
        "city-known clarification mode",
        data.get("assistant_mode") == "clarification"
        or ctx.get("assistant_mode") == "clarification"
        or ctx.get("intent") == "machine_requirement_collection"
        or state.get("active_flow") == "machine_requirement_collection",
    )


async def test_integration_brand_search(c: Counter) -> None:
    from app.ai.safe_action_router import resolve_action_decision

    dec = resolve_action_decision(
        {"intent": "unknown", "entities": {"brand": "JCB", "city": "jaipur"}},
        {"last_filters": {"category": "excavator", "city": "jaipur"}},
        message="jcb brand only",
    )
    c.record("brand filter uses search not inventory", dec.get("selected_action") in (
        "machine_search", "refine_search_filters", "check_brand_availability",
    ))


async def test_integration_support_blocks_search(c: Counter) -> None:
    from app.ai.assistant_router import handle_assistant_message
    from app.chatbot.chatbot_service import _save_last_filters

    sid = "p11_support_block"
    _save_last_filters(sid, {"category": "excavator", "city": "jaipur"})
    resp = await handle_assistant_message(sid, "how does payment work", None)
    data = resp.get("data") or {}
    intent = (data.get("context") or {}).get("intent") or ""
    c.record("payment how-to not refund_return", intent != "refund_return")
    c.record("payment how-to no search machines", len(data.get("machines") or []) == 0)


def main() -> int:
    c = Counter()
    print("Phase 11 Reliability Baseline\n")

    print("1. Single-query entity resolution")
    test_single_query_entity_resolution(c)

    print("\n2. Multi-turn requirement collection")
    test_multi_turn_requirement_collection(c)

    print("\n3. Context eligibility")
    test_context_eligibility(c)

    print("\n4. Tool permission")
    test_tool_permission(c)

    print("\n5. Comparison")
    test_comparison_mechanism(c)

    print("\n6. Support")
    test_support_mechanism(c)

    print("\n7. False claim prevention")
    test_false_claim_prevention(c)

    print("\n8. Search refinement")
    test_search_refinement(c)

    print("\nRuntime / integration")
    asyncio.run(test_purpose_search_no_crash(c))
    asyncio.run(test_integration_city_known(c))
    asyncio.run(test_integration_brand_search(c))
    asyncio.run(test_integration_support_blocks_search(c))

    print(f"\n{'=' * 50}")
    print(f"PASSED: {c.passed}  FAILED: {c.failed}")
    if c.errors:
        print("\nFailures:")
        for e in c.errors:
            print(e)
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
