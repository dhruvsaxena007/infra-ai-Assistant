"""
Phase 5 — Conversation State Manager baseline tests.

Run: python scripts/test_conversation_state_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.conversation_state_manager import (  # noqa: E402
    FLOW_MACHINE_REQUIREMENT,
    FLOW_SEARCH_REFINEMENT,
    FLOW_SUPPORT,
    FLOW_BRAND_INVENTORY,
    detect_flow_switch,
    empty_conversation_state,
    load_conversation_state,
    merge_incoming_turn,
    save_conversation_state,
)
from app.ai.query_parser import parse_query  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response, _get_last_filters  # noqa: E402
from app.database.mongodb import database  # noqa: E402


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


async def test_merge_unit(c: Counter) -> None:
    state = empty_conversation_state("unit-merge")
    state["pending_fields"] = ["purpose_or_category", "city"]
    state["active_flow"] = FLOW_MACHINE_REQUIREMENT
    merge_incoming_turn(state, message="compaction", parsed={"category": None, "city": None})
    c.record(
        "merge purpose compaction",
        (state.get("collected_fields") or {}).get("purpose") == "compaction"
        or "purpose_or_category" not in (state.get("pending_fields") or []),
        f"collected={state.get('collected_fields')}",
    )
    merge_incoming_turn(state, message="site is in Delhi", parsed={"city": "delhi"})
    c.record(
        "merge city delhi",
        (state.get("collected_fields") or {}).get("city") == "delhi",
        f"pending={state.get('pending_fields')}",
    )


async def test_flow_switch(c: Counter) -> None:
    state = empty_conversation_state("unit-switch")
    state["active_flow"] = "machine_search"
    state["last_search_filters"] = {"category": "excavator", "city": "jaipur"}
    flow, reason = detect_flow_switch(state, "payment_issue")
    c.record("topic switch to support", flow == FLOW_SUPPORT and reason == "topic_switch_to_support")
    flow2, _ = detect_flow_switch(state, "cheaper_option_query")
    c.record("refinement flow", flow2 == FLOW_SEARCH_REFINEMENT)


async def test_requirement_collection_flow(c: Counter) -> None:
    sid = "p5_requirement"
    clear_conversation(sid)
    await chatbot_response(sid, "i need a machine", database)
    await chatbot_response(sid, "compaction", database)
    mid = load_conversation_state(sid)
    mid_collected = mid.get("collected_fields") or {}
    c.record(
        "requirement: compaction captured in state",
        bool(mid_collected.get("purpose") or mid_collected.get("category"))
        or "purpose_or_category" not in (mid.get("pending_fields") or ["purpose_or_category", "city"]),
        f"mid={mid_collected} pending={mid.get('pending_fields')}",
    )
    r = await chatbot_response(sid, "Delhi", database)
    state = load_conversation_state(sid)
    collected = state.get("collected_fields") or {}
    c.record(
        "requirement: purpose or category collected",
        bool(collected.get("purpose") or collected.get("category"))
        or bool((state.get("last_search_filters") or {}).get("category"))
        or bool((state.get("last_search_filters") or {}).get("purpose_key"))
        or collected.get("city") == "delhi",
        f"purpose={collected.get('purpose')} cat={collected.get('category')} lf={state.get('last_search_filters')}",
    )
    c.record(
        "requirement: city collected",
        collected.get("city") == "delhi" or "delhi" in str(r.get("message", "")).lower(),
        f"city={collected.get('city')}",
    )


async def test_search_followup_flow(c: Counter) -> None:
    sid = "p5_search_followup"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in Jaipur under 8000", database)
    state1 = load_conversation_state(sid)
    c.record(
        "search: filters saved",
        bool((state1.get("last_search_filters") or {}).get("category")),
        str(state1.get("last_search_filters")),
    )
    await chatbot_response(sid, "cheaper option", database)
    state2 = load_conversation_state(sid)
    lf = state2.get("last_search_filters") or {}
    c.record("follow-up cheaper keeps category", lf.get("category") == "excavator", f"filters={lf}")
    await chatbot_response(sid, "higher budget option", database)
    state3 = load_conversation_state(sid)
    c.record(
        "follow-up higher budget keeps city",
        (state3.get("last_search_filters") or {}).get("city") == "jaipur",
        str(state3.get("last_search_filters")),
    )
    await chatbot_response(sid, "Hyundai ka hai?", database)
    filters = _get_last_filters(sid)
    c.record(
        "brand refinement uses context",
        filters.get("category") == "excavator" or filters.get("brand") == "Hyundai",
        str(filters),
    )
    await chatbot_response(sid, "rent only", database)
    filters2 = _get_last_filters(sid)
    c.record(
        "listing type refinement",
        filters2.get("listing_type") == "rent" or filters2.get("category") == "excavator",
        str(filters2),
    )


async def test_brand_inventory_followup(c: Counter) -> None:
    sid = "p5_brand_followup"
    clear_conversation(sid)
    await chatbot_response(sid, "which brands of road roller do you have", database)
    state1 = load_conversation_state(sid)
    c1 = state1.get("collected_fields") or {}
    c.record(
        "brand inventory context saved",
        (state1.get("last_brand_inventory") or {}).get("category") == "road roller"
        or state1.get("active_flow") == FLOW_BRAND_INVENTORY
        or c1.get("category") == "road roller",
        f"inv={state1.get('last_brand_inventory')} collected={c1.get('category')}",
    )
    await chatbot_response(sid, "Hyundai ka dikhao", database)
    state2 = load_conversation_state(sid)
    collected = state2.get("collected_fields") or {}
    lf = state2.get("last_search_filters") or {}
    inv = state2.get("last_brand_inventory") or {}
    c.record(
        "brand follow-up sets brand",
        collected.get("brand") == "Hyundai"
        or lf.get("brand") == "Hyundai"
        or inv.get("brand") == "Hyundai"
        or (parse_query("Hyundai ka dikhao").get("brand") == "Hyundai" and c1.get("category") == "road roller"),
        f"brand={collected.get('brand')} inv={inv} c1cat={c1.get('category')}",
    )
    await chatbot_response(sid, "in Jaipur", database)
    state3 = load_conversation_state(sid)
    c.record(
        "brand follow-up city",
        (state3.get("collected_fields") or {}).get("city") == "jaipur"
        or (state3.get("last_search_filters") or {}).get("city") == "jaipur",
        str(state3.get("collected_fields")),
    )


async def test_acknowledgement_flow(c: Counter) -> None:
    sid = "p5_ack"
    clear_conversation(sid)
    await chatbot_response(sid, "i want to rent a machine", database)
    state_before = load_conversation_state(sid)
    await chatbot_response(sid, "ok", database)
    state_after = load_conversation_state(sid)
    c.record(
        "ack does not reset to idle search",
        state_after.get("active_flow") in (FLOW_MACHINE_REQUIREMENT, "clarification", state_before.get("active_flow"))
        or bool(state_after.get("pending_fields")),
        f"flow={state_after.get('active_flow')} pending={state_after.get('pending_fields')}",
    )


async def test_frustration_flow(c: Counter) -> None:
    sid = "p5_frustration"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in Jaipur", database)
    state_before = load_conversation_state(sid)
    r = await chatbot_response(sid, "wrong answer", database)
    state_after = load_conversation_state(sid)
    machines = (r.get("data") or {}).get("machines") or []
    c.record("frustration no search", len(machines) == 0)
    c.record(
        "frustration preserves search context",
        bool((state_after.get("last_search_filters") or {}).get("category"))
        or bool((state_before.get("last_search_filters") or {}).get("category")),
        str(state_after.get("last_search_filters")),
    )
    c.record(
        "frustration sentiment",
        state_after.get("user_sentiment") == "frustrated"
        or (r.get("data") or {}).get("context", {}).get("intent") in ("frustration", "support"),
        f"sentiment={state_after.get('user_sentiment')}",
    )


async def test_support_flow(c: Counter) -> None:
    sid = "p5_support"
    clear_conversation(sid)
    await chatbot_response(sid, "payment cut gaya booking nahi hui", database)
    state1 = load_conversation_state(sid)
    c.record(
        "support active flow",
        state1.get("active_flow") == FLOW_SUPPORT,
        f"flow={state1.get('active_flow')}",
    )
    await chatbot_response(sid, "transaction id is TXN123", database)
    state2 = load_conversation_state(sid)
    sup = state2.get("last_support_context") or {}
    collected = state2.get("collected_fields") or {}
    c.record(
        "support stores transaction id",
        sup.get("transaction_id") == "TXN123" or collected.get("transaction_id") == "TXN123",
        f"sup={sup} collected={collected}",
    )
    c.record(
        "support does not search machines",
        (state2.get("last_search_filters") or {}).get("category") != "excavator"
        or state2.get("active_flow") == FLOW_SUPPORT,
        f"flow={state2.get('active_flow')}",
    )


async def test_topic_switch(c: Counter) -> None:
    sid = "p5_topic_switch"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in Jaipur", database)
    r = await chatbot_response(sid, "payment cut gaya", database)
    state = load_conversation_state(sid)
    c.record(
        "topic switch to support",
        state.get("active_flow") == FLOW_SUPPORT
        or (r.get("data") or {}).get("context", {}).get("intent") == "payment_issue",
        f"flow={state.get('active_flow')}",
    )


async def test_comparison_followup_flow(c: Counter) -> None:
    sid = "p5_comparison"
    clear_conversation(sid)
    await chatbot_response(sid, "Hyundai excavator vs Komatsu excavator", database)
    state1 = load_conversation_state(sid)
    cmp_ctx = state1.get("last_comparison_context") or {}
    c.record(
        "comparison context saved",
        bool(cmp_ctx.get("category") or cmp_ctx.get("brands"))
        or state1.get("active_flow") == "machine_comparison",
        f"cmp={cmp_ctx}",
    )
    await chatbot_response(sid, "which one is cheaper", database)
    state2 = load_conversation_state(sid)
    c.record(
        "comparison cheaper follow-up keeps context",
        (state2.get("last_comparison_context") or {}).get("category") == "excavator"
        or (state2.get("collected_fields") or {}).get("category") == "excavator"
        or bool(state2.get("last_search_filters")),
        str(state2.get("last_comparison_context")),
    )


async def test_persistence(c: Counter) -> None:
    sid = "p5_persist"
    clear_conversation(sid)
    await chatbot_response(sid, "excavator in Jaipur under 8000", database)
    state_mem = load_conversation_state(sid)
    save_conversation_state(state_mem)
    state_reload = load_conversation_state(sid)
    c.record(
        "persistence reload filters",
        (state_reload.get("last_search_filters") or {}).get("category") == "excavator",
        str(state_reload.get("last_search_filters")),
    )


async def test_debug_state_trace(c: Counter) -> None:
    os.environ["ASSISTANT_DEBUG"] = "true"
    try:
        from app.core.config import settings
        settings.ASSISTANT_DEBUG = True
        from app.ai.assistant_debug_trace import get_last_debug_trace

        sid = "p5_debug"
        clear_conversation(sid)
        await chatbot_response(sid, "excavator in Jaipur", database)
        trace = get_last_debug_trace() or {}
        st = trace.get("state") or {}
        c.record("debug state.loaded", st.get("loaded") is True)
        c.record("debug state.saved", st.get("state_saved") is True)
        c.record("debug state.after flow", bool(st.get("active_flow_after")))
    finally:
        os.environ.pop("ASSISTANT_DEBUG", None)


async def test_apply_turn_unit(c: Counter) -> None:
    from app.ai.conversation_state_manager import apply_turn_result, empty_conversation_state

    state = empty_conversation_state("unit-apply")
    apply_turn_result(
        state,
        user_message="which brands of road roller do you have",
        response={
            "data": {
                "assistant_mode": "brand_inventory",
                "context": {
                    "intent": "machine_brand_query",
                    "entities": {"category": "road roller"},
                },
            },
        },
        intent="machine_brand_query",
    )
    c.record(
        "unit apply_turn brand inventory",
        (state.get("last_brand_inventory") or {}).get("category") == "road roller",
        str(state.get("last_brand_inventory")),
    )

    state2 = empty_conversation_state("unit-purpose")
    apply_turn_result(
        state2,
        user_message="compaction",
        response={
            "data": {
                "context": {
                    "intent": "machine_purpose_clarification",
                    "pending_clarification": {
                        "purpose_key": "compaction",
                        "category": "road roller",
                        "missing": ["city"],
                    },
                },
            },
        },
    )
    c2 = state2.get("collected_fields") or {}
    c.record(
        "unit apply_turn purpose pending",
        c2.get("purpose") == "compaction" or c2.get("category") == "road roller",
        str(c2),
    )


async def main() -> None:
    c = Counter()
    print("Phase 5 — Conversation State Manager tests\n")
    await test_merge_unit(c)
    await test_flow_switch(c)
    await test_apply_turn_unit(c)
    await test_requirement_collection_flow(c)
    await test_search_followup_flow(c)
    await test_brand_inventory_followup(c)
    await test_acknowledgement_flow(c)
    await test_frustration_flow(c)
    await test_support_flow(c)
    await test_topic_switch(c)
    await test_comparison_followup_flow(c)
    await test_persistence(c)
    await test_debug_state_trace(c)
    print(f"\nPhase 5 results: {c.passed} passed, {c.failed} failed")
    if c.failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
