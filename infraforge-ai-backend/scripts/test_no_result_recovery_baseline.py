"""
Phase 8 — No Result Recovery Engine baseline tests.

Run: python scripts/test_no_result_recovery_baseline.py
With debug: ASSISTANT_DEBUG=true python scripts/test_no_result_recovery_baseline.py
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
os.environ.setdefault("AI_INTENT_MODE", "rules_first")

from app.ai.assistant_debug_trace import (  # noqa: E402
    _current,
    begin_chat_trace,
    end_chat_trace,
    record_recovery,
)
from app.ai.conversation_state_manager import (  # noqa: E402
    FLOW_NO_RESULT_RECOVERY,
    empty_conversation_state,
    load_conversation_state,
    merge_incoming_turn,
)
from app.ai.no_result_recovery import (  # noqa: E402
    RECOVERY_TYPES,
    build_recovery_draft_message,
    detect_recovery_followup,
    empty_recovery_output,
    recovery_context_for_state,
    run_brand_inventory_recovery,
    run_comparison_recovery,
    run_no_result_recovery,
)
from app.ai.tool_permission_matrix import TOOL_MONGODB_SEARCH  # noqa: E402
from app.chatbot.memory import clear_conversation  # noqa: E402
from app.chatbot.chatbot_service import chatbot_response  # noqa: E402
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


def _mock_db():
    return mock.MagicMock()


async def test_recovery_types_defined(c: Counter) -> None:
    required = {
        "nearby_or_alternate_city",
        "budget_relaxation",
        "similar_category",
        "brand_alternative",
        "listing_type_alternative",
        "broaden_filters",
        "ask_missing_context",
        "no_safe_recovery",
    }
    c.record("recovery types present", required.issubset(RECOVERY_TYPES), str(RECOVERY_TYPES))


async def test_support_not_machine_recovery(c: Counter) -> None:
    out = await run_no_result_recovery(
        _mock_db(),
        intent="payment_issue",
        filters={},
    )
    c.record(
        "support uses support_missing_details",
        out.get("recovery_type") == "support_missing_details",
        out.get("recovery_type"),
    )


async def test_document_not_machine_recovery(c: Counter) -> None:
    out = await run_no_result_recovery(_mock_db(), intent="document_question", filters={})
    c.record(
        "document uses ask_document_upload",
        out.get("recovery_type") == "ask_document_upload",
        out.get("recovery_type"),
    )


async def test_image_not_machine_recovery(c: Counter) -> None:
    out = await run_no_result_recovery(_mock_db(), intent="image_followup", filters={})
    c.record(
        "image uses image_clarification",
        out.get("recovery_type") == "image_clarification",
        out.get("recovery_type"),
    )


async def test_permission_blocks_auto_retry(c: Counter) -> None:
    with mock.patch(
        "app.utils.machine_repository.min_price_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=5000.0,
    ), mock.patch(
        "app.utils.machine_repository.search_by_filters",
        new_callable=mock.AsyncMock,
        return_value=[],
    ), mock.patch(
        "app.utils.machine_repository.nearby_cities_with_category_listings",
        new_callable=mock.AsyncMock,
        return_value=[],
    ), mock.patch(
        "app.utils.machine_repository.available_brands_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=[],
    ), mock.patch(
        "app.ai.no_result_recovery._try_auto_retry",
        new_callable=mock.AsyncMock,
        return_value=([{"name": "X"}], "budget"),
    ) as retry_mock:
        out = await run_no_result_recovery(
            _mock_db(),
            intent="machine_search",
            filters={"category": "excavator", "city": "jaipur", "max_price": 100},
            permission_decision={
                "permission_passed": False,
                "allowed_tool": None,
                "should_search_machines": False,
            },
        )
    c.record("permission denies auto retry", not out.get("auto_retried"), str(out.get("auto_retried")))
    c.record("auto_retry_allowed false", not out.get("auto_retry_allowed"))
    c.record(
        "budget recovery still suggested",
        out.get("recovery_type") == "budget_relaxation"
        or bool(out.get("safe_alternatives")),
        out.get("recovery_type"),
    )
    retry_mock.assert_not_called()


async def test_budget_relaxation_mock(c: Counter) -> None:
    machines = [{"name": "E1", "category": "excavator", "city": "jaipur", "price_per_day": 5000}]
    with mock.patch(
        "app.utils.machine_repository.min_price_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=5000.0,
    ), mock.patch(
        "app.ai.no_result_recovery._try_auto_retry",
        new_callable=mock.AsyncMock,
        return_value=(machines, "max_price=None"),
    ):
        out = await run_no_result_recovery(
            _mock_db(),
            intent="machine_search",
            filters={"category": "excavator", "city": "jaipur", "max_price": 100},
            permission_decision={
                "permission_passed": True,
                "allowed_tool": TOOL_MONGODB_SEARCH,
                "should_search_machines": True,
            },
        )
    c.record(
        "budget recovery type",
        out.get("recovery_type") == "budget_relaxation" or out.get("auto_retried"),
        out.get("recovery_type"),
    )
    c.record("budget auto retry has machines", bool((out.get("auto_retry_results") or {}).get("machines")))


async def test_brand_alternative_mock(c: Counter) -> None:
    machines = [{"name": "E1", "category": "excavator", "brand": "JCB"}]
    with mock.patch(
        "app.utils.machine_repository.available_brands_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=["JCB", "CAT"],
    ), mock.patch(
        "app.ai.no_result_recovery._try_auto_retry",
        new_callable=mock.AsyncMock,
        return_value=(machines, "brand=None"),
    ):
        out = await run_no_result_recovery(
            _mock_db(),
            intent="machine_search",
            filters={"category": "excavator", "city": "jaipur", "brand": "UnknownBrand"},
            permission_decision={
                "permission_passed": True,
                "allowed_tool": TOOL_MONGODB_SEARCH,
                "should_search_machines": True,
            },
        )
    c.record("brand recovery auto retry", out.get("auto_retried") or out.get("recovery_type") == "brand_alternative")
    alts = out.get("safe_alternatives") or []
    c.record("brand alternatives factual", any(a.get("available_brands") for a in alts) or out.get("auto_retried"))


async def test_nearby_city_mock(c: Counter) -> None:
    machines = [{"name": "R1", "category": "road roller", "city": "delhi"}]
    with mock.patch(
        "app.utils.machine_repository.min_price_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=None,
    ), mock.patch(
        "app.utils.machine_repository.search_by_filters",
        new_callable=mock.AsyncMock,
        return_value=[],
    ), mock.patch(
        "app.utils.machine_repository.nearby_cities_with_category_listings",
        new_callable=mock.AsyncMock,
        return_value=["delhi"],
    ), mock.patch(
        "app.ai.no_result_recovery._try_auto_retry",
        new_callable=mock.AsyncMock,
        return_value=(machines, "city=delhi"),
    ):
        out = await run_no_result_recovery(
            _mock_db(),
            intent="machine_search",
            filters={"category": "road roller", "city": "jaipur"},
            permission_decision={
                "permission_passed": True,
                "allowed_tool": TOOL_MONGODB_SEARCH,
                "should_search_machines": True,
            },
        )
    c.record(
        "nearby city recovery",
        out.get("recovery_type") == "nearby_or_alternate_city" or out.get("auto_retried"),
        out.get("recovery_type"),
    )


async def test_similar_category_mock(c: Counter) -> None:
    machines = [{"name": "B1", "category": "backhoe loader", "city": "jaipur"}]
    with mock.patch(
        "app.utils.machine_repository.min_price_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=None,
    ), mock.patch(
        "app.utils.machine_repository.nearby_cities_with_category_listings",
        new_callable=mock.AsyncMock,
        return_value=[],
    ), mock.patch(
        "app.utils.machine_repository.search_by_filters",
        new_callable=mock.AsyncMock,
        return_value=machines,
    ):
        out = await run_no_result_recovery(
            _mock_db(),
            intent="machine_search",
            filters={"category": "excavator", "city": "jaipur"},
            purpose_key="digging",
            permission_decision={
                "permission_passed": True,
                "allowed_tool": TOOL_MONGODB_SEARCH,
                "should_search_machines": True,
            },
        )
    c.record(
        "similar category recovery",
        out.get("recovery_type") == "similar_category" or out.get("auto_retried"),
        out.get("recovery_type"),
    )


async def test_recovery_followup_detection(c: Counter) -> None:
    ctx = {
        "suggested_filters": [
            {"action": "drop_brand_filter", "brand": None, "category": "excavator"},
            {"action": "search_nearby_city", "city": "delhi", "category": "excavator"},
            {"action": "remove_budget_cap", "max_price": None},
        ],
        "last_no_result_filters": {"category": "excavator", "city": "jaipur"},
        "safe_alternatives": [{"type": "nearby_or_alternate_city", "nearby_cities": ["delhi"]}],
    }
    c.record("followup other brands", detect_recovery_followup("show other brands", ctx) is not None)
    c.record("followup increase budget", detect_recovery_followup("increase budget", ctx) is not None)
    c.record("followup nearby", detect_recovery_followup("try nearby city", ctx) is not None)
    same = detect_recovery_followup("same city only", ctx)
    c.record("followup same city", same is not None and same.get("nearby_allowed") is False)


async def test_recovery_state_merge(c: Counter) -> None:
    state = empty_conversation_state("p8_followup_merge")
    state["last_no_result_context"] = {
        "suggested_filters": [{"action": "drop_brand_filter", "brand": None}],
        "last_no_result_filters": {"category": "excavator", "city": "jaipur"},
    }
    state["active_flow"] = FLOW_NO_RESULT_RECOVERY
    merge_incoming_turn(state, message="show other brands")
    c.record(
        "state merge recovery followup",
        bool(state.get("_recovery_followup_filters")),
        str(state.get("_recovery_followup_filters")),
    )


async def test_recovery_context_for_state(c: Counter) -> None:
    recovery = {
        **empty_recovery_output(),
        "recovery_type": "brand_alternative",
        "suggested_filters": [{"brand": None}],
        "safe_alternatives": [{"type": "brand_alternative"}],
        "auto_retried": False,
        "auto_retry_results": {},
        "next_best_action": "show_other_brands",
        "suggestions": ["JCB", "CAT"],
    }
    ctx = recovery_context_for_state(recovery, {"category": "excavator", "city": "jaipur"})
    c.record("recovery context keys", "last_no_result_filters" in ctx and "recovery_type" in ctx)


async def test_build_recovery_draft(c: Counter) -> None:
    recovery = {
        **empty_recovery_output(),
        "recovery_type": "no_safe_recovery",
        "message_facts": {"not_found_reason": "no_exact_match"},
        "safe_alternatives": [],
    }
    draft, meta = build_recovery_draft_message(
        recovery,
        filters={"category": "excavator", "city": "jaipur"},
        lang="english",
    )
    c.record("draft message generated", bool(draft))
    c.record("draft meta has recovery_type", meta.get("recovery_type") == "no_safe_recovery")


async def test_brand_inventory_recovery_mock(c: Counter) -> None:
    with mock.patch(
        "app.utils.machine_repository.available_cities_for_category",
        new_callable=mock.AsyncMock,
        return_value=["delhi", "mumbai"],
    ):
        out = await run_brand_inventory_recovery(
            _mock_db(),
            category="excavator",
            brand=None,
            city="jaipur",
            brands_found=[],
        )
    c.record("brand inventory empty type", out.get("recovery_type") == "brand_inventory_empty")
    c.record("brand inventory suggestions", bool(out.get("suggestions")))


async def test_comparison_recovery_mock(c: Counter) -> None:
    with mock.patch(
        "app.utils.machine_repository.available_brands_for_category_city",
        new_callable=mock.AsyncMock,
        return_value=["JCB", "CAT", "Hyundai"],
    ):
        out = await run_comparison_recovery(
            _mock_db(),
            brands=["JCB", "UnknownBrand"],
            category="excavator",
            city="jaipur",
            results=[{"brand": "JCB"}],
        )
    c.record("comparison partial type", out.get("recovery_type") == "comparison_partial")
    missing = (out.get("message_facts") or {}).get("missing_brands") or []
    c.record("comparison missing brand", "UnknownBrand" in missing or bool(missing))


async def test_debug_trace_recovery_block(c: Counter) -> None:
    token = begin_chat_trace("p8_debug", "test recovery trace")
    record_recovery(
        {
            "recovery_type": "budget_relaxation",
            "auto_retried": True,
            "auto_retry_allowed": True,
            "auto_retry_results": {"count": 2, "machines": [{}, {}]},
            "safe_alternatives": [{"type": "budget_relaxation"}],
            "next_best_action": "show_relaxed_budget_results",
        },
        recovery_state_saved=True,
    )
    trace = dict(_current() or {})
    end_chat_trace(token)
    rec = trace.get("recovery") or {}
    c.record("debug recovery engine_called", rec.get("engine_called") is True)
    c.record("debug recovery type", rec.get("recovery_type") == "budget_relaxation")
    c.record("debug auto_retry_count", rec.get("auto_retry_results_count") == 2)
    c.record("debug recovery_state_saved", rec.get("recovery_state_saved") is True)


async def test_integration_no_result_search(c: Counter) -> None:
    sid = "p8_integration_noresult"
    clear_conversation(sid)
    r = await chatbot_response(
        sid,
        "excavator in Jaipur under 1",
        database,
    )
    msg = (r.get("message") or "").lower()
    data = r.get("data") or {}
    ctx = data.get("context") or {}
    mode = data.get("assistant_mode") or ctx.get("assistant_mode")
    c.record(
        "integration no dead-end",
        bool(msg) and len(msg) > 15,
        msg[:120],
    )
    c.record(
        "integration recovery context or no_result mode",
        mode in ("no_result", "search")
        or bool(ctx.get("no_result_recovery"))
        or bool(ctx.get("recovery_type"))
        or "budget" in msg
        or "jaipur" in msg,
        f"mode={mode} recovery={ctx.get('recovery_type')}",
    )


async def test_integration_support_no_recovery_search(c: Counter) -> None:
    sid = "p8_support"
    clear_conversation(sid)
    r = await chatbot_response(sid, "payment issue without transaction id", database)
    msg = (r.get("message") or "").lower()
    mode = (r.get("data") or {}).get("assistant_mode") or ""
    c.record(
        "support asks details not machine search",
        "booking" in msg or "transaction" in msg or "id" in msg or mode in ("support", "payment_issue"),
        f"mode={mode} msg={msg[:80]}",
    )


async def test_production_defaults_unchanged(c: Counter) -> None:
    from app.core.config import settings

    config_path = os.path.join(PROJECT_ROOT, "app", "core", "config.py")
    with open(config_path, encoding="utf-8") as fh:
        config_src = fh.read()
    c.record(
        "config default AI_INTENT_MODE rules_first",
        'or "rules_first"' in config_src,
    )
    c.record("runtime ENABLE_OPENAI false", not settings.ENABLE_OPENAI, str(settings.ENABLE_OPENAI))


async def main() -> int:
    c = Counter()
    print("\n=== Phase 8 — No Result Recovery Engine ===\n")

    await test_recovery_types_defined(c)
    await test_support_not_machine_recovery(c)
    await test_document_not_machine_recovery(c)
    await test_image_not_machine_recovery(c)
    await test_permission_blocks_auto_retry(c)
    await test_budget_relaxation_mock(c)
    await test_brand_alternative_mock(c)
    await test_nearby_city_mock(c)
    await test_similar_category_mock(c)
    await test_recovery_followup_detection(c)
    await test_recovery_state_merge(c)
    await test_recovery_context_for_state(c)
    await test_build_recovery_draft(c)
    await test_brand_inventory_recovery_mock(c)
    await test_comparison_recovery_mock(c)
    await test_debug_trace_recovery_block(c)
    await test_integration_no_result_search(c)
    await test_integration_support_no_recovery_search(c)
    await test_production_defaults_unchanged(c)

    print(f"\nPhase 8: {c.passed} passed, {c.failed} failed\n")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
