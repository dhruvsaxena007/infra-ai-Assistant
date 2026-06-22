"""
Structured debug trace for assistant /chat requests.

Enabled only when ASSISTANT_DEBUG=true. Logs one JSON object per request;
does not alter API response shape.
"""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from app.core.config import settings

_TRACE: ContextVar[Optional[dict[str, Any]]] = ContextVar("assistant_debug_trace", default=None)
_LAST_TRACE: dict[str, Any] | None = None


def assistant_debug_enabled() -> bool:
    return bool(getattr(settings, "ASSISTANT_DEBUG", False))


def _empty_trace(session_id: str, user_message: str, request_id: str | None = None) -> dict[str, Any]:
    return {
        "request_id": request_id or f"trace-{uuid.uuid4().hex[:8]}",
        "session_id": session_id,
        "user_message": user_message,
        "normalized_message": "",
        "env": {
            "ai_intent_mode": settings.AI_INTENT_MODE,
            "llm_intent_first": settings.llm_intent_first,
            "llm_shadow": settings.llm_shadow,
            "ai_provider": settings.AI_PROVIDER,
            "enable_openai": settings.ENABLE_OPENAI,
            "use_llm_response_generation": settings.use_llm_response_generation,
        },
        "memory_before": _empty_memory(),
        "classification": _empty_classification(),
        "llm_intent": _empty_llm_intent(),
        "rules_intent": _empty_rules_intent(),
        "intent_resolution": _empty_intent_resolution(),
        "permission": _empty_permission(),
        "state": _empty_state(),
        "routing": _empty_routing(),
        "recovery": _empty_recovery(),
        "user_profile": _empty_user_profile_trace(),
        "context_routing": _empty_context_routing(),
        "requirement_transition": _empty_requirement_transition(),
        "domain_intelligence": _empty_domain_intelligence(),
        "capability_validation": _empty_capability_validation_trace(),
        "response": _empty_response(),
        "memory_after": _empty_memory(),
    }


def _empty_memory() -> dict[str, Any]:
    return {
        "active_flow": None,
        "pending_fields": [],
        "collected_fields": {},
        "last_search_filters": {},
        "recent_response_signatures": [],
    }


def _empty_classification() -> dict[str, Any]:
    return {
        "llm_intent_called": False,
        "rules_intent_called": False,
        "universal_classifier_called": False,
        "intent_source": "fallback",
        "raw_intent": "",
        "validated_intent": "",
        "confidence": 0.0,
        "entities": {},
        "missing_fields": [],
        "validation_notes": [],
        "response_goal": "",
    }


def _empty_llm_intent() -> dict[str, Any]:
    return {
        "called": False,
        "mode": settings.AI_INTENT_MODE,
        "provider": settings.AI_PROVIDER,
        "raw_output_valid": False,
        "intent": "",
        "confidence": 0.0,
        "entities": {},
        "missing_fields": [],
        "validation_passed": False,
        "fallback_reason": None,
    }


def _empty_rules_intent() -> dict[str, Any]:
    return {
        "called": False,
        "intent": "",
        "confidence": 0.0,
        "entities": {},
    }


def _empty_intent_resolution() -> dict[str, Any]:
    return {
        "final_intent_source": "",
        "final_intent": "",
        "llm_rules_match": None,
        "mismatch_reason": None,
    }


def _empty_state() -> dict[str, Any]:
    return {
        "loaded": False,
        "active_flow_before": "",
        "active_flow_after": "",
        "expected_user_reply_before": "",
        "expected_user_reply_after": "",
        "pending_fields_before": [],
        "pending_fields_after": [],
        "collected_fields_before": {},
        "collected_fields_after": {},
        "last_search_filters_before": {},
        "last_search_filters_after": {},
        "state_merge_applied": False,
        "state_saved": False,
        "state_switch_reason": None,
    }


def _empty_permission() -> dict[str, Any]:
    return {
        "matrix_applied": False,
        "allowed_tools": [],
        "blocked_tools": [],
        "selected_tool": "",
        "permission_passed": False,
        "permission_block_reason": None,
    }


def _empty_user_profile_trace() -> dict[str, Any]:
    return {
        "loaded": False,
        "profile_source": "none",
        "profile_hints_used": [],
        "profile_updated": False,
        "updated_fields": [],
        "sensitive_fields_skipped": True,
    }


def _empty_context_routing() -> dict[str, Any]:
    return {
        "current_intent_family": "",
        "context_eligibility_decision": "",
        "previous_context_used": False,
        "previous_context_blocked_reason": "",
        "reference_enrich_applied": False,
        "reference_enrich_blocked_reason": "",
        "active_flow_before": "",
        "active_flow_after": "",
        "tool_permission_checked": False,
        "selected_action": "",
        "selected_tool": "",
        "search_blocked_reason": "",
        "false_claim_guard_applied": False,
        "current_message_entities": {},
        "previous_filters": {},
        "context_reuse_allowed": True,
        "final_filters": {},
    }


def record_context_routing(meta: dict[str, Any] | None) -> None:
    trace = _current()
    if trace is None or not meta:
        return
    cr = trace["context_routing"]
    for key in _empty_context_routing():
        if key in meta:
            cr[key] = meta[key]


def _empty_requirement_transition() -> dict[str, Any]:
    return {
        "active_flow_before": "",
        "active_flow_after": "",
        "intent_family": "",
        "explicit_fields": {},
        "derived_fields": {},
        "field_provenance": {},
        "pending_fields_before": [],
        "pending_fields_after": [],
        "collected_fields_before": {},
        "collected_fields_after": {},
        "fields_changed": [],
        "fields_invalidated": [],
        "context_applied": False,
        "context_rejected_reason": "",
        "requirements_complete": False,
        "next_missing_field": None,
        "selected_action": "",
        "search_triggered": False,
        "search_filters": {},
        "permission_passed": True,
        "reason": "",
        "invariant_violations": [],
    }


def _empty_domain_intelligence() -> dict[str, Any]:
    return {
        "called": False,
        "provider": "",
        "model": "",
        "schema_valid": False,
        "confidence": 0.0,
        "user_goal": "",
        "domain_scope": "",
        "relevance": "",
        "request_type": "",
        "response_mode": "",
        "proposed_tool": None,
        "fallback_used": False,
        "fallback_reason": None,
        "rules_response_mode": "",
        "llm_response_mode": "",
        "mismatch": False,
    }


def _empty_capability_validation_trace() -> dict[str, Any]:
    return {
        "registry_checked": False,
        "catalog_checked": False,
        "requested_asset_supported": None,
        "requested_action_supported": None,
        "closest_supported_capability": None,
    }


def record_domain_intelligence(
    result: Any,
    *,
    rules: Any = None,
    llm: Any = None,
    fallback_used: bool = False,
) -> None:
    trace = _current()
    if trace is None or result is None:
        return
    di = trace["domain_intelligence"]
    d = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    di.update({
        "called": True,
        "provider": "groq" if getattr(settings, "domain_intelligence_use_llm", False) else "rules",
        "schema_valid": True,
        "confidence": d.get("confidence", 0.0),
        "user_goal": d.get("user_goal", ""),
        "domain_scope": d.get("domain_scope", ""),
        "relevance": d.get("relevance", ""),
        "request_type": d.get("request_type", ""),
        "response_mode": d.get("response_mode", ""),
        "proposed_tool": d.get("proposed_tool"),
        "fallback_used": fallback_used,
        "fallback_reason": d.get("reason") if fallback_used else None,
    })
    if rules:
        r = rules.to_dict() if hasattr(rules, "to_dict") else {}
        di["rules_response_mode"] = r.get("response_mode", "")
    if llm:
        l = llm.to_dict() if hasattr(llm, "to_dict") else {}
        di["llm_response_mode"] = l.get("response_mode", "")
        di["mismatch"] = di["rules_response_mode"] != di["llm_response_mode"]
    cap = d.get("capability") or {}
    trace["capability_validation"] = {
        **_empty_capability_validation_trace(),
        **cap,
    }


def record_requirement_transition(decision: Any) -> None:
    """Log canonical requirement state transition when ASSISTANT_DEBUG=true."""
    trace = _current()
    if trace is None or decision is None:
        return
    rt = trace["requirement_transition"]
    d = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
    state_before = getattr(decision, "state_before", None) or d.get("state_before") or {}
    state_after = getattr(decision, "state_after", None) or d.get("state_after") or {}
    explicit_before = (state_before.get("explicit") or {}) if isinstance(state_before, dict) else {}
    explicit_after = (state_after.get("explicit") or {}) if isinstance(state_after, dict) else {}
    rt.update({
        "active_flow_before": d.get("active_flow_before") or "",
        "active_flow_after": d.get("active_flow_after") or "",
        "intent_family": d.get("intent_family") or "",
        "explicit_fields": explicit_after,
        "derived_fields": d.get("derived_fields") or {},
        "field_provenance": (state_after.get("provenance") or {}) if isinstance(state_after, dict) else {},
        "pending_fields_before": d.get("pending_fields_before") or [],
        "pending_fields_after": d.get("pending_fields_after") or [],
        "collected_fields_before": explicit_before,
        "collected_fields_after": explicit_after,
        "fields_changed": d.get("fields_changed") or [],
        "fields_invalidated": d.get("fields_invalidated") or [],
        "context_applied": bool(getattr(decision, "context_applied", d.get("context_applied"))),
        "context_rejected_reason": d.get("context_rejected_reason") or "",
        "requirements_complete": bool(d.get("requirements_complete")),
        "next_missing_field": d.get("next_missing_field"),
        "selected_action": d.get("selected_action") or "",
        "search_triggered": bool(d.get("search_triggered")),
        "search_filters": d.get("search_filters") or {},
        "permission_passed": bool(d.get("permission_passed", True)),
        "reason": d.get("reason") or "",
        "invariant_violations": d.get("invariant_violations") or [],
    })
    st = trace["state"]
    st["pending_fields_after"] = rt["pending_fields_after"]
    st["collected_fields_after"] = rt["collected_fields_after"]
    st["active_flow_after"] = rt["active_flow_after"]
    st["state_merge_applied"] = True


def _empty_recovery() -> dict[str, Any]:
    return {
        "engine_called": False,
        "recovery_type": "",
        "auto_retry_attempted": False,
        "auto_retry_allowed": False,
        "auto_retry_results_count": 0,
        "safe_alternatives_count": 0,
        "next_best_action": "",
        "recovery_state_saved": False,
    }


def _empty_routing() -> dict[str, Any]:
    return {
        "selected_action": "",
        "assistant_mode": "",
        "tool_used": "none",
        "required_entities": [],
        "missing_fields": [],
        "should_search_machines": False,
        "should_use_rag": False,
        "should_use_support": False,
        "response_plan_created": False,
    }


def _empty_response() -> dict[str, Any]:
    return {
        "response_plan_created": False,
        "gateway_used": False,
        "llm_response_called": False,
        "final_response_source": "",
        "response_goal": "",
        "response_signature": "",
        "avoided_recent_signature": False,
        "old_template_bypassed": False,
        "response_gateway_bypass_detected": False,
        "suggestions": [],
    }


def begin_chat_trace(
    session_id: str,
    user_message: str,
    *,
    request_id: str | None = None,
) -> Any:
    """Start per-request trace context. Returns reset token."""
    if not assistant_debug_enabled():
        return None
    trace = _empty_trace(session_id, user_message, request_id)
    return _TRACE.set(trace)


def _current() -> dict[str, Any] | None:
    if not assistant_debug_enabled():
        return None
    return _TRACE.get()


def end_chat_trace(token: Any) -> None:
    if token is not None:
        _TRACE.reset(token)


def build_memory_snapshot(
    session_ctx: dict | None,
    last_filters: dict | None,
    pending: dict | None = None,
) -> dict[str, Any]:
    from app.ai.response_memory import get_response_memory

    ctx = session_ctx or {}
    mem = get_response_memory(ctx)
    pending_fields = list(mem.get("pending_fields") or [])
    if pending:
        missing = pending.get("missing") or []
        if isinstance(missing, list):
            pending_fields = list(dict.fromkeys(pending_fields + missing))
        pf = pending.get("missing_field")
        if pf and pf not in pending_fields:
            pending_fields.append(pf)

    active_flow = None
    if pending:
        active_flow = pending.get("type") or pending.get("missing_field")
    elif ctx.get("awaiting_project_type"):
        active_flow = "project_recommendation"
    elif mem.get("last_support_issue"):
        active_flow = "support"

    collected = {}
    for key in ("category", "city", "brand", "max_price", "purpose_key"):
        val = (last_filters or {}).get(key)
        if val is not None and val != "":
            collected[key] = val

    return {
        "active_flow": active_flow,
        "pending_fields": pending_fields,
        "collected_fields": collected,
        "last_search_filters": dict(last_filters or {}),
        "recent_response_signatures": list(mem.get("recent_response_signatures") or []),
    }


def record_memory_before(snapshot: dict[str, Any]) -> None:
    trace = _current()
    if trace is not None:
        trace["memory_before"] = snapshot


def record_normalized_message(normalized: str) -> None:
    trace = _current()
    if trace is not None:
        trace["normalized_message"] = normalized


def record_universal_classifier_called() -> None:
    trace = _current()
    if trace is not None:
        trace["classification"]["universal_classifier_called"] = True


def record_rules_intent_called() -> None:
    trace = _current()
    if trace is not None:
        trace["classification"]["rules_intent_called"] = True


def record_llm_intent_called() -> None:
    trace = _current()
    if trace is not None:
        trace["classification"]["llm_intent_called"] = True


def record_intent_result(classification: dict[str, Any]) -> None:
    trace = _current()
    if trace is None:
        return
    layer = str(classification.get("layer") or "").lower()
    intent = classification.get("llm_intent") or classification.get("intent") or ""
    validated = classification.get("intent") or intent

    if settings.llm_intent_first or layer in ("llm", "groq_llm", "groq", "llm_low_confidence"):
        src = classification.get("intent_source")
        if src == "rules_fallback" or layer == "rules_fallback":
            trace["classification"]["intent_source"] = "rules_fallback"
        elif settings.llm_intent_first:
            trace["classification"]["intent_source"] = "llm"
        elif layer == "groq":
            trace["classification"]["intent_source"] = "llm"
        else:
            trace["classification"]["intent_source"] = "rules"
    elif layer == "rules" or layer == "fuzzy":
        trace["classification"]["intent_source"] = "rules"
    elif layer == "universal":
        trace["classification"]["intent_source"] = "universal"
    else:
        trace["classification"]["intent_source"] = "fallback"

    trace["classification"]["raw_intent"] = str(intent)
    trace["classification"]["validated_intent"] = str(validated)
    trace["classification"]["confidence"] = float(classification.get("confidence") or 0.0)
    trace["classification"]["entities"] = dict(classification.get("entities") or {})
    trace["classification"]["missing_fields"] = list(classification.get("missing_fields") or [])
    trace["classification"]["validation_notes"] = list(classification.get("validation_notes") or [])
    trace["classification"]["response_goal"] = str(classification.get("response_goal") or "")


def record_llm_intent_result(
    classification: dict[str, Any],
    *,
    validation_passed: bool,
    fallback_reason: str | None = None,
) -> None:
    trace = _current()
    if trace is None:
        return
    block = trace["llm_intent"]
    block["called"] = True
    block["mode"] = settings.AI_INTENT_MODE
    block["provider"] = settings.AI_PROVIDER
    block["raw_output_valid"] = bool(classification)
    block["intent"] = str(classification.get("llm_intent") or classification.get("intent") or "")
    block["confidence"] = float(classification.get("confidence") or 0.0)
    block["entities"] = dict(classification.get("entities") or {})
    block["missing_fields"] = list(classification.get("missing_fields") or [])
    block["validation_passed"] = validation_passed
    block["fallback_reason"] = fallback_reason


def record_rules_intent_snapshot(classification: dict[str, Any]) -> None:
    trace = _current()
    if trace is None:
        return
    block = trace["rules_intent"]
    block["called"] = True
    block["intent"] = str(classification.get("intent") or "")
    block["confidence"] = float(classification.get("confidence") or 0.0)
    block["entities"] = dict(classification.get("entities") or {})


def record_intent_shadow_comparison(
    rules_result: dict[str, Any],
    llm_result: dict[str, Any],
) -> None:
    trace = _current()
    if trace is None:
        return
    record_rules_intent_snapshot(rules_result)
    record_llm_intent_result(
        llm_result,
        validation_passed=bool(llm_result) and float(llm_result.get("confidence") or 0) >= 0.55,
        fallback_reason=None if llm_result else "shadow_llm_unavailable",
    )
    rules_intent = str(rules_result.get("intent") or "")
    llm_intent = str(llm_result.get("llm_intent") or llm_result.get("intent") or "")
    match = rules_intent == llm_intent or (
        rules_intent == (llm_result.get("intent") or "")
    )
    res = trace["intent_resolution"]
    res["final_intent_source"] = "rules_shadow"
    res["final_intent"] = rules_intent
    res["llm_rules_match"] = match
    res["mismatch_reason"] = None if match else f"rules={rules_intent} llm={llm_intent}"


def record_intent_resolution(
    classification: dict[str, Any],
    *,
    final_source: str,
) -> None:
    trace = _current()
    if trace is None:
        return
    res = trace["intent_resolution"]
    res["final_intent_source"] = final_source
    res["final_intent"] = str(classification.get("intent") or classification.get("llm_intent") or "")
    if final_source == "rules_fallback":
        res["mismatch_reason"] = classification.get("reason") or "llm_fallback"
    llm_block = trace.get("llm_intent") or {}
    rules_block = trace.get("rules_intent") or {}
    if llm_block.get("intent") and rules_block.get("intent"):
        res["llm_rules_match"] = llm_block["intent"] == rules_block["intent"]


def record_state_before(state: dict[str, Any]) -> None:
    trace = _current()
    if trace is None:
        return
    st = trace["state"]
    st["loaded"] = True
    st["active_flow_before"] = str(state.get("active_flow") or "")
    st["expected_user_reply_before"] = str(state.get("expected_user_reply") or "")
    st["pending_fields_before"] = list(state.get("pending_fields") or [])
    st["collected_fields_before"] = dict(state.get("collected_fields") or {})
    st["last_search_filters_before"] = dict(state.get("last_search_filters") or {})


def record_state_after(state: dict[str, Any], *, saved: bool = True) -> None:
    trace = _current()
    if trace is None:
        return
    st = trace["state"]
    st["active_flow_after"] = str(state.get("active_flow") or "")
    st["expected_user_reply_after"] = str(state.get("expected_user_reply") or "")
    st["pending_fields_after"] = list(state.get("pending_fields") or [])
    st["collected_fields_after"] = dict(state.get("collected_fields") or {})
    st["last_search_filters_after"] = dict(state.get("last_search_filters") or {})
    st["state_merge_applied"] = bool(state.get("_merge_applied"))
    st["state_saved"] = saved
    st["state_switch_reason"] = state.get("_switch_reason")


def record_action_decision(decision: dict[str, Any]) -> None:
    """Record Phase 4 permission matrix + action routing decision."""
    trace = _current()
    if trace is None:
        return
    perm = trace["permission"]
    perm["matrix_applied"] = True
    from app.ai.tool_permission_matrix import get_intent_permissions

    intent = decision.get("intent") or "unknown"
    intent_perms = get_intent_permissions(intent)
    perm["allowed_tools"] = list(intent_perms.get("allowed_tools") or [])
    perm["blocked_tools"] = list(decision.get("blocked_tools") or intent_perms.get("blocked_tools") or [])
    perm["selected_tool"] = str(decision.get("allowed_tool") or "")
    perm["permission_passed"] = bool(decision.get("permission_passed"))
    perm["permission_block_reason"] = decision.get("permission_block_reason")
    record_context_routing({
        "tool_permission_checked": True,
        "selected_action": str(decision.get("selected_action") or ""),
        "selected_tool": str(decision.get("allowed_tool") or ""),
        "search_blocked_reason": decision.get("permission_block_reason") or "",
    })

    routing = trace["routing"]
    routing["selected_action"] = str(decision.get("selected_action") or "")
    routing["assistant_mode"] = str(decision.get("assistant_mode") or "")
    routing["required_entities"] = list(decision.get("required_entities") or [])
    routing["missing_fields"] = list(decision.get("missing_fields") or [])
    routing["should_search_machines"] = bool(decision.get("should_search_machines"))
    routing["should_use_rag"] = bool(decision.get("should_use_rag"))
    routing["should_use_support"] = bool(decision.get("should_use_support"))
    if decision.get("allowed_tool"):
        routing["tool_used"] = str(decision.get("allowed_tool"))


def record_routing(
    *,
    selected_action: str = "",
    tool_used: str = "none",
    should_search_machines: bool = False,
    response_plan_created: bool = False,
) -> None:
    trace = _current()
    if trace is None:
        return
    routing = trace["routing"]
    if selected_action:
        routing["selected_action"] = selected_action
    if tool_used:
        routing["tool_used"] = tool_used
    routing["should_search_machines"] = should_search_machines
    if response_plan_created:
        routing["response_plan_created"] = True


def record_user_profile(meta: dict[str, Any] | None) -> None:
    trace = _current()
    if trace is None or not meta:
        return
    up = trace["user_profile"]
    up["loaded"] = bool(meta.get("loaded"))
    up["profile_source"] = str(meta.get("profile_source") or "none")
    up["profile_hints_used"] = list(meta.get("profile_hints_used") or [])
    up["profile_updated"] = bool(meta.get("profile_updated"))
    up["updated_fields"] = list(meta.get("updated_fields") or [])
    up["sensitive_fields_skipped"] = bool(meta.get("sensitive_fields_skipped", True))


def record_recovery(
    recovery: dict[str, Any] | None,
    *,
    recovery_state_saved: bool = False,
) -> None:
    trace = _current()
    if trace is None:
        return
    rec = trace["recovery"]
    rec["engine_called"] = True
    if not recovery:
        return
    rec["recovery_type"] = str(recovery.get("recovery_type") or "")
    rec["auto_retry_attempted"] = bool(recovery.get("auto_retried"))
    rec["auto_retry_allowed"] = bool(recovery.get("auto_retry_allowed"))
    auto = recovery.get("auto_retry_results") or {}
    rec["auto_retry_results_count"] = int(auto.get("count") or len(auto.get("machines") or []))
    rec["safe_alternatives_count"] = len(recovery.get("safe_alternatives") or [])
    rec["next_best_action"] = str(recovery.get("next_best_action") or "")
    rec["recovery_state_saved"] = recovery_state_saved


def record_response_delivery(result: dict[str, Any]) -> None:
    trace = _current()
    if trace is None:
        return
    resp = trace["response"]
    llm_gen = bool(result.get("llm_generated"))
    fallback = bool(result.get("fallback_used"))
    style = str(result.get("response_style") or "")

    if llm_gen:
        resp["final_response_source"] = "llm_response"
    elif style == "deterministic":
        resp["final_response_source"] = "deterministic_fallback"
        resp["response_gateway_bypass_detected"] = True
    elif fallback and result.get("response_plan"):
        resp["final_response_source"] = "local_dynamic_fallback"
    elif fallback or style in ("local_fallback", "local_dynamic_fallback", "template"):
        resp["final_response_source"] = "local_dynamic_fallback"
    elif style == "error_fallback":
        resp["final_response_source"] = "error_fallback"
    else:
        resp["final_response_source"] = "local_dynamic_fallback"

    resp["gateway_used"] = bool(result.get("gateway_used", True))
    resp["response_plan_created"] = bool(result.get("response_plan"))
    resp["avoided_recent_signature"] = bool(result.get("avoided_recent_signature"))
    resp["old_template_bypassed"] = not bool(result.get("gateway_used", True))

    if settings.use_llm_response_generation:
        resp["llm_response_called"] = llm_gen or bool(result.get("llm_response_attempted"))

    resp["response_goal"] = str(result.get("response_goal") or "")
    resp["response_signature"] = str(result.get("response_signature") or "")
    suggestions = result.get("suggestions")
    if isinstance(suggestions, list):
        resp["suggestions"] = [str(s) for s in suggestions[:8]]

    trace["routing"]["response_plan_created"] = bool(result.get("response_plan"))


def _infer_tool_from_response(data: dict[str, Any], ctx: dict[str, Any]) -> str:
    mode = str(data.get("context", {}).get("assistant_mode") or data.get("assistant_mode") or "")
    intent = str(ctx.get("intent") or "")
    if mode in ("document_qa",) or intent == "document_question":
        return "rag"
    if mode in ("support", "payment_issue", "order_issue", "refund_return", "out_of_scope") or "issue" in intent:
        return "support"
    if mode in ("image_clarification", "image_search") or "image" in intent:
        return "image"
    machines = data.get("machines") or []
    filters = data.get("filters") or {}
    if machines or filters.get("category") or ctx.get("should_search_machines"):
        return "mongodb"
    return "none"


def _infer_response_source_from_context(ctx: dict[str, Any]) -> str:
    if ctx.get("llm_generated"):
        return "llm_response"
    if ctx.get("fallback_used"):
        return "local_dynamic_fallback"
    if ctx.get("response_signature") and not ctx.get("llm_generated"):
        return "local_dynamic_fallback"
    if ctx.get("gateway_used"):
        return "local_dynamic_fallback"
    return ""


def finalize_chat_trace(
    response: dict[str, Any],
    session_id: str,
    *,
    memory_after: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build final trace from response + session state, log JSON, return trace."""
    global _LAST_TRACE
    trace = _current()
    if trace is None:
        return None

    data = response.get("data") or {}
    ctx = data.get("context") or {}
    message = response.get("message") or data.get("message") or ""

    if memory_after is not None:
        trace["memory_after"] = memory_after

    if not trace["classification"]["raw_intent"] and ctx.get("intent"):
        trace["classification"]["validated_intent"] = str(ctx.get("intent"))
        trace["classification"]["raw_intent"] = str(ctx.get("intent"))
    if ctx.get("confidence") is not None:
        try:
            trace["classification"]["confidence"] = float(ctx.get("confidence") or 0)
        except (TypeError, ValueError):
            pass

    if not trace["routing"]["selected_action"]:
        trace["routing"]["selected_action"] = str(
            ctx.get("assistant_mode") or data.get("assistant_mode") or ctx.get("intent") or ""
        )
    if trace["routing"]["tool_used"] == "none":
        trace["routing"]["tool_used"] = _infer_tool_from_response(data, ctx)
    if "should_search_machines" in ctx:
        trace["routing"]["should_search_machines"] = bool(ctx.get("should_search_machines"))
    elif data.get("machines"):
        trace["routing"]["should_search_machines"] = True

    if not trace["response"]["final_response_source"]:
        inferred = _infer_response_source_from_context(ctx)
        if inferred:
            trace["response"]["final_response_source"] = inferred
        elif message:
            trace["response"]["final_response_source"] = "local_dynamic_fallback"

    if ctx.get("gateway_used") is True:
        trace["response"]["gateway_used"] = True
        trace["response"]["response_plan_created"] = True
        trace["response"]["response_gateway_bypass_detected"] = False
    if ctx.get("response_signature"):
        trace["response"]["response_signature"] = str(ctx.get("response_signature"))
    if not trace["response"]["response_goal"]:
        trace["response"]["response_goal"] = str(ctx.get("response_goal") or "")
    if not trace["response"]["suggestions"]:
        suggestions = data.get("suggestions") or []
        if isinstance(suggestions, list):
            trace["response"]["suggestions"] = [str(s) for s in suggestions[:8]]

    _LAST_TRACE = trace
    print(f"[assistant_debug_trace] {json.dumps(trace, ensure_ascii=False, default=str)}")
    return trace


def get_current_debug_trace() -> dict[str, Any] | None:
    """Return in-flight or last completed trace (for evaluation tests)."""
    trace = _current()
    if trace is not None:
        return dict(trace)
    return _LAST_TRACE


def get_last_debug_trace() -> dict[str, Any] | None:
    """Return last completed trace (for evaluation tests when ASSISTANT_DEBUG=true)."""
    return _LAST_TRACE
