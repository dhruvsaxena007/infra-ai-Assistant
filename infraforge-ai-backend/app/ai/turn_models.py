"""
Normalized turn decision and result objects — single source for response, debug, state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TurnDecision:
    current_intent_family: str = "unknown"
    raw_intent: str = "unknown"
    assistant_mode: str = "clarification"
    selected_action: str = ""
    selected_tool: str = "none"
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    should_search_machines: bool = False
    should_use_support: bool = False
    should_use_rag: bool = False
    context_allowed: bool = True
    context_used: bool = False
    context_block_reason: str = ""
    filters_to_use: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_gate_and_action(
        cls,
        gate: dict[str, Any],
        classification: dict[str, Any],
        action_decision: dict[str, Any],
        *,
        filters: dict | None = None,
    ) -> "TurnDecision":
        return cls(
            current_intent_family=gate.get("family") or "unknown",
            raw_intent=str(classification.get("intent") or "unknown"),
            assistant_mode=(
                action_decision.get("assistant_mode")
                or classification.get("assistant_mode")
                or "clarification"
            ),
            selected_action=action_decision.get("selected_action") or "",
            selected_tool=action_decision.get("allowed_tool") or "none",
            allowed_tools=list(action_decision.get("allowed_tools") or []),
            blocked_tools=list(action_decision.get("blocked_tools") or []),
            missing_fields=list(classification.get("missing_fields") or []),
            should_search_machines=bool(action_decision.get("should_search_machines")),
            should_use_support=bool(action_decision.get("should_use_support")),
            should_use_rag=bool(action_decision.get("should_use_rag")),
            context_allowed=not gate.get("block_previous_search_context"),
            context_used=not gate.get("block_previous_search_context"),
            context_block_reason=gate.get("reason") or "",
            filters_to_use=dict(filters or {}),
        )

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "current_intent_family": self.current_intent_family,
            "raw_intent": self.raw_intent,
            "selected_action": self.selected_action,
            "selected_tool": self.selected_tool,
            "should_search_machines": self.should_search_machines,
            "context_allowed": self.context_allowed,
            "context_used": self.context_used,
            "context_block_reason": self.context_block_reason,
            "filters_to_use": self.filters_to_use,
        }


@dataclass
class TurnResult:
    response_text: str = ""
    assistant_mode: str = "clarification"
    selected_action: str = ""
    filters_used: dict[str, Any] = field(default_factory=dict)
    category: str | None = None
    city: str | None = None
    brand: str | None = None
    model: str | None = None
    listing_type: str | None = None
    budget: Any = None
    machines: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    state_updates: dict[str, Any] = field(default_factory=dict)
    frontend_payload: dict[str, Any] = field(default_factory=dict)
    false_claim_guard_applied: bool = False

    @classmethod
    def from_response(
        cls,
        response: dict[str, Any],
        *,
        decision: TurnDecision | None = None,
        filters: dict | None = None,
    ) -> "TurnResult":
        data = response.get("data") or {}
        ctx = data.get("context") or {}
        used = dict(filters or data.get("filters") or {})
        if decision and decision.filters_to_use and not used:
            used = dict(decision.filters_to_use)
        return cls(
            response_text=response.get("message") or data.get("advisor_message") or "",
            assistant_mode=data.get("assistant_mode") or ctx.get("assistant_mode") or "clarification",
            selected_action=(decision.selected_action if decision else ctx.get("selected_action")) or "",
            filters_used=used,
            category=used.get("category"),
            city=used.get("city"),
            brand=used.get("brand"),
            model=used.get("model"),
            listing_type=used.get("listing_type"),
            budget=used.get("max_price"),
            machines=list(data.get("machines") or []),
            suggestions=list(data.get("suggestions") or []),
            frontend_payload=data,
            false_claim_guard_applied=bool(ctx.get("false_claim_guard_applied")),
        )

    def sync_filters_to_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure filters in API payload match filters_used (shape unchanged)."""
        if self.filters_used:
            payload["filters"] = {**payload.get("filters", {}), **self.filters_used}
        ctx = payload.get("context") or {}
        if self.filters_used:
            ctx["filters"] = {**ctx.get("filters", {}), **self.filters_used}
        if self.category:
            ctx.setdefault("entities", {})["category"] = self.category
        if self.city:
            ctx.setdefault("entities", {})["city"] = self.city
        payload["context"] = ctx
        return payload


def build_turn_result_payload(
    *,
    message: str,
    machines: list | None,
    assistant_mode: str,
    suggestions: list | None,
    filters: dict | None,
    context_extra: dict | None,
    payload_builder,
    **kwargs,
) -> dict[str, Any]:
    """Build assistant payload with synchronized filters."""
    flt = {k: v for k, v in (filters or {}).items() if v is not None}
    payload = payload_builder(
        message=message,
        machines=machines or [],
        assistant_mode=assistant_mode,
        suggestions=suggestions or [],
        filters=flt,
        context_extra={
            **(context_extra or {}),
            "filters": flt,
            "entities": {
                k: flt.get(k)
                for k in ("category", "city", "brand", "model", "listing_type")
                if flt.get(k)
            },
        },
        **kwargs,
    )
    return payload
