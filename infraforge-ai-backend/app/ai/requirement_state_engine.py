"""
Canonical multi-turn machine requirement state transition engine.

Single deterministic owner for:
- collected requirements (explicit + derived + provenance)
- pending fields
- search readiness
- revision / invalidation
- normalized search filters

Router, response, and search layers must consume RequirementTransitionDecision
instead of independently reconstructing requirement state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ai.purpose_taxonomy import (
    categories_for_purpose,
    category_compatible_with_purpose,
    purpose_category_ambiguous,
    resolve_derived_category,
)
from app.ai.query_parser import parse_query

# Field keys used in pending_fields (canonical names)
FIELD_PURPOSE_OR_CATEGORY = "purpose_or_category"
FIELD_CITY = "city"
FIELD_BRAND = "brand"
FIELD_MODEL = "model"
FIELD_BUDGET = "budget"
FIELD_LISTING_TYPE = "listing_type"

MACHINE_REQUIREMENT_FLOWS = frozenset({
    "machine_requirement_collection",
    "machine_search",
    "search_refinement",
    "machine_recommendation",
    "brand_inventory",
    "no_result_recovery",
})

PROTECTED_NON_SEARCH_FAMILIES = frozenset({
    "frustration_or_abuse",
    "return_refund_or_booking_problem",
    "support_or_issue",
    "document_question",
    "image_followup",
    "conversational",
    "out_of_scope",
})

_EXPLICIT_KEYS = (
    "purpose", "category", "city", "brand", "model", "budget", "listing_type",
)
_PROVENANCE_SOURCES = ("user_explicit", "pending_answer", "session_context", "profile_hint", "derived")


def empty_requirement_state() -> dict[str, Any]:
    return {
        "explicit": {k: None for k in _EXPLICIT_KEYS},
        "derived": {"category": None},
        "provenance": {k: None for k in _EXPLICIT_KEYS},
        "pending_fields": [],
        "active_flow": None,
        "revision": 0,
        "suspended": False,
        "needs_confirmation": False,
        "confirmation_reason": None,
    }


def requirement_state_from_conversation(conv_state: dict[str, Any]) -> dict[str, Any]:
    """Hydrate canonical requirement state from conversation_state collected_fields."""
    collected = conv_state.get("collected_fields") or {}
    req = empty_requirement_state()
    req["active_flow"] = conv_state.get("active_flow")
    req["pending_fields"] = list(conv_state.get("pending_fields") or [])
    req["revision"] = int(conv_state.get("_requirement_revision") or 0)
    req["suspended"] = bool(conv_state.get("_requirement_suspended"))

    for key in _EXPLICIT_KEYS:
        val = collected.get(key)
        if key == "budget":
            val = val if val is not None else collected.get("max_price")
        if val is not None and val != "" and val != []:
            req["explicit"][key] = val
            prov = (conv_state.get("_field_provenance") or {}).get(key)
            req["provenance"][key] = prov or "session_context"

    derived_cat = (conv_state.get("_derived_category") or {}).get("category")
    if derived_cat and not req["explicit"].get("category"):
        req["derived"]["category"] = derived_cat
    elif req["explicit"].get("category"):
        req["derived"]["category"] = None

    return req


def sync_requirement_to_conversation(
    conv_state: dict[str, Any],
    req: dict[str, Any],
    *,
    decision: Optional["RequirementTransitionDecision"] = None,
) -> dict[str, Any]:
    """Write canonical requirement state back to conversation_state (single writer)."""
    explicit = req.get("explicit") or {}
    collected = dict(conv_state.get("collected_fields") or {})

    for key in _EXPLICIT_KEYS:
        val = explicit.get(key)
        if val is not None and val != "" and val != []:
            collected[key] = val
        elif key in collected and decision and key in (decision.fields_invalidated or []):
            collected.pop(key, None)

    # Effective category: explicit beats derived
    eff_cat = explicit.get("category") or (req.get("derived") or {}).get("category")
    if eff_cat:
        collected["category"] = eff_cat
    elif decision and "category" in (decision.fields_invalidated or []):
        collected.pop("category", None)

    if explicit.get("brand"):
        collected["brands"] = [explicit["brand"]]

    conv_state["collected_fields"] = collected
    conv_state["pending_fields"] = list(req.get("pending_fields") or [])
    conv_state["active_flow"] = req.get("active_flow") or conv_state.get("active_flow")
    conv_state["_requirement_revision"] = req.get("revision", 0)
    conv_state["_requirement_suspended"] = req.get("suspended", False)
    conv_state["_field_provenance"] = dict(req.get("provenance") or {})
    conv_state["_derived_category"] = dict(req.get("derived") or {})

    # Sync last_search_filters from effective requirements
    sf = dict(conv_state.get("last_search_filters") or {})
    if eff_cat:
        sf["category"] = eff_cat
    if explicit.get("city"):
        sf["city"] = explicit["city"]
    if explicit.get("brand"):
        sf["brand"] = explicit["brand"]
    if explicit.get("model"):
        sf["model"] = explicit["model"]
    if explicit.get("budget") is not None:
        sf["max_price"] = explicit["budget"]
    if explicit.get("listing_type"):
        sf["listing_type"] = explicit["listing_type"]
    if explicit.get("purpose"):
        sf["purpose_key"] = explicit["purpose"]
    conv_state["last_search_filters"] = {k: v for k, v in sf.items() if v is not None}

    if decision:
        conv_state["_last_requirement_decision"] = decision.to_dict()

    return conv_state


@dataclass
class RequirementTransitionDecision:
    intent_family: str = "unknown"
    active_flow_before: str | None = None
    active_flow_after: str | None = None
    state_before: dict = field(default_factory=dict)
    state_after: dict = field(default_factory=dict)
    incoming_entities: dict = field(default_factory=dict)
    fields_changed: list[str] = field(default_factory=list)
    fields_invalidated: list[str] = field(default_factory=list)
    derived_fields: dict = field(default_factory=dict)
    pending_fields_before: list[str] = field(default_factory=list)
    pending_fields_after: list[str] = field(default_factory=list)
    next_missing_field: str | None = None
    requirements_complete: bool = False
    needs_confirmation: bool = False
    confirmation_reason: str | None = None
    selected_action: str = "none"
    search_triggered: bool = False
    search_filters: dict = field(default_factory=dict)
    reason: str = ""
    permission_passed: bool = True
    context_applied: bool = False
    context_rejected_reason: str = ""
    invariant_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_family": self.intent_family,
            "active_flow_before": self.active_flow_before,
            "active_flow_after": self.active_flow_after,
            "fields_changed": self.fields_changed,
            "fields_invalidated": self.fields_invalidated,
            "derived_fields": self.derived_fields,
            "pending_fields_before": self.pending_fields_before,
            "pending_fields_after": self.pending_fields_after,
            "next_missing_field": self.next_missing_field,
            "requirements_complete": self.requirements_complete,
            "needs_confirmation": self.needs_confirmation,
            "confirmation_reason": self.confirmation_reason,
            "selected_action": self.selected_action,
            "search_triggered": self.search_triggered,
            "search_filters": self.search_filters,
            "reason": self.reason,
            "permission_passed": self.permission_passed,
            "context_applied": self.context_applied,
            "context_rejected_reason": self.context_rejected_reason,
            "invariant_violations": self.invariant_violations,
        }


def _effective_category(req: dict[str, Any]) -> str | None:
    explicit = (req.get("explicit") or {}).get("category")
    if explicit:
        return str(explicit).lower()
    derived = (req.get("derived") or {}).get("category")
    return str(derived).lower() if derived else None


def _resolve_field_value(
    field: str,
    message: str,
    parsed: dict[str, Any],
    entities: dict[str, Any],
) -> Any:
    """Generalized field resolver — typed text, chips, and voice use same path."""
    from app.ai.catalog_entity_resolver import resolve_entities
    from app.chatbot.assistant_intelligence import (
        detect_requested_category,
        parse_purpose_option,
        resolve_purpose_key,
    )

    if field == FIELD_PURPOSE_OR_CATEGORY:
        pk = (
            entities.get("purpose")
            or resolve_purpose_key(message)
            or parse_purpose_option(message)
        )
        if pk and str(pk).startswith("machine:"):
            return {"category": str(pk).split(":", 1)[1], "purpose": None}
        if pk:
            return {"purpose": pk, "category": None}
        cat = (
            entities.get("category")
            or entities.get("machine_type")
            or parsed.get("category")
            or detect_requested_category(message)
        )
        if cat:
            return {"category": cat, "purpose": None}
        return None

    if field == FIELD_CITY:
        return parsed.get("city") or entities.get("city")

    if field == FIELD_BRAND:
        resolved = resolve_entities(message, parsed=parsed)
        return resolved.get("brand") or entities.get("brand")

    if field == FIELD_MODEL:
        return parsed.get("model") or entities.get("model")

    if field == FIELD_BUDGET:
        return parsed.get("max_price") or entities.get("max_price") or entities.get("budget")

    if field == FIELD_LISTING_TYPE:
        return parsed.get("listing_type") or entities.get("listing_type")

    return None


def _pending_field_from_legacy(pending: dict | None) -> str | None:
    if not pending:
        return None
    mf = pending.get("missing_field") or ""
    missing = pending.get("missing") or []
    if mf == "machine_purpose" or FIELD_PURPOSE_OR_CATEGORY in missing:
        return FIELD_PURPOSE_OR_CATEGORY
    if mf == "city" or FIELD_CITY in missing:
        return FIELD_CITY
    if mf == "category":
        return FIELD_PURPOSE_OR_CATEGORY
    if missing:
        return missing[0]
    return mf or None


def _apply_explicit_value(
    req: dict[str, Any],
    key: str,
    value: Any,
    *,
    source: str,
    changed: list[str],
    invalidated: list[str],
) -> None:
    if value is None or value == "":
        return
    old = req["explicit"].get(key)
    if old != value:
        changed.append(key)
        req["explicit"][key] = value
        req["provenance"][key] = source
        req["revision"] = int(req.get("revision") or 0) + 1

        if key == "purpose":
            old_derived = (req.get("derived") or {}).get("category")
            prov_cat = req["provenance"].get("category")
            if prov_cat in (None, "derived_from_purpose") or not req["explicit"].get("category"):
                if old_derived:
                    invalidated.append("derived.category")
                req["derived"] = {"category": None}
                _recompute_derived_category(req)

        if key == "category":
            req["derived"]["category"] = None
            req["provenance"]["category"] = source


def _recompute_derived_category(req: dict[str, Any]) -> None:
    purpose = req["explicit"].get("purpose")
    explicit_cat = req["explicit"].get("category")
    result = resolve_derived_category(purpose, explicit_category=explicit_cat)

    if result.get("source") == "explicit":
        req["derived"]["category"] = None
        req["needs_confirmation"] = False
        return

    if result.get("needs_confirmation"):
        req["needs_confirmation"] = True
        req["confirmation_reason"] = "explicit_category_conflicts_with_purpose"
        req["derived"]["category"] = result.get("derived_recommendation")
        return

    if result.get("category") and not explicit_cat:
        req["derived"]["category"] = result["category"]
        if result.get("source") == "derived_from_purpose":
            req["provenance"]["category"] = "derived_from_purpose"
    req["needs_confirmation"] = bool(result.get("needs_confirmation"))


def _compute_pending_fields(req: dict[str, Any]) -> list[str]:
    """Derive pending from current normalized state — never accumulate stale fields."""
    if req.get("suspended"):
        return []

    pending: list[str] = []
    explicit = req.get("explicit") or {}
    has_purpose_or_cat = bool(
        explicit.get("purpose")
        or explicit.get("category")
        or (req.get("derived") or {}).get("category")
    )

    if not has_purpose_or_cat:
        pending.append(FIELD_PURPOSE_OR_CATEGORY)
    if not explicit.get("city"):
        pending.append(FIELD_CITY)

    # Optional fields never block search readiness but can be pending for recommendation flows
    # Brand/model/budget/listing_type are refinements — not mandatory for base search

    # Deduplicate preserve order
    seen: set[str] = set()
    out: list[str] = []
    for f in pending:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def assess_search_readiness(req: dict[str, Any]) -> tuple[bool, str | None, str]:
    """
    Canonical readiness: (category OR resolved purpose) AND city.
    Returns (complete, next_missing_field, reason).
    """
    if req.get("suspended"):
        return False, None, "requirement_flow_suspended"

    if req.get("needs_confirmation"):
        return False, FIELD_PURPOSE_OR_CATEGORY, "explicit_category_conflicts_with_purpose"

    explicit = req.get("explicit") or {}
    has_purpose_or_cat = bool(
        explicit.get("purpose")
        or explicit.get("category")
        or _effective_category(req)
    )
    has_city = bool(explicit.get("city"))

    if not has_purpose_or_cat:
        return False, FIELD_PURPOSE_OR_CATEGORY, "missing_purpose_or_category"
    if not has_city:
        return False, FIELD_CITY, "missing_city"

    return True, None, "all_required_fields_complete"


def build_search_filters(req: dict[str, Any]) -> dict[str, Any]:
    explicit = req.get("explicit") or {}
    filters: dict[str, Any] = {}
    cat = _effective_category(req)
    if cat:
        filters["category"] = cat
    if explicit.get("city"):
        filters["city"] = explicit["city"]
    if explicit.get("brand"):
        filters["brand"] = explicit["brand"]
    if explicit.get("model"):
        filters["model"] = explicit["model"]
    if explicit.get("budget") is not None:
        filters["max_price"] = explicit["budget"]
    if explicit.get("listing_type"):
        filters["listing_type"] = explicit["listing_type"]
    if explicit.get("purpose"):
        filters["purpose_key"] = explicit["purpose"]
    return {k: v for k, v in filters.items() if v is not None}


def _validate_invariants(req: dict[str, Any], decision: RequirementTransitionDecision) -> None:
    violations: list[str] = []
    explicit = req.get("explicit") or {}
    pending = list(req.get("pending_fields") or [])

    for field in (FIELD_PURPOSE_OR_CATEGORY, FIELD_CITY):
        if field == FIELD_PURPOSE_OR_CATEGORY:
            satisfied = bool(
                explicit.get("purpose")
                or explicit.get("category")
                or _effective_category(req)
            )
        else:
            satisfied = bool(explicit.get("city"))
        if satisfied and field in pending:
            violations.append(f"answered_field_still_pending:{field}")

    if len(pending) != len(set(pending)):
        violations.append("duplicate_pending_fields")

    if decision.requirements_complete and decision.next_missing_field:
        violations.append("complete_but_has_next_missing")

    if decision.requirements_complete and FIELD_PURPOSE_OR_CATEGORY in pending:
        violations.append("complete_but_purpose_pending")

    decision.invariant_violations = violations


def apply_requirement_transition(
    req: dict[str, Any],
    *,
    message: str,
    parsed: dict[str, Any] | None = None,
    entities: dict[str, Any] | None = None,
    intent: str | None = None,
    intent_family: str | None = None,
    pending_clarification: dict | None = None,
    active_flow: str | None = None,
    profile_hints: dict | None = None,
    block_previous_context: bool = False,
    permission_passed: bool = True,
) -> RequirementTransitionDecision:
    """
    Deterministic state transition for one incoming turn.
    Precedence: explicit entities > pending answer > session > profile hint.
    """
    parsed = parsed or parse_query(message)
    entities = entities or {}
    profile_hints = profile_hints or {}

    decision = RequirementTransitionDecision(
        intent_family=intent_family or "unknown",
        active_flow_before=req.get("active_flow"),
        state_before={
            "explicit": dict(req.get("explicit") or {}),
            "derived": dict(req.get("derived") or {}),
            "pending_fields": list(req.get("pending_fields") or []),
        },
        incoming_entities=dict(entities),
        pending_fields_before=list(req.get("pending_fields") or []),
        permission_passed=permission_passed,
    )

    if intent_family in PROTECTED_NON_SEARCH_FAMILIES:
        req["suspended"] = True
        decision.context_rejected_reason = f"protected_family:{intent_family}"
        decision.selected_action = "suspend_requirement_flow"
        decision.reason = "non_search_intent_suspends_requirement_collection"
        decision.active_flow_after = req.get("active_flow")
        decision.state_after = req
        return decision

    if req.get("suspended") and active_flow in MACHINE_REQUIREMENT_FLOWS:
        req["suspended"] = False
        decision.context_applied = True

    from app.ai.intent_signals import (
        current_message_requirement_entities,
        is_fresh_broad_machine_intent,
    )

    current_entities = current_message_requirement_entities(message, parsed, entities)
    previous_explicit = dict(req.get("explicit") or {})
    fresh_broad = is_fresh_broad_machine_intent(message, parsed, entities)
    should_clear_stale = fresh_broad or (
        block_previous_context and not current_entities
    )

    changed: list[str] = []
    invalidated: list[str] = []

    if should_clear_stale and (
        previous_explicit.get("category")
        or previous_explicit.get("city")
        or previous_explicit.get("purpose")
        or previous_explicit.get("brand")
    ):
        req.clear()
        req.update(empty_requirement_state())
        req["active_flow"] = active_flow or "machine_requirement_collection"
        invalidated = list(_EXPLICIT_KEYS)
        decision.context_rejected_reason = (
            "fresh_broad_intent_clears_stale_requirements"
            if fresh_broad
            else "block_previous_context_clears_stale_requirements"
        )

    # B. Pending field answer (state-driven, not phrase lists)
    pending_field = _pending_field_from_legacy(pending_clarification)
    if not pending_field and req.get("pending_fields"):
        pending_field = req["pending_fields"][0]

    effective_pending = pending_clarification or (
        pending_clarification_from_requirement(req, next_field=pending_field)
        if pending_field
        else None
    )

    if pending_field and effective_pending:
        from app.chatbot.assistant_intelligence import is_clarification_answer

        if is_clarification_answer(message, effective_pending, parsed=parsed):
            resolved = _resolve_field_value(pending_field, message, parsed, entities)
            if resolved is not None:
                if isinstance(resolved, dict):
                    for k, v in resolved.items():
                        if v:
                            _apply_explicit_value(
                                req, k, v, source="pending_answer",
                                changed=changed, invalidated=invalidated,
                            )
                elif pending_field == FIELD_CITY:
                    _apply_explicit_value(
                        req, "city", resolved, source="pending_answer",
                        changed=changed, invalidated=invalidated,
                    )
                elif pending_field == FIELD_BUDGET:
                    _apply_explicit_value(
                        req, "budget", resolved, source="pending_answer",
                        changed=changed, invalidated=invalidated,
                    )
                elif pending_field == FIELD_BRAND:
                    _apply_explicit_value(
                        req, "brand", resolved, source="pending_answer",
                        changed=changed, invalidated=invalidated,
                    )
                elif pending_field == FIELD_MODEL:
                    _apply_explicit_value(
                        req, "model", resolved, source="pending_answer",
                        changed=changed, invalidated=invalidated,
                    )
                elif pending_field == FIELD_LISTING_TYPE:
                    _apply_explicit_value(
                        req, "listing_type", resolved, source="pending_answer",
                        changed=changed, invalidated=invalidated,
                    )
                decision.context_applied = True

    # A. Explicit entities in current message (override previous)
    ent_map = {
        "purpose": entities.get("purpose") or parsed.get("purpose_key"),
        "category": entities.get("category") or entities.get("machine_type") or entities.get("machine_category"),
        "city": entities.get("city"),
        "brand": entities.get("brand"),
        "model": entities.get("model"),
        "budget": entities.get("max_price") or entities.get("budget"),
        "listing_type": entities.get("listing_type"),
    }
    parsed_map = {
        "category": parsed.get("category"),
        "city": parsed.get("city"),
        "brand": parsed.get("brand"),
        "model": parsed.get("model"),
        "budget": parsed.get("max_price"),
        "listing_type": parsed.get("listing_type"),
    }

    for key in _EXPLICIT_KEYS:
        val = ent_map.get(key) or parsed_map.get(key)
        if val is not None and val != "":
            _apply_explicit_value(req, key, val, source="user_explicit", changed=changed, invalidated=invalidated)

    # Purpose / machine revision — always evaluate (user can change work type mid-conversation)
    purpose_resolved = _resolve_field_value(FIELD_PURPOSE_OR_CATEGORY, message, parsed, entities)
    if isinstance(purpose_resolved, dict):
        new_purpose = purpose_resolved.get("purpose")
        new_cat = purpose_resolved.get("category")
        if new_purpose:
            from app.ai.purpose_taxonomy import category_compatible_with_purpose

            old_purpose = req["explicit"].get("purpose")
            old_cat = req["explicit"].get("category") or _effective_category(req)
            purpose_changed = new_purpose != old_purpose
            cat_incompatible = bool(
                old_cat and not category_compatible_with_purpose(old_cat, new_purpose)
            )
            if purpose_changed or cat_incompatible:
                if cat_incompatible and req["explicit"].get("category"):
                    req["explicit"]["category"] = None
                    req["provenance"]["category"] = None
                    req["derived"] = {"category": None}
                    if "category" not in invalidated:
                        invalidated.append("category")
                if not req["explicit"].get("purpose") or purpose_changed:
                    _apply_explicit_value(
                        req,
                        "purpose",
                        new_purpose,
                        source="user_explicit",
                        changed=changed,
                        invalidated=invalidated,
                    )
        elif new_cat and not req["explicit"].get("category"):
            _apply_explicit_value(
                req,
                "category",
                new_cat,
                source="user_explicit",
                changed=changed,
                invalidated=invalidated,
            )

    # Recompute derived category after any purpose/category change
    if "purpose" in changed or "category" in changed or invalidated:
        _recompute_derived_category(req)

    # Profile hints — suggest only, never silently override explicit
    if profile_hints.get("preferred_city") and not req["explicit"].get("city"):
        if profile_hints.get("city_hint_requires_confirmation"):
            pass  # never auto-apply
        elif not block_previous_context and not changed:
            pass  # profile not applied without confirmation

    # Set active flow
    if active_flow:
        req["active_flow"] = active_flow
    elif any(req["explicit"].get(k) for k in ("city", "category", "purpose")):
        req["active_flow"] = "machine_requirement_collection"

    # Pending fields from normalized state
    req["pending_fields"] = _compute_pending_fields(req)

    complete, next_missing, reason = assess_search_readiness(req)
    decision.requirements_complete = complete
    decision.next_missing_field = next_missing
    decision.reason = reason
    decision.fields_changed = changed
    decision.fields_invalidated = invalidated
    decision.derived_fields = dict(req.get("derived") or {})
    decision.pending_fields_after = list(req["pending_fields"])
    decision.needs_confirmation = bool(req.get("needs_confirmation"))
    decision.confirmation_reason = req.get("confirmation_reason")
    decision.search_filters = build_search_filters(req)
    decision.active_flow_after = req.get("active_flow")

    if complete and permission_passed and not req.get("needs_confirmation"):
        decision.selected_action = "search_machines"
        decision.search_triggered = True
    elif next_missing:
        decision.selected_action = "ask_missing_field"
        decision.search_triggered = False
    else:
        decision.selected_action = "clarify_requirements"
        decision.search_triggered = False

    decision.state_after = req
    _validate_invariants(req, decision)

    if fresh_broad or should_clear_stale or decision.search_triggered:
        print(
            "[req-context] "
            f"current_message_entities={current_entities} "
            f"previous_filters={previous_explicit} "
            f"context_reuse_allowed={not should_clear_stale} "
            f"final_filters={decision.search_filters or {}} "
            f"reason={decision.reason}"
        )

    return decision


def suggestions_for_missing_field(
    field: str,
    req: dict[str, Any],
    *,
    database=None,
) -> list[str]:
    """Generalized suggestion chips for the next missing field."""
    from app.ai.category_mapping import KNOWN_CITIES
    from app.ai.purpose_taxonomy import PURPOSE_TO_CATEGORIES
    from app.chatbot.assistant_intelligence import (
        chips_from_categories,
        purpose_clarification_chips,
    )

    explicit = req.get("explicit") or {}
    if field == FIELD_PURPOSE_OR_CATEGORY:
        purpose = explicit.get("purpose")
        if purpose:
            from app.ai.purpose_taxonomy import categories_for_purpose
            return chips_from_categories(categories_for_purpose(purpose)[:4])
        cats: list[str] = []
        for values in PURPOSE_TO_CATEGORIES.values():
            for c in values:
                if c not in cats:
                    cats.append(c)
        return purpose_clarification_chips()[:6] + chips_from_categories(cats[:4])

    if field == FIELD_CITY:
        city = explicit.get("city")
        if database is not None and city:
            try:
                from app.utils.machine_repository import available_categories_in_city
                avail = available_categories_in_city(database, city)
                if avail:
                    return chips_from_categories(avail[:6]) + ["Contact support"]
            except Exception:
                pass
        return [c.title() for c in KNOWN_CITIES[:8]] + ["Contact support"]

    return ["Contact support"]


def clarification_message_for_field(
    field: str,
    req: dict[str, Any],
    *,
    lang: str = "english",
) -> str:
    """Draft clarification text aligned with canonical requirement state."""
    explicit = req.get("explicit") or {}
    eff_cat = _effective_category(req)
    city = explicit.get("city")

    if field == FIELD_CITY:
        label = eff_cat or "machines"
        if lang == "english":
            return f"Which city should I search for {label}?"
        return f"{label} ke liye kaunsi city search karun?"

    if field == FIELD_PURPOSE_OR_CATEGORY:
        if city:
            city_title = str(city).title()
            if lang == "english":
                return f"Got it — {city_title}. Which machine type or work do you need there?"
            return f"Theek hai — {city_title}. Wahan kaunsi machine ya kaam ke liye chahiye?"
        if lang == "english":
            return "What work do you need the machine for, or which machine type?"
        return "Kaunsa kaam ya machine type chahiye?"

    if req.get("needs_confirmation"):
        if lang == "english":
            return (
                f"Your category ({explicit.get('category')}) and work purpose may not match. "
                f"Should I search for {explicit.get('category')} or "
                f"{(req.get('derived') or {}).get('category')}?"
            )
        return (
            f"Aapki category aur kaam match nahi kar rahe. "
            f"{explicit.get('category')} search karun ya "
            f"{(req.get('derived') or {}).get('category')}?"
        )

    return "Please share a few more details about the machine you need."


def pending_clarification_from_requirement(
    req: dict[str, Any],
    *,
    next_field: str | None = None,
) -> dict[str, Any] | None:
    """Build legacy pending_clarification dict from canonical requirement state."""
    field = next_field or (req.get("pending_fields") or [None])[0]
    if not field:
        return None

    explicit = req.get("explicit") or {}
    mf_map = {
        FIELD_PURPOSE_OR_CATEGORY: "machine_purpose",
        FIELD_CITY: "city",
        FIELD_BRAND: "category",
        FIELD_MODEL: "model",
        FIELD_BUDGET: "machine_purpose",
        FIELD_LISTING_TYPE: "machine_purpose",
    }
    return {
        "missing_field": mf_map.get(field, field),
        "type": "machine_purpose",
        "missing": list(req.get("pending_fields") or []),
        "source": "requirement_state_engine",
        "purpose_key": explicit.get("purpose"),
        "category": explicit.get("category") or (req.get("derived") or {}).get("category"),
        "city": explicit.get("city"),
    }
