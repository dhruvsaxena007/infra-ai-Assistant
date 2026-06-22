"""
Central intent-priority and context-eligibility gate.

Evaluates the current user message BEFORE enrichment, pending resume, universal
early exits, or machine search. Mechanism-level — not phrase-by-phrase patches.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any, Optional

from app.ai.query_parser import parse_query

_GATE_CTX: ContextVar[Optional[dict[str, Any]]] = ContextVar("context_routing_gate", default=None)

# Broad action families (priority order for blocking previous machine context)
FAMILY_FRUSTRATION = "frustration_or_abuse"
FAMILY_RETURN_REFUND = "return_refund_or_booking_problem"
FAMILY_SUPPORT = "support_or_issue"
FAMILY_DOCUMENT = "document_question"
FAMILY_IMAGE = "image_followup"
FAMILY_COMPARISON = "machine_comparison"
FAMILY_CITY_INVENTORY = "city_inventory"
FAMILY_SEARCH_REFINEMENT = "search_refinement"
FAMILY_MACHINE_SEARCH = "machine_search_or_requirement"
FAMILY_CONVERSATIONAL = "conversational"
FAMILY_UNKNOWN = "unknown"

_PROTECTED_FAMILIES = frozenset({
    FAMILY_FRUSTRATION,
    FAMILY_RETURN_REFUND,
    FAMILY_SUPPORT,
    FAMILY_DOCUMENT,
    FAMILY_IMAGE,
})

_CONTEXT_MACHINE_SEARCH = "machine_search"
_CONTEXT_COMPARISON = "comparison"
_CONTEXT_SUPPORT = "support"
_CONTEXT_PROFILE = "profile_hint"
_CONTEXT_BRAND_INVENTORY = "brand_inventory"
_CONTEXT_SELECTED_MACHINE = "selected_machine"

# Structural feature detectors (language families, not fixed sentences)
_ASSISTANT_DIRECTED_RE = re.compile(
    r"\b(?:you|u|your(?:self)?|aap(?:ka|ki|ke)?|tum(?:hara|hari|he)?|assistant|bot)\b",
    re.I,
)
_INSULT_STEM_RE = re.compile(
    r"\b(?:useless|worthless|stupid|dumb|idiot|fool|moron|hopeless|bekar|bekaar|pagal|"
    r"nonsense|garbage|trash|pathetic|incompetent|worst)\b",
    re.I,
)
_SUPPORT_ISSUE_RE = re.compile(
    r"\b(?:problem|issue|fault|defect|broken|malfunction|not\s+working|doesn'?t\s+work|"
    r"technical|repair|maintenance|complaint|help\s+me|support)\b",
    re.I,
)
_POST_TRANSACTION_RE = re.compile(
    r"\b(?:rented|hired|booked|ordered|my\s+booking|my\s+order|already\s+(?:rent|hire|book))\b",
    re.I,
)
_RETURN_REFUND_RE = re.compile(
    r"\b(?:refund|return|money\s+back|cancel\s+(?:booking|order)|wapas|paisa\s+waps)\b",
    re.I,
)
_PAYMENT_BOOKING_RE = re.compile(
    r"\b(?:payment|transaction|invoice|receipt|booking\s+confirm|amount\s+deducted|"
    r"double\s+charge|deposit|security\s+deposit)\b",
    re.I,
)
_DOCUMENT_RE = re.compile(
    r"\b(?:document|pdf|attachment|uploaded\s+file|uploaded\s+pdf)\b",
    re.I,
)
_IMAGE_REF_RE = re.compile(
    r"\b(?:this\s+image|uploaded\s+image|photo\s+i\s+sent|image\s+i\s+uploaded|"
    r"ye\s+photo|is\s+photo)\b",
    re.I,
)
_CITY_INVENTORY_RE = re.compile(
    r"(?:"
    r"(?:what|which)\s+(?:machines?|equipment|machinery)\s+(?:are\s+)?(?:available|there)"
    r"|(?:list|show)\s+(?:all\s+)?(?:machines?|equipment)\s+(?:in|near|around)"
    r"|(?:available|milega|milta|milegi)\s+(?:equipment|machines?)\s+(?:in|near)"
    r"|machines?\s+available\s+in"
    r"|(?:kaun|kon)\s+(?:si|se)\s+(?:machines?|equipment|machinery)"
    r"|(?:city|sheher)\s+me\s+(?:kaun|kon|kya)"
    r")",
    re.I,
)
_REFINEMENT_RE = re.compile(
    r"\b(?:cheaper|sasta|premium|higher\s+budget|lower\s+price|under\s+\d|"
    r"same\s+in|also\s+in|city\s+me\s+bhi|what\s+about|show\s+more|rent\s+only|buy\s+only|nearby|"
    r"brand\s+only|with\s+operator|bina\s+operator)\b",
    re.I,
)
_PLATFORM_HOWTO_RE = re.compile(
    r"\b(?:how\s+(?:does|do|to)|what\s+is\s+the\s+(?:process|way)|payment\s+work|"
    r"payment\s+kaise|kaise\s+pay|how\s+to\s+pay)\b",
    re.I,
)
_DEMONSTRATIVE_RE = re.compile(
    r"\b(?:this|that|it|its|these|those|ye|yeh|wahi|same)\b",
    re.I,
)
_EQUIPMENT_CONTEXT_RE = re.compile(
    r"\b(?:machine|equipment|machinery|listing|rental|booking)\b",
    re.I,
)


def _message_features(message: str, parsed: dict | None = None) -> dict[str, Any]:
    text = (message or "").strip()
    p = parsed or parse_query(text)
    lower = text.lower()
    return {
        "has_city": bool(p.get("city")),
        "has_category": bool(p.get("category")),
        "has_brand": bool(p.get("brand") or p.get("brands")),
        "has_listing_type": bool(p.get("listing_type")),
        "assistant_directed": bool(_ASSISTANT_DIRECTED_RE.search(text)),
        "insult_stem": bool(_INSULT_STEM_RE.search(text)),
        "support_issue": bool(_SUPPORT_ISSUE_RE.search(text)),
        "post_transaction": bool(_POST_TRANSACTION_RE.search(text)),
        "return_refund": bool(_RETURN_REFUND_RE.search(text)),
        "payment_booking": bool(_PAYMENT_BOOKING_RE.search(text)),
        "document": bool(_DOCUMENT_RE.search(text)),
        "image_ref": bool(_IMAGE_REF_RE.search(text)),
        "city_inventory": bool(
            _CITY_INVENTORY_RE.search(text)
            and p.get("city")
            and not p.get("category")
        ),
        "refinement": bool(_REFINEMENT_RE.search(text)),
        "demonstrative": bool(_DEMONSTRATIVE_RE.search(text)),
        "equipment_context": bool(_EQUIPMENT_CONTEXT_RE.search(text)),
        "word_count": len(text.split()),
        "parsed": p,
    }


def classify_message_family(
    message: str,
    *,
    active_flow: str | None = None,
    parsed: dict | None = None,
) -> dict[str, Any]:
    """
    Classify current message into a broad action family.
    Current explicit message is evaluated first — not enriched text.
    """
    text = (message or "").strip()
    feats = _message_features(text, parsed)
    p = feats["parsed"]

    family = FAMILY_UNKNOWN
    confidence = 0.5
    reason = "default"
    block_previous_context = False
    allow_machine_search = False

    if not text:
        return _pack(family, confidence, reason, feats, block_previous_context, allow_machine_search)

    if feats["assistant_directed"] and feats["insult_stem"]:
        return _pack(FAMILY_FRUSTRATION, 0.92, "assistant_directed_insult", feats, True, False)

    if feats["return_refund"]:
        return _pack(FAMILY_RETURN_REFUND, 0.88, "return_refund_signal", feats, True, False)

    if feats["payment_booking"] and _PLATFORM_HOWTO_RE.search(text) and not feats["return_refund"]:
        return _pack(FAMILY_SUPPORT, 0.86, "platform_payment_how_to", feats, True, False)

    if feats["payment_booking"] and feats["support_issue"]:
        return _pack(FAMILY_RETURN_REFUND, 0.9, "return_refund_or_payment_issue", feats, True, False)

    if feats["post_transaction"] and feats["support_issue"]:
        return _pack(FAMILY_SUPPORT, 0.9, "post_transaction_equipment_issue", feats, True, False)

    if feats["payment_booking"] and not p.get("category"):
        return _pack(FAMILY_RETURN_REFUND, 0.85, "payment_booking_without_search", feats, True, False)

    if feats["support_issue"] and (feats["equipment_context"] or feats["post_transaction"]):
        return _pack(FAMILY_SUPPORT, 0.88, "equipment_support_issue", feats, True, False)

    if feats["support_issue"] and feats["demonstrative"] and active_flow in (
        "machine_search", "machine_requirement_collection", "search_refinement", "brand_inventory",
    ):
        return _pack(FAMILY_SUPPORT, 0.86, "demonstrative_support_after_search", feats, True, False)

    if feats["document"]:
        return _pack(FAMILY_DOCUMENT, 0.86, "document_reference", feats, True, False)

    if feats["image_ref"]:
        return _pack(FAMILY_IMAGE, 0.84, "image_followup_reference", feats, True, False)

    if feats["city_inventory"]:
        return _pack(FAMILY_CITY_INVENTORY, 0.87, "city_wide_inventory", feats, False, True)

    if active_flow in ("machine_comparison",) or (
        p.get("brands") and len(p.get("brands") or []) >= 1
        and re.search(r"\b(?:compare|vs|versus|better|or|ya)\b", text, re.I)
    ):
        return _pack(FAMILY_COMPARISON, 0.82, "comparison_shape", feats, False, False)

    if feats["refinement"] and (
        feats["has_category"]
        or feats["has_city"]
        or active_flow in ("machine_search", "search_refinement", "brand_inventory", "machine_requirement_collection")
        or feats.get("parsed", {}).get("max_price") is not None
    ):
        return _pack(FAMILY_SEARCH_REFINEMENT, 0.84, "search_refinement", feats, False, True)

    if p.get("category") or p.get("city") or p.get("brand") or feats["has_listing_type"]:
        return _pack(FAMILY_MACHINE_SEARCH, 0.8, "explicit_search_entities", feats, False, True)

    if re.search(r"\b(?:rent|buy|hire|kiraye|chahiye|need|want|search|find|show)\b", text, re.I):
        if feats["equipment_context"] or p.get("listing_type"):
            from app.chatbot.assistant_intelligence import is_broad_vague_query

            block_stale = is_broad_vague_query(text, session_collected=None)
            reason = "fresh_broad_machine_request" if block_stale else "search_action_equipment"
            return _pack(FAMILY_MACHINE_SEARCH, 0.75, reason, feats, block_stale, False)

    if feats["assistant_directed"] and feats["word_count"] <= 12 and not feats["equipment_context"]:
        return _pack(FAMILY_CONVERSATIONAL, 0.78, "assistant_directed_social", feats, True, False)

    if active_flow in ("support_issue", "frustration_recovery") and feats["support_issue"]:
        return _pack(FAMILY_SUPPORT, 0.8, "support_flow_continuation", feats, True, False)

    # Social / intro / gratitude turns — must not arm requirement collection
    from app.ai.social_turn_detector import detect_social_turn

    social = detect_social_turn(text)
    if social:
        return _pack(
            FAMILY_CONVERSATIONAL,
            0.88,
            f"social_turn_{social.get('kind') or social.get('subtype') or 'conversational'}",
            feats,
            True,
            False,
        )

    from app.ai.universal_turn_engine import extract_user_name, is_greeting

    if extract_user_name(text) or is_greeting(text):
        return _pack(FAMILY_CONVERSATIONAL, 0.82, "user_intro_or_greeting", feats, True, False)

    return _pack(family, confidence, reason, feats, block_previous_context, allow_machine_search)


def _pack(
    family: str,
    confidence: float,
    reason: str,
    features: dict,
    block_previous_context: bool,
    allow_machine_search: bool,
) -> dict[str, Any]:
    return {
        "family": family,
        "confidence": confidence,
        "reason": reason,
        "features": features,
        "block_previous_search_context": family in _PROTECTED_FAMILIES or block_previous_context,
        "block_reference_enrich": family in _PROTECTED_FAMILIES,
        "allow_machine_search": allow_machine_search and family not in _PROTECTED_FAMILIES,
        "allow_pending_machine_resume": family not in _PROTECTED_FAMILIES,
    }


def should_apply_previous_context(
    current_family: str,
    *,
    active_flow: str | None = None,
    context_type: str,
    message_features: dict | None = None,
) -> tuple[bool, str]:
    """Whether a specific previous context type may influence this turn."""
    feats = message_features or {}
    flow = (active_flow or "").strip()

    if current_family in _PROTECTED_FAMILIES:
        return False, f"family_{current_family}_blocks_all_previous_context"

    if context_type == _CONTEXT_MACHINE_SEARCH:
        if current_family == FAMILY_SEARCH_REFINEMENT:
            return True, "refinement_reuses_search_context"
        if current_family == FAMILY_MACHINE_SEARCH and feats.get("refinement"):
            return True, "explicit_refinement"
        if feats.get("refinement") and flow in (
            "machine_search", "search_refinement", "machine_requirement_collection",
        ):
            return True, "refinement_with_active_machine_flow"
        if current_family == FAMILY_MACHINE_SEARCH and flow in (
            "machine_search", "search_refinement", "machine_requirement_collection",
        ):
            return True, "active_machine_flow_continuation"
        if current_family == FAMILY_CONVERSATIONAL:
            return False, "conversational_blocks_search_context"
        return False, "search_context_not_eligible_for_family"

    if context_type == _CONTEXT_COMPARISON:
        if current_family == FAMILY_COMPARISON or flow == "machine_comparison":
            return True, "comparison_continuation"
        return False, "comparison_context_not_eligible"

    if context_type == _CONTEXT_SUPPORT:
        if current_family in (FAMILY_SUPPORT, FAMILY_RETURN_REFUND) or flow == "support_issue":
            return True, "support_continuation"
        return False, "support_context_not_eligible"

    if context_type == _CONTEXT_PROFILE:
        if current_family == FAMILY_MACHINE_SEARCH and not feats.get("has_city"):
            return True, "profile_hint_for_ambiguous_search"
        return False, "profile_hint_not_eligible"

    if context_type == _CONTEXT_SELECTED_MACHINE:
        if current_family in (FAMILY_MACHINE_SEARCH, FAMILY_CONVERSATIONAL) and feats.get("demonstrative"):
            return True, "selected_machine_for_demonstrative"
        if current_family == FAMILY_SUPPORT:
            return False, "support_blocks_selected_machine_search"
        return feats.get("demonstrative", False), "demonstrative_reference_check"

    return False, "unknown_context_type"


def sanitize_router_context(
    router_ctx: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    """Strip ineligible previous machine context from router/classifier context."""
    if not gate.get("block_previous_search_context"):
        return router_ctx

    clean = dict(router_ctx)
    clean["last_filters"] = {}
    clean["last_search_filters"] = {}
    clean["last_results"] = {}
    collected = dict(clean.get("collected_fields") or {})
    for key in ("category", "city", "brand", "brands", "budget", "listing_type", "purpose"):
        collected.pop(key, None)
    clean["collected_fields"] = collected
    clean["_context_blocked"] = True
    clean["_context_blocked_reason"] = gate.get("reason") or "protected_family"
    return clean


def should_allow_reference_enrich(
    gate: dict[str, Any],
    *,
    message: str,
    has_last_machines: bool,
) -> tuple[bool, str]:
    if gate.get("block_reference_enrich"):
        return False, f"family_{gate.get('family')}_blocks_reference_enrich"
    if not has_last_machines:
        return False, "no_last_machines"
    feats = _message_features(message)
    if not feats.get("demonstrative"):
        return False, "no_demonstrative_reference"
    if feats.get("support_issue") or feats.get("post_transaction"):
        return False, "support_features_block_enrich"
    allowed, reason = should_apply_previous_context(
        gate.get("family") or FAMILY_UNKNOWN,
        context_type=_CONTEXT_MACHINE_SEARCH,
        message_features=feats,
    )
    if not allowed:
        return False, f"search_context_ineligible:{reason}"
    return True, "demonstrative_search_followup"


def family_to_intent_hint(family: str) -> str | None:
    """Map family to coarse intent for protected short-circuit routing."""
    return {
        FAMILY_FRUSTRATION: "frustration",
        FAMILY_RETURN_REFUND: "refund_return",
        FAMILY_SUPPORT: "order_issue",
        FAMILY_DOCUMENT: "document_question",
        FAMILY_IMAGE: "image_search_followup",
        FAMILY_CITY_INVENTORY: "machine_availability",
        FAMILY_COMPARISON: "machine_comparison",
    }.get(family)


def family_blocks_universal_early_exit(family: str) -> bool:
    return family in _PROTECTED_FAMILIES or family == FAMILY_CITY_INVENTORY


def set_current_gate(gate: dict[str, Any]) -> Any:
    return _GATE_CTX.set(gate)


def get_current_gate() -> dict[str, Any] | None:
    return _GATE_CTX.get()


def reset_current_gate(token: Any) -> None:
    _GATE_CTX.reset(token)


def evaluate_routing_gate(
    message: str,
    *,
    active_flow: str | None = None,
    parsed: dict | None = None,
) -> dict[str, Any]:
    """Evaluate gate and store in context var for the request."""
    gate = classify_message_family(message, active_flow=active_flow, parsed=parsed)
    set_current_gate(gate)
    return gate


def isolate_context_on_flow_switch(
    state: dict[str, Any],
    new_flow: str,
    *,
    switch_reason: str | None = None,
) -> dict[str, Any]:
    """Clear machine search fields when switching to support/frustration/document flows."""
    protected_flows = {"support_issue", "frustration_recovery", "document_qa", "out_of_scope"}
    if new_flow not in protected_flows:
        return state

    snapshot = {
        "last_search_filters": dict(state.get("last_search_filters") or {}),
        "collected_machine_fields": {
            k: v for k, v in (state.get("collected_fields") or {}).items()
            if k in ("category", "city", "brand", "brands", "budget", "listing_type", "purpose")
            and v
        },
    }
    state["_isolated_search_snapshot"] = snapshot
    state["last_search_filters"] = {}
    collected = dict(state.get("collected_fields") or {})
    for key in ("category", "city", "brand", "brands", "budget", "listing_type", "purpose"):
        collected.pop(key, None)
    state["collected_fields"] = collected
    if switch_reason:
        state["_switch_reason"] = switch_reason
    state["_context_isolated"] = True
    return state
