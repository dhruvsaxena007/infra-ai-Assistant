"""
Central Conversation State Manager — unified session state across fragmented stores.

Wraps existing persistence (last_filters, pending_clarification, recommendation_context,
session_context/response_memory) without duplicating disconnected state.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

from app.ai.query_parser import parse_query
from app.ai.response_memory import get_response_memory, record_response_memory

_STATE: ContextVar[Optional[dict[str, Any]]] = ContextVar("conversation_state", default=None)

# Flow types supported by the assistant
FLOW_IDLE = "idle"
FLOW_MACHINE_REQUIREMENT = "machine_requirement_collection"
FLOW_MACHINE_SEARCH = "machine_search"
FLOW_MACHINE_RECOMMENDATION = "machine_recommendation"
FLOW_BRAND_INVENTORY = "brand_inventory"
FLOW_MACHINE_COMPARISON = "machine_comparison"
FLOW_SEARCH_REFINEMENT = "search_refinement"
FLOW_SUPPORT = "support_issue"
FLOW_DOCUMENT_QA = "document_qa"
FLOW_IMAGE_FOLLOWUP = "image_followup"
FLOW_FRUSTRATION = "frustration_recovery"
FLOW_NO_RESULT_RECOVERY = "no_result_recovery"
FLOW_OUT_OF_SCOPE = "out_of_scope"

MACHINE_FLOWS = {
    FLOW_MACHINE_REQUIREMENT,
    FLOW_MACHINE_SEARCH,
    FLOW_MACHINE_RECOMMENDATION,
    FLOW_BRAND_INVENTORY,
    FLOW_MACHINE_COMPARISON,
    FLOW_SEARCH_REFINEMENT,
    FLOW_IMAGE_FOLLOWUP,
    FLOW_NO_RESULT_RECOVERY,
}

SUPPORT_INTENTS = {
    "payment_issue", "refund_return", "order_issue", "delivery_issue",
    "delivery_logistics", "invoice_issue", "security_deposit",
    "complaint", "support_request", "human_handover", "contact_owner",
    "platform_how_to", "general_marketplace_help", "general_help", "booking_help",
}

MACHINE_SEARCH_INTENTS = {
    "machine_search", "rent_machine", "buy_machine", "machine_availability",
    "price_query", "cheaper_option_query", "higher_budget_query",
}

REFINEMENT_INTENTS = {"cheaper_option_query", "higher_budget_query"}

COLLECTED_KEYS = (
    "category", "purpose", "city", "budget", "listing_type", "brand", "model",
    "order_id", "booking_id", "transaction_id",
)

_FILTER_TO_COLLECTED = {
    "category": "category",
    "city": "city",
    "max_price": "budget",
    "listing_type": "listing_type",
    "brand": "brand",
    "model": "model",
    "purpose_key": "purpose",
}

_COLLECTED_TO_FILTER = {v: k for k, v in _FILTER_TO_COLLECTED.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_collected_fields() -> dict[str, Any]:
    return {
        "category": None,
        "purpose": None,
        "city": None,
        "budget": None,
        "listing_type": None,
        "brand": None,
        "brands": [],
        "model": None,
        "order_id": None,
        "booking_id": None,
        "transaction_id": None,
    }


def clear_machine_search_context(state: dict[str, Any], *, reason: str = "") -> None:
    """Drop stale requirement/search fields from in-memory conversation state."""
    state["collected_fields"] = empty_collected_fields()
    state["last_search_filters"] = {}
    state["pending_fields"] = []
    state.pop("_field_provenance", None)
    state.pop("_derived_category", None)
    state["_requirement_revision"] = 0
    state["_requirement_suspended"] = False
    state["active_flow"] = FLOW_MACHINE_REQUIREMENT
    state["_context_cleared"] = True
    if reason:
        state["_context_cleared_reason"] = reason


def reset_conversation_session(session_id: str) -> dict[str, Any]:
    """Clear all assistant session memory for a session (frontend reset/clear)."""
    from app.chatbot.chatbot_service import reset_session_state

    session_id = (session_id or "").strip()
    reset_session_state(session_id)
    return empty_conversation_state(session_id)


def empty_conversation_state(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "active_flow": FLOW_IDLE,
        "last_intent": None,
        "last_action": None,
        "assistant_mode": None,
        "expected_user_reply": None,
        "pending_fields": [],
        "collected_fields": empty_collected_fields(),
        "last_search_filters": {},
        "last_user_goal": None,
        "last_recommendation_context": {},
        "last_comparison_context": {},
        "pending_clarification": None,
        "last_search_results_summary": {
            "count": 0,
            "lowest_price": None,
            "highest_price": None,
            "brands": [],
            "categories": [],
            "cities": [],
        },
        "last_brand_inventory": {},
        "last_support_context": {},
        "last_document_context": {},
        "last_image_context": {},
        "last_no_result_context": {},
        "selected_machine": {},
        "last_visible_results": [],
        "recent_intents": [],
        "recent_actions": [],
        "recent_response_signatures": [],
        "recent_user_messages_summary": [],
        "user_sentiment": "neutral",
        "language": None,
        "updated_at": _now_iso(),
        "_merge_applied": False,
        "_switch_reason": None,
    }


def _filters_to_collected(filters: dict[str, Any]) -> dict[str, Any]:
    collected = empty_collected_fields()
    for filt_key, col_key in _FILTER_TO_COLLECTED.items():
        val = filters.get(filt_key)
        if val is not None and val != "":
            collected[col_key] = val
    if filters.get("brand"):
        collected["brands"] = [str(filters["brand"])]
    return collected


def _collected_to_filters(collected: dict[str, Any]) -> dict[str, Any]:
    from app.chatbot.chatbot_service import _DEFAULT_FILTERS

    merged = dict(_DEFAULT_FILTERS)
    for col_key, filt_key in _COLLECTED_TO_FILTER.items():
        val = collected.get(col_key)
        if val is not None and val != "":
            merged[filt_key] = val
    brands = collected.get("brands") or []
    if brands and not merged.get("brand"):
        merged["brand"] = brands[0]
    return merged


def _derive_active_flow(
    pending: dict | None,
    mem: dict,
    stored_flow: str | None,
    last_intent: str | None,
) -> str:
    if stored_flow and stored_flow != FLOW_IDLE:
        return stored_flow
    if pending:
        ptype = pending.get("type") or pending.get("missing_field") or ""
        if ptype in ("machine_purpose", "broad_machine_request", "purpose"):
            return FLOW_MACHINE_REQUIREMENT
        if ptype == "project_type":
            return FLOW_MACHINE_RECOMMENDATION
        if pending.get("source") == "support":
            return FLOW_SUPPORT
        return FLOW_MACHINE_REQUIREMENT
    if last_intent in SUPPORT_INTENTS:
        return FLOW_SUPPORT
    if last_intent in ("machine_brand_query",):
        return FLOW_BRAND_INVENTORY
    if last_intent in ("machine_comparison", "compare_machine"):
        return FLOW_MACHINE_COMPARISON
    if last_intent in MACHINE_SEARCH_INTENTS:
        return FLOW_MACHINE_SEARCH
    if last_intent == "machine_recommendation":
        return FLOW_MACHINE_RECOMMENDATION
    if last_intent == "frustration":
        return FLOW_FRUSTRATION
    if last_intent == "document_question":
        return FLOW_DOCUMENT_QA
    if mem.get("last_support_issue"):
        return FLOW_SUPPORT
    return FLOW_IDLE


def _pending_fields_from_pending(pending: dict | None, mem: dict) -> list[str]:
    fields: list[str] = []
    if pending:
        missing = pending.get("missing")
        if isinstance(missing, list):
            fields.extend(missing)
        mf = pending.get("missing_field")
        if mf:
            mapped = {
                "machine_purpose": "purpose_or_category",
                "purpose": "purpose_or_category",
                "project_type": "work_type_or_purpose",
                "city": "city",
                "category": "category",
            }.get(mf, mf)
            if mapped not in fields:
                fields.insert(0, mapped)
    mem_pending = mem.get("pending_fields") or []
    for f in mem_pending:
        if f not in fields:
            fields.append(f)
    return fields


def _build_results_summary(machines: list[dict], filters: dict | None = None) -> dict[str, Any]:
    prices = []
    brands: set[str] = set()
    categories: set[str] = set()
    cities: set[str] = set()
    for m in machines or []:
        p = m.get("price_per_day") or m.get("price")
        if p is not None:
            try:
                prices.append(float(p))
            except (TypeError, ValueError):
                pass
        if m.get("brand"):
            brands.add(str(m["brand"]))
        if m.get("category"):
            categories.add(str(m["category"]))
        if m.get("city"):
            cities.add(str(m["city"]))
    if filters:
        if filters.get("category"):
            categories.add(str(filters["category"]))
        if filters.get("city"):
            cities.add(str(filters["city"]))
        if filters.get("brand"):
            brands.add(str(filters["brand"]))
    return {
        "count": len(machines or []),
        "lowest_price": min(prices) if prices else None,
        "highest_price": max(prices) if prices else None,
        "brands": sorted(brands, key=str.lower),
        "categories": sorted(categories, key=str.lower),
        "cities": sorted(cities, key=str.lower),
    }


def load_conversation_state(session_id: str) -> dict[str, Any]:
    """Assemble unified state from existing session stores."""
    from app.ai.conversation_context import get_result_context
    from app.chatbot.chatbot_service import (
        _get_last_filters,
        _get_pending_clarification,
        _get_recommendation_context,
        _get_session_context,
    )
    from app.chatbot.image_context_memory import get_image_context

    session_id = (session_id or "").strip()
    state = empty_conversation_state(session_id)
    session_ctx = _get_session_context(session_id)
    last_filters = _get_last_filters(session_id)
    pending = _get_pending_clarification(session_id)
    rec_ctx = _get_recommendation_context(session_id) or {}
    mem = get_response_memory(session_ctx)
    stored = dict(session_ctx.get("conversation_state") or {})
    result_ctx = get_result_context(session_ctx)

    collected = _filters_to_collected(last_filters)
    if rec_ctx.get("purpose_key"):
        collected["purpose"] = rec_ctx["purpose_key"]
    if pending and pending.get("purpose_key"):
        collected["purpose"] = pending["purpose_key"]
    if pending and pending.get("category") and not collected.get("category"):
        collected["category"] = pending["category"]
    if pending and pending.get("city") and not collected.get("city"):
        collected["city"] = pending["city"]

    state["collected_fields"] = collected
    state["last_search_filters"] = {
        k: v for k, v in (last_filters or {}).items() if v is not None
    }
    state["pending_fields"] = _pending_fields_from_pending(pending, mem)
    state["last_intent"] = stored.get("last_intent") or (
        (mem.get("recent_intents") or [None])[-1]
    )
    state["last_action"] = stored.get("last_action")
    state["assistant_mode"] = stored.get("assistant_mode")
    state["expected_user_reply"] = stored.get("expected_user_reply")
    state["active_flow"] = _derive_active_flow(
        pending, mem, stored.get("active_flow"), state["last_intent"],
    )
    state["recent_intents"] = list(mem.get("recent_intents") or stored.get("recent_intents") or [])[-12:]
    state["recent_actions"] = list(stored.get("recent_actions") or [])[-12:]
    state["recent_response_signatures"] = list(
        mem.get("recent_response_signatures") or stored.get("recent_response_signatures") or []
    )[-12:]
    state["recent_user_messages_summary"] = list(
        mem.get("recent_messages_summary") or stored.get("recent_user_messages_summary") or []
    )[-12:]
    state["user_sentiment"] = stored.get("user_sentiment") or "neutral"
    state["language"] = mem.get("preferred_language") or stored.get("language")

    machines = result_ctx.get("last_machines") or []
    rf = result_ctx.get("filters") or last_filters
    if machines or rf:
        state["last_search_results_summary"] = _build_results_summary(machines, rf)

    state["last_brand_inventory"] = dict(stored.get("last_brand_inventory") or {})
    state["last_comparison_context"] = dict(stored.get("last_comparison_context") or {})
    state["selected_machine"] = dict(stored.get("selected_machine") or session_ctx.get("selected_machine") or {})
    state["last_visible_results"] = list(stored.get("last_visible_results") or result_ctx.get("last_machines") or [])
    state["last_support_context"] = dict(stored.get("last_support_context") or mem.get("last_support_issue") or {})
    state["last_document_context"] = dict(stored.get("last_document_context") or {})
    img = get_image_context(session_id)
    if img:
        state["last_image_context"] = dict(img)
    else:
        state["last_image_context"] = dict(stored.get("last_image_context") or {})

    state["updated_at"] = stored.get("updated_at") or _now_iso()
    return state


def save_conversation_state(state: dict[str, Any]) -> None:
    """Persist unified state back into existing fragmented stores."""
    from app.chatbot.chatbot_service import (
        _get_session_context,
        _save_last_filters,
        _save_pending_clarification,
        _save_recommendation_context,
        _save_session_context,
    )

    session_id = state.get("session_id") or ""
    if not session_id:
        return

    try:
        from app.chatbot.chatbot_service import _get_last_filters as _glf
        live = _glf(session_id)
        if live:
            clean_live = {k: v for k, v in live.items() if v is not None}
            if clean_live:
                state["last_search_filters"] = {
                    **state.get("last_search_filters", {}),
                    **clean_live,
                }
    except Exception:
        pass

    filters = _collected_to_filters(state.get("collected_fields") or {})
    last_sf = state.get("last_search_filters") or {}
    for key in ("category", "city", "max_price", "brand", "model", "listing_type", "rent_type", "region"):
        if last_sf.get(key) is not None and filters.get(key) is None:
            filters[key] = last_sf[key]
    if state.get("active_flow") in (FLOW_MACHINE_SEARCH, FLOW_SEARCH_REFINEMENT) and last_sf:
        for key, val in last_sf.items():
            if val is not None:
                filters[key] = val

    _save_last_filters(session_id, filters)

    pending = _state_to_pending_clarification(state)
    _save_pending_clarification(session_id, pending)

    rec_ctx = None
    purpose = (state.get("collected_fields") or {}).get("purpose")
    if state.get("active_flow") == FLOW_MACHINE_RECOMMENDATION:
        rec_ctx = {
            "purpose_key": purpose,
            "awaiting_project_type": "work_type_or_purpose" in (state.get("pending_fields") or []),
        }
    if state.get("active_flow") == FLOW_MACHINE_RECOMMENDATION and rec_ctx:
        _save_recommendation_context(session_id, rec_ctx)

    session_ctx = _get_session_context(session_id)
    blob = {
        "active_flow": state.get("active_flow"),
        "last_intent": state.get("last_intent"),
        "last_action": state.get("last_action"),
        "assistant_mode": state.get("assistant_mode"),
        "expected_user_reply": state.get("expected_user_reply"),
        "pending_fields": state.get("pending_fields"),
        "last_brand_inventory": state.get("last_brand_inventory"),
        "last_comparison_context": state.get("last_comparison_context"),
        "selected_machine": state.get("selected_machine"),
        "last_visible_results": state.get("last_visible_results"),
        "last_support_context": state.get("last_support_context"),
        "last_document_context": state.get("last_document_context"),
        "last_image_context": state.get("last_image_context"),
        "recent_actions": state.get("recent_actions"),
        "recent_intents": state.get("recent_intents"),
        "recent_response_signatures": state.get("recent_response_signatures"),
        "recent_user_messages_summary": state.get("recent_user_messages_summary"),
        "user_sentiment": state.get("user_sentiment"),
        "language": state.get("language"),
        "updated_at": _now_iso(),
    }
    session_ctx["conversation_state"] = blob
    mem_update = record_response_memory(
        session_ctx,
        intent=str(state.get("last_intent") or ""),
        response_goal=str(state.get("expected_user_reply") or ""),
        message="",
        pending_fields=state.get("pending_fields"),
        machine_search=state.get("last_search_filters") or None,
        support_issue=state.get("last_support_context") or None,
        language=state.get("language"),
    )
    _save_session_context(session_id, mem_update)
    state["updated_at"] = blob["updated_at"]


def _state_to_pending_clarification(state: dict[str, Any]) -> dict | None:
    pending_fields = list(state.get("pending_fields") or [])
    if not pending_fields and state.get("active_flow") not in (
        FLOW_MACHINE_REQUIREMENT, FLOW_MACHINE_RECOMMENDATION, FLOW_SUPPORT,
    ):
        return None

    collected = state.get("collected_fields") or {}
    flow = state.get("active_flow")

    if flow == FLOW_SUPPORT:
        return {
            "type": "support",
            "missing_field": "booking_id_or_transaction_id",
            "missing": pending_fields or ["booking_id_or_transaction_id"],
            "source": "support",
            **{k: collected.get(k) for k in ("order_id", "booking_id", "transaction_id") if collected.get(k)},
        }

    if flow == FLOW_MACHINE_RECOMMENDATION:
        return {
            "missing_field": "project_type",
            "type": "project_type",
            "missing": pending_fields or ["work_type_or_purpose", "city"],
            "source": "machine_recommendation",
            "purpose_key": collected.get("purpose"),
            "city": collected.get("city"),
        }

    if pending_fields or flow == FLOW_MACHINE_REQUIREMENT:
        from app.ai.requirement_state_engine import (
            pending_clarification_from_requirement,
            requirement_state_from_conversation,
        )
        req = requirement_state_from_conversation(state)
        pc = pending_clarification_from_requirement(req)
        if pc:
            return pc
        return {
            "missing_field": "machine_purpose" if "purpose_or_category" in pending_fields else (pending_fields[0] if pending_fields else "machine_purpose"),
            "type": "machine_purpose",
            "missing": pending_fields or ["purpose_or_category", "city"],
            "source": "broad_machine_request",
            "purpose_key": collected.get("purpose"),
            "category": collected.get("category"),
            "city": collected.get("city"),
        }
    return None


def detect_flow_switch(state: dict[str, Any], intent: str) -> tuple[str, str | None]:
    """Return (new_active_flow, switch_reason) when topic changes."""
    current = state.get("active_flow") or FLOW_IDLE
    intent = (intent or "").lower()

    if intent in SUPPORT_INTENTS and current in MACHINE_FLOWS:
        return FLOW_SUPPORT, "topic_switch_to_support"

    if intent in MACHINE_SEARCH_INTENTS and current == FLOW_SUPPORT:
        collected = state.get("collected_fields") or {}
        if collected.get("category") or collected.get("city"):
            return FLOW_MACHINE_SEARCH, "topic_switch_to_search"

    if intent == "out_of_scope":
        return FLOW_OUT_OF_SCOPE, "topic_switch_out_of_scope"

    if intent == "frustration":
        return FLOW_FRUSTRATION, "frustration_detected"

    if intent == "machine_brand_query":
        return FLOW_BRAND_INVENTORY, None

    if intent in ("machine_comparison", "compare_machine"):
        return FLOW_MACHINE_COMPARISON, None

    if intent in REFINEMENT_INTENTS and state.get("last_search_filters"):
        return FLOW_SEARCH_REFINEMENT, None

    if intent in MACHINE_SEARCH_INTENTS:
        return FLOW_MACHINE_SEARCH, None

    if intent == "machine_recommendation":
        return FLOW_MACHINE_RECOMMENDATION, None

    if intent == "broad_machine_request":
        return FLOW_MACHINE_REQUIREMENT, None

    if intent == "document_question":
        return FLOW_DOCUMENT_QA, None

    if intent in ("image_followup", "image_search_followup", "image_context_followup"):
        return FLOW_IMAGE_FOLLOWUP, None

    return current, None


def _apply_pending_field_answer(
    state: dict[str, Any],
    message: str,
    parsed: dict[str, Any],
) -> bool:
    """Merge support clarification answers; machine requirements use canonical engine."""
    if state.get("active_flow") == FLOW_SUPPORT:
        pending_fields = list(state.get("pending_fields") or [])
        if "booking_id_or_transaction_id" in pending_fields:
            collected = dict(state.get("collected_fields") or empty_collected_fields())
            txn = _extract_transaction_id(message)
            if txn:
                if txn.upper().startswith("TXN") or "transaction" in message.lower():
                    collected["transaction_id"] = txn
                else:
                    collected["booking_id"] = txn
                pending_fields = [f for f in pending_fields if f != "booking_id_or_transaction_id"]
                state["collected_fields"] = collected
                state["pending_fields"] = pending_fields
                state["_merge_applied"] = True
                return True
    return False


def _extract_transaction_id(message: str) -> str | None:
    m = re.search(r"\b(?:txn|transaction\s*id|booking\s*id|order\s*id)\s*(?:is\s*)?([A-Za-z0-9_-]{4,})\b", message, re.I)
    if m:
        return m.group(1)
    m2 = re.search(r"\b(TXN[A-Za-z0-9]+)\b", message, re.I)
    return m2.group(1) if m2 else None


def _remove_satisfied_pending(state: dict[str, Any], parsed: dict, message: str) -> None:
    collected = state.get("collected_fields") or {}
    pending = list(state.get("pending_fields") or [])
    if collected.get("purpose") or collected.get("category"):
        pending = [f for f in pending if f not in ("purpose_or_category", "work_type_or_purpose")]
    if collected.get("city"):
        pending = [f for f in pending if f != "city"]
    state["pending_fields"] = pending


def establish_requirement_collection(
    state: dict[str, Any],
    *,
    parsed: dict[str, Any],
    message: str = "",
) -> bool:
    """Set active_flow and pending_fields when city-only or category-only is detected."""
    from app.chatbot.image_context_memory import get_image_context

    sid = (state.get("session_id") or "").strip()
    if sid:
        img = get_image_context(sid)
        if img and (
            img.get("awaiting_image_choice")
            or img.get("pending_image_intent")
            or img.get("awaiting_image_field")
        ):
            return False

    from app.ai.context_routing_gate import get_current_gate

    gate = get_current_gate() or {}
    if gate.get("family") in (
        "frustration_or_abuse",
        "return_refund_or_booking_problem",
        "support_or_issue",
        "document_question",
        "image_followup",
        "conversational",
    ):
        return False

    flow = state.get("active_flow") or FLOW_IDLE
    if flow in (FLOW_SUPPORT, FLOW_FRUSTRATION, FLOW_DOCUMENT_QA, FLOW_OUT_OF_SCOPE):
        return False

    collected = dict(state.get("collected_fields") or empty_collected_fields())
    city = collected.get("city") or parsed.get("city")
    cat = collected.get("category") or parsed.get("category")
    purpose = collected.get("purpose")

    has_machine_signal = bool(
        re.search(r"\b(?:machine|equipment|machinery|saman|rent|buy|hire|chahiye)\b", message, re.I)
        or city
        or cat
    )
    if not has_machine_signal:
        return False

    if city and not cat and not purpose:
        state["active_flow"] = FLOW_MACHINE_REQUIREMENT
        state["pending_fields"] = ["purpose_or_category"]
        state["collected_fields"] = {**collected, "city": city}
        sf = dict(state.get("last_search_filters") or {})
        sf["city"] = city
        state["last_search_filters"] = sf
        state["_merge_applied"] = True
        return True

    if cat and not city:
        state["active_flow"] = FLOW_MACHINE_REQUIREMENT
        state["pending_fields"] = ["city"]
        state["collected_fields"] = {**collected, "category": cat}
        sf = dict(state.get("last_search_filters") or {})
        sf["category"] = cat
        state["last_search_filters"] = sf
        state["_merge_applied"] = True
        return True

    return False


def _apply_refinement_merge(state: dict[str, Any], intent: str, parsed: dict, entities: dict) -> None:
    """Reuse last search context for follow-up refinements."""
    if intent not in REFINEMENT_INTENTS and intent not in (
        "machine_search", "machine_brand_query", "machine_availability", "price_query",
    ):
        return

    last_sf = state.get("last_search_filters") or {}
    if not last_sf:
        return

    is_refinement = intent in REFINEMENT_INTENTS or (
        not parsed.get("category") and not parsed.get("city") and bool(last_sf)
    )
    if not is_refinement:
        return

    collected = dict(state.get("collected_fields") or empty_collected_fields())
    for filt_key, col_key in _FILTER_TO_COLLECTED.items():
        if last_sf.get(filt_key) is not None and not collected.get(col_key):
            collected[col_key] = last_sf[filt_key]
    if last_sf.get("brand") and not collected.get("brand"):
        collected["brand"] = last_sf["brand"]
        collected["brands"] = [last_sf["brand"]]

    if entities.get("brand") or (entities.get("brands") or [None])[0]:
        brand = entities.get("brand") or (entities.get("brands") or [None])[0]
        collected["brand"] = brand
        collected["brands"] = [brand]

    if parsed.get("listing_type"):
        collected["listing_type"] = parsed["listing_type"]

    state["collected_fields"] = collected
    state["_merge_applied"] = True


def apply_canonical_requirement_merge(
    state: dict[str, Any],
    *,
    message: str,
    parsed: dict[str, Any],
    entities: dict[str, Any] | None = None,
    intent: str | None = None,
    intent_family: str | None = None,
    block_previous_context: bool = False,
    permission_passed: bool = True,
) -> Any:
    """
    Single canonical requirement state transition for this turn.
    Writes collected_fields, pending_fields, last_search_filters from engine output.
    """
    from app.ai.requirement_state_engine import (
        RequirementTransitionDecision,
        apply_requirement_transition,
        pending_clarification_from_requirement,
        requirement_state_from_conversation,
        sync_requirement_to_conversation,
    )
    from app.chatbot.chatbot_service import _get_pending_clarification, _save_pending_clarification

    if not intent_family:
        from app.ai.context_routing_gate import get_current_gate
        gate = get_current_gate() or {}
        intent_family = gate.get("family")

    req = requirement_state_from_conversation(state)
    session_id = state.get("session_id") or ""
    pending = _get_pending_clarification(session_id)

    decision = apply_requirement_transition(
        req,
        message=message,
        parsed=parsed,
        entities=entities or {},
        intent=intent,
        intent_family=intent_family,
        pending_clarification=pending,
        active_flow=state.get("active_flow"),
        profile_hints=state.get("user_profile_hints") or {},
        block_previous_context=block_previous_context,
        permission_passed=permission_passed,
    )

    sync_requirement_to_conversation(state, req, decision=decision)

    if decision.requirements_complete and decision.search_triggered:
        _save_pending_clarification(session_id, None)
    elif decision.next_missing_field:
        pc = pending_clarification_from_requirement(req, next_field=decision.next_missing_field)
        if pc:
            _save_pending_clarification(session_id, pc)
    elif not req.get("pending_fields"):
        _save_pending_clarification(session_id, None)

    try:
        from app.ai.assistant_debug_trace import record_context_routing, record_requirement_transition
        from app.ai.intent_signals import current_message_requirement_entities

        record_context_routing({
            "current_message_entities": current_message_requirement_entities(
                message, parsed, entities or {},
            ),
            "previous_filters": dict(state.get("last_search_filters") or {}),
            "context_reuse_allowed": not block_previous_context,
            "final_filters": dict(decision.search_filters or {}),
        })
        record_requirement_transition(decision)
    except Exception:
        pass

    state["_requirement_decision"] = decision
    state["_merge_applied"] = True
    return decision


def merge_incoming_turn(
    state: dict[str, Any],
    *,
    message: str,
    parsed: dict[str, Any] | None = None,
    entities: dict[str, Any] | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    """Merge current message entities into conversation state."""
    parsed = parsed or parse_query(message)
    entities = entities or {}

    from app.ai.context_routing_gate import get_current_gate
    from app.ai.intent_signals import is_fresh_broad_machine_intent
    from app.ai.session_requirement_context import enrich_parsed_from_session

    gate = get_current_gate() or {}
    block_ctx = bool(gate.get("block_previous_search_context"))
    fresh_broad = is_fresh_broad_machine_intent(message, parsed, entities)
    allow_session_enrich = not block_ctx and not fresh_broad

    if block_ctx or fresh_broad:
        clear_reason = "fresh_broad_machine_intent" if fresh_broad else (gate.get("reason") or "block_previous_context")
        clear_machine_search_context(state, reason=clear_reason)

    parsed = enrich_parsed_from_session(
        message,
        parsed,
        last_filters=state.get("last_search_filters") or {},
        session_collected=state.get("collected_fields") or {},
        allow_session_enrich=allow_session_enrich,
    )

    from app.ai.semantic_turn_gateway import is_short_context_fragment, resolve_fragment_context

    if allow_session_enrich and is_short_context_fragment(message, parsed=parsed):
        frag = resolve_fragment_context(
            message,
            conv_state=state,
            last_filters=state.get("last_search_filters") or {},
            parsed=parsed,
        )
        parsed = frag["parsed"]
        if frag.get("merged_from_session"):
            state["_fragment_merge"] = frag["context_reference"]
            state["_merge_applied"] = True

    recovery_ctx = state.get("last_no_result_context") or {}
    if recovery_ctx or state.get("active_flow") == FLOW_NO_RESULT_RECOVERY:
        from app.ai.no_result_recovery import detect_recovery_followup

        follow = detect_recovery_followup(message, recovery_ctx)
        if follow:
            state["_recovery_followup_filters"] = follow
            state["_merge_applied"] = True

    if state.get("active_flow") == FLOW_SUPPORT:
        txn = _extract_transaction_id(message)
        if txn:
            collected = dict(state.get("collected_fields") or empty_collected_fields())
            if txn.upper().startswith("TXN") or "transaction" in message.lower():
                collected["transaction_id"] = txn
            else:
                collected["booking_id"] = txn
            state["collected_fields"] = collected
            sup = dict(state.get("last_support_context") or {})
            if collected.get("transaction_id"):
                sup["transaction_id"] = collected["transaction_id"]
            if collected.get("booking_id"):
                sup["booking_id"] = collected["booking_id"]
            state["last_support_context"] = sup
            pending = [f for f in (state.get("pending_fields") or []) if f != "booking_id_or_transaction_id"]
            state["pending_fields"] = pending
            state["_merge_applied"] = True

    _apply_pending_field_answer(state, message, parsed)

    # Support / booking fields only — machine requirements use canonical engine below
    collected = dict(state.get("collected_fields") or empty_collected_fields())
    if state.get("active_flow") == FLOW_SUPPORT:
        ent_cat = entities.get("category") or entities.get("machine_type")
        if ent_cat:
            collected["category"] = ent_cat
        if entities.get("order_id"):
            collected["order_id"] = entities["order_id"]
        state["collected_fields"] = collected

    # Reuse brand inventory / comparison context for follow-ups (session context tier C)
    inv = state.get("last_brand_inventory") or {}
    if inv.get("category") and not collected.get("category"):
        from app.ai.context_routing_gate import get_current_gate

        gate = get_current_gate() or {}
        if not gate.get("block_previous_search_context"):
            if parsed.get("brand") or intent in ("machine_brand_query", "machine_search") or re.search(
                r"\b(?:dikhao|show|available|ka\s+hai)\b", message, re.I,
            ):
                collected["category"] = inv["category"]
    if inv.get("city") and not collected.get("city") and re.search(
        r"\b(?:in|me|mai)\b", message, re.I,
    ):
        collected["city"] = inv["city"]

    if parsed.get("brand") and inv.get("category"):
        collected["brand"] = parsed["brand"]
        collected["brands"] = [parsed["brand"]]
        if not collected.get("category"):
            collected["category"] = inv["category"]
        state["_merge_applied"] = True
    elif parsed.get("brand") and collected.get("category"):
        collected["brand"] = parsed["brand"]
        collected["brands"] = [parsed["brand"]]
        state["_merge_applied"] = True

    cmp_ctx = state.get("last_comparison_context") or {}
    from app.ai.context_routing_gate import get_current_gate

    gate = get_current_gate() or {}
    cmp_allowed = not gate.get("block_previous_search_context") or (gate.get("family") == "machine_comparison")
    if cmp_allowed:
        if cmp_ctx.get("category") and not collected.get("category"):
            if intent in ("machine_comparison", "machine_search", "cheaper_option_query", "higher_budget_query"):
                collected["category"] = cmp_ctx["category"]
        if cmp_ctx.get("city") and not collected.get("city"):
            collected["city"] = cmp_ctx.get("city")
        if cmp_ctx.get("brands") and not collected.get("brands"):
            if intent in ("machine_comparison", "machine_search"):
                collected["brands"] = cmp_ctx["brands"]

    state["collected_fields"] = collected

    from app.ai.context_routing_gate import get_current_gate
    gate = get_current_gate() or {}
    block_ctx = bool(gate.get("block_previous_search_context"))

    from app.ai.social_turn_detector import detect_social_turn

    social_ctx = {
        "last_filters": state.get("last_search_filters") or {},
        "collected_fields": state.get("collected_fields") or {},
        "conversation_state": state,
        "greeted": bool(state.get("greeted")),
    }
    is_social_turn = gate.get("family") == "conversational" or detect_social_turn(
        message, social_ctx,
    ) is not None

    if is_social_turn:
        state["_is_social_turn"] = True
        state.pop("_requirement_decision", None)
    else:
        state.pop("_is_social_turn", None)

    if intent:
        new_flow, switch_reason = detect_flow_switch(state, intent)
        if switch_reason and new_flow in (FLOW_SUPPORT, FLOW_FRUSTRATION, FLOW_DOCUMENT_QA):
            from app.ai.context_routing_gate import isolate_context_on_flow_switch
            isolate_context_on_flow_switch(state, new_flow, switch_reason=switch_reason)
        state["active_flow"] = new_flow
        if switch_reason:
            state["_switch_reason"] = switch_reason
        _apply_refinement_merge(state, intent, parsed, entities)
    elif not is_social_turn:
        establish_requirement_collection(state, parsed=parsed, message=message)

    # Canonical requirement transition — single writer for machine requirement fields
    if (
        not is_social_turn
        and state.get("active_flow") not in (FLOW_SUPPORT, FLOW_FRUSTRATION, FLOW_DOCUMENT_QA, FLOW_OUT_OF_SCOPE)
    ):
        apply_canonical_requirement_merge(
            state,
            message=message,
            parsed=parsed,
            entities=entities,
            intent=intent,
            intent_family=gate.get("family"),
            block_previous_context=block_ctx,
        )

    return state


def state_to_router_context(state: dict[str, Any]) -> dict[str, Any]:
    """Build router/classifier context from conversation state."""
    collected = state.get("collected_fields") or {}
    last_sf = dict(state.get("last_search_filters") or {})
    for col_key, filt_key in _COLLECTED_TO_FILTER.items():
        if collected.get(col_key) is not None and last_sf.get(filt_key) is None:
            last_sf[filt_key] = collected[col_key]
    if collected.get("brand") and not last_sf.get("brand"):
        last_sf["brand"] = collected["brand"]

    from app.chatbot.chatbot_service import _get_pending_clarification

    session_id = state.get("session_id") or ""
    pending = _get_pending_clarification(session_id)
    if not pending and state.get("pending_fields"):
        pending = _state_to_pending_clarification(state)

    return {
        "last_filters": last_sf,
        "collected_fields": collected,
        "pending_fields": state.get("pending_fields") or [],
        "active_flow": state.get("active_flow"),
        "last_search_filters": state.get("last_search_filters") or {},
        "last_search_results_summary": state.get("last_search_results_summary") or {},
        "last_brand_inventory": state.get("last_brand_inventory") or {},
        "last_comparison_context": state.get("last_comparison_context") or {},
        "last_support_context": state.get("last_support_context") or {},
        "last_no_result_context": state.get("last_no_result_context") or {},
        "recovery_followup_filters": state.get("_recovery_followup_filters"),
        "user_profile_hints": state.get("user_profile_hints") or {},
        "selected_machine": state.get("selected_machine") or {},
        "pending": pending,
        "conversation_state": state,
    }


def apply_turn_result(
    state: dict[str, Any],
    *,
    user_message: str,
    response: dict[str, Any],
    intent: str | None = None,
    action_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update state from completed turn response."""
    data = response.get("data") or {}
    ctx = data.get("context") or {}
    intent = intent or ctx.get("intent") or state.get("last_intent")
    action_decision = action_decision or {}

    ctx_entities = ctx.get("entities") or {}
    if ctx_entities:
        collected = dict(state.get("collected_fields") or empty_collected_fields())
        cat = ctx_entities.get("category") or ctx_entities.get("machine_type")
        if cat:
            collected["category"] = cat
        if ctx_entities.get("city"):
            collected["city"] = ctx_entities["city"]
        if ctx_entities.get("brand"):
            collected["brand"] = ctx_entities["brand"]
            collected["brands"] = [ctx_entities["brand"]]
        state["collected_fields"] = collected

    state["last_intent"] = intent
    state["last_action"] = action_decision.get("selected_action") or ctx.get("selected_action")
    state["assistant_mode"] = (
        data.get("assistant_mode") or ctx.get("assistant_mode") or action_decision.get("assistant_mode")
    )
    state["language"] = state.get("language") or ctx.get("reply_language")

    summary = re.sub(r"\s+", " ", (user_message or "").strip())[:80]
    for key, val in (("recent_intents", intent), ("recent_user_messages_summary", summary)):
        items = list(state.get(key) or [])
        if val:
            items.append(val)
        state[key] = items[-12:]

    action = state.get("last_action")
    if action:
        actions = list(state.get("recent_actions") or [])
        actions.append(action)
        state["recent_actions"] = actions[-12:]

    machines = data.get("machines") or []
    filters = data.get("filters") or {}
    if machines:
        state["last_visible_results"] = machines[:12]
    if machines or filters:
        sf = {k: v for k, v in filters.items() if v is not None}
        ctx_filters = ctx.get("filters") or {}
        for k in ("purpose_key", "brand", "listing_type"):
            if ctx_filters.get(k) is not None:
                sf[k] = ctx_filters[k]
        state["last_search_filters"] = sf
        state["collected_fields"] = {
            **(state.get("collected_fields") or empty_collected_fields()),
            **_filters_to_collected(sf),
        }
        state["last_search_results_summary"] = _build_results_summary(machines, sf)
        if intent not in REFINEMENT_INTENTS:
            state["active_flow"] = FLOW_MACHINE_SEARCH
        else:
            state["active_flow"] = FLOW_SEARCH_REFINEMENT

    pending_ctx = ctx.get("pending_clarification")
    if pending_ctx:
        state["pending_fields"] = list(pending_ctx.get("missing") or [])
        mf = pending_ctx.get("missing_field")
        if mf:
            mapped = {
                "machine_purpose": "purpose_or_category",
                "project_type": "work_type_or_purpose",
                "city": "city",
            }.get(mf, mf)
            if mapped not in state["pending_fields"]:
                state["pending_fields"].insert(0, mapped)
        state["expected_user_reply"] = mf or (state["pending_fields"][0] if state["pending_fields"] else None)
        if state["active_flow"] == FLOW_IDLE:
            state["active_flow"] = FLOW_MACHINE_REQUIREMENT
        collected = dict(state.get("collected_fields") or empty_collected_fields())
        if pending_ctx.get("purpose_key"):
            collected["purpose"] = pending_ctx["purpose_key"]
        if pending_ctx.get("category"):
            collected["category"] = pending_ctx["category"]
        if pending_ctx.get("city"):
            collected["city"] = pending_ctx["city"]
        state["collected_fields"] = collected

    amode = data.get("assistant_mode") or ctx.get("assistant_mode") or ""
    if (
        intent == "machine_brand_query"
        or amode == "brand_inventory"
        or action_decision.get("assistant_mode") == "brand_inventory"
        or state.get("active_flow") == FLOW_BRAND_INVENTORY
    ):
        inv = dict(state.get("last_brand_inventory") or {})
        collected = state.get("collected_fields") or {}
        inv["category"] = collected.get("category") or inv.get("category") or (state.get("last_search_filters") or {}).get("category")
        inv["brand"] = collected.get("brand") or inv.get("brand")
        inv["city"] = collected.get("city") or inv.get("city")
        extra = ctx.get("brands") or data.get("brands") or (ctx.get("action_decision") or {}).get("brands")
        if isinstance(extra, list) and extra:
            inv["brands_returned"] = extra
        state["last_brand_inventory"] = inv
        state["active_flow"] = FLOW_BRAND_INVENTORY
        state["expected_user_reply"] = "brand_selection_or_city"

    if intent in ("machine_comparison", "compare_machine"):
        cmp_ctx = dict(state.get("last_comparison_context") or {})
        collected = state.get("collected_fields") or {}
        cmp_ctx["category"] = collected.get("category") or cmp_ctx.get("category")
        cmp_ctx["brands"] = collected.get("brands") or cmp_ctx.get("brands") or []
        cmp_ctx["city"] = collected.get("city") or cmp_ctx.get("city")
        cmp_ctx["purpose"] = collected.get("purpose") or cmp_ctx.get("purpose")
        ctx_brands = ctx_entities.get("brands")
        if isinstance(ctx_brands, list) and ctx_brands:
            cmp_ctx["brands"] = ctx_brands
        state["last_comparison_context"] = cmp_ctx
        state["active_flow"] = FLOW_MACHINE_COMPARISON
        if not state.get("pending_fields"):
            missing_cmp = []
            if not cmp_ctx.get("category") and not collected.get("purpose"):
                missing_cmp.append("purpose_or_category")
            if len(cmp_ctx.get("brands") or []) < 2:
                missing_cmp.append("comparison_items")
            if missing_cmp:
                state["pending_fields"] = missing_cmp

    recovery_ctx = ctx.get("no_result_recovery") or data.get("recovery_context")
    if recovery_ctx or amode == "no_result":
        if recovery_ctx:
            state["last_no_result_context"] = recovery_ctx
            state["active_flow"] = FLOW_NO_RESULT_RECOVERY
            state["expected_user_reply"] = recovery_ctx.get("next_best_action")
        elif amode == "no_result" and not state.get("last_no_result_context"):
            state["active_flow"] = FLOW_NO_RESULT_RECOVERY

    if intent in SUPPORT_INTENTS:
        sup = dict(state.get("last_support_context") or {})
        sup["issue_type"] = intent
        collected = state.get("collected_fields") or {}
        for k in ("order_id", "booking_id", "transaction_id"):
            if collected.get(k):
                sup[k] = collected[k]
        state["last_support_context"] = sup
        state["active_flow"] = FLOW_SUPPORT
        if not sup.get("transaction_id") and not sup.get("booking_id"):
            state["pending_fields"] = list(dict.fromkeys(
                (state.get("pending_fields") or []) + ["booking_id_or_transaction_id"]
            ))
            state["expected_user_reply"] = "booking_id_or_transaction_id"

    if intent == "frustration":
        state["user_sentiment"] = "frustrated"
        state["active_flow"] = FLOW_FRUSTRATION

    sig = ctx.get("response_signature")
    if sig:
        sigs = list(state.get("recent_response_signatures") or [])
        sigs.append(sig)
        state["recent_response_signatures"] = sigs[-12:]

    state["updated_at"] = _now_iso()
    return state


# ---------------------------------------------------------------------------
# Per-request context (ContextVar)
# ---------------------------------------------------------------------------

def set_current_state(state: dict[str, Any]) -> Any:
    return _STATE.set(state)


def get_current_state() -> dict[str, Any] | None:
    return _STATE.get()


def reset_current_state(token: Any) -> None:
    _STATE.reset(token)


def begin_turn(session_id: str) -> dict[str, Any]:
    state = load_conversation_state(session_id)
    set_current_state(state)
    return state


def end_turn(
    state: dict[str, Any],
    *,
    user_message: str,
    response: dict[str, Any],
    intent: str | None = None,
    action_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    apply_turn_result(
        state,
        user_message=user_message,
        response=response,
        intent=intent,
        action_decision=action_decision,
    )
    try:
        from app.chatbot.chatbot_service import (
            _DEFAULT_FILTERS,
            _get_last_filters,
            _save_last_filters,
        )

        session_id = state.get("session_id") or ""
        collected = state.get("collected_fields") or {}
        # Canonical requirement state → chatbot filter store (never reverse-clobber)
        if any(collected.get(k) for k in ("category", "purpose", "city", "budget", "listing_type")):
            synced = {**_DEFAULT_FILTERS, **_get_last_filters(session_id)}
            synced.update(_collected_to_filters(collected))
            _save_last_filters(session_id, synced)
        elif state.get("last_search_filters"):
            clean = {k: v for k, v in state["last_search_filters"].items() if v is not None}
            if clean:
                _save_last_filters(
                    session_id,
                    {**_DEFAULT_FILTERS, **_get_last_filters(session_id), **clean},
                )
    except Exception:
        pass
    save_conversation_state(state)
    return state
