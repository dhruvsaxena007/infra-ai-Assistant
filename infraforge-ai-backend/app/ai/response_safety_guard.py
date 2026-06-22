"""
Response safety — prevent unverified booking/rental/contact claims.
"""

from __future__ import annotations

import re
from typing import Any

_UNVERIFIED_BOOKING_CLAIM_RE = re.compile(
    r"\b(?:you(?:'ve|\s+have)\s+(?:rented|booked|ordered|hired)|"
    r"your\s+(?:rental|booking)(?:\s+for\s+[^.!?]{0,40})?\s+(?:is|has\s+been)\s+(?:confirmed|active|complete)|"
    r"(?:return|refund)\s+(?:is\s+)?(?:initiated|processed|started)|"
    r"(?:i\s+)?(?:contacted|reached)\s+(?:the\s+)?owner)\b",
    re.I,
)

_SUPPORT_FAMILIES = frozenset({
    "support_or_issue",
    "return_refund_or_booking_problem",
    "frustration_or_abuse",
})

_SUPPORT_INTENTS = frozenset({
    "order_issue", "refund_return", "payment_issue", "complaint",
    "support_request", "human_handover", "delivery_logistics",
    "invoice_issue", "security_deposit", "frustration", "contact_owner",
})


def _has_booking_confirmation(known: dict[str, Any]) -> bool:
    sup = known.get("last_support_context") or {}
    collected = known.get("collected_fields") or {}
    return bool(
        sup.get("booking_id")
        or sup.get("transaction_id")
        or sup.get("order_id")
        or collected.get("booking_id")
        or collected.get("transaction_id")
        or collected.get("order_id")
    )


def build_fact_constraints(
    *,
    intent: str | None = None,
    response_goal: str | None = None,
    known_context: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    intent_family: str | None = None,
) -> dict[str, Any]:
    """Fact tiers the response layer must respect."""
    known = known_context or {}
    tool = tool_result or {}
    intent = (intent or "").lower()
    family = intent_family or ""

    has_listings = bool(tool.get("machines"))
    has_selection = bool(known.get("selected_machine"))
    has_booking = _has_booking_confirmation(known)

    constraints = {
        "listing_facts_only": has_listings and not has_booking,
        "selected_machine_not_booked": has_selection and not has_booking,
        "booking_unconfirmed": not has_booking,
        "must_not_claim": [],
        "must_ask_for": [],
        "false_claim_guard_applied": True,
    }

    support_turn = intent in _SUPPORT_INTENTS or family in _SUPPORT_FAMILIES
    if support_turn and not has_booking:
        constraints["must_not_claim"] = [
            "user_has_completed_rental",
            "user_has_active_booking",
            "return_or_refund_initiated",
            "owner_already_contacted",
        ]
        constraints["must_ask_for"] = ["booking_id_or_transaction_id"]
    elif has_listings and not has_booking:
        constraints["must_not_claim"] = [
            "user_has_completed_rental",
            "return_or_refund_initiated",
        ]

    return constraints


def apply_false_claim_guard(
    message: str,
    *,
    constraints: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """Strip or soften unverified booking claims from draft text."""
    text = (message or "").strip()
    if not text or not constraints:
        return text, False

    if not constraints.get("booking_unconfirmed") and not constraints.get("must_not_claim"):
        return text, False

    if _UNVERIFIED_BOOKING_CLAIM_RE.search(text):
        cleaned = _UNVERIFIED_BOOKING_CLAIM_RE.sub("", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .,;")
        if not cleaned or len(cleaned) < 12:
            cleaned = (
                "I can help with that. Please share your booking or transaction ID "
                "so our team can verify the details."
            )
        elif constraints.get("must_ask_for"):
            cleaned = (
                f"{cleaned} Please share your booking or transaction ID so we can verify."
            )
        return cleaned, True

    return text, False


def must_include_for_response_plan(constraints: dict[str, Any]) -> list[str]:
    includes: list[str] = []
    if constraints.get("booking_unconfirmed"):
        includes.append("never_claim_booking_or_rental_without_confirmation")
    if constraints.get("selected_machine_not_booked"):
        includes.append("selected_machine_is_not_confirmed_booking")
    if constraints.get("listing_facts_only"):
        includes.append("search_results_are_listings_not_user_bookings")
    for item in constraints.get("must_not_claim") or []:
        includes.append(f"must_not_claim:{item}")
    return includes
