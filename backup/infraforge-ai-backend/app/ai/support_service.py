"""
Backward-compatible re-exports — use support_response_service for new code.
"""

from app.ai.support_response_service import (  # noqa: F401
    NON_SEARCH_INTENTS,
    UNKNOWN_CHIPS,
    build_handover as build_handover_payload,
    build_response as build_support_response,
    is_non_search_intent as is_support_intent,
)

# Legacy intent name mapping for older callers
_INTENT_ALIASES = {
    "order_support": "order_issue",
    "complaint_issue": "complaint",
    "human_handover": "support_request",
    "seller_contact": "contact_owner",
    "booking_status": "order_issue",
    "rental_policy": "security_deposit",
}


def build_support_response_legacy(intent: str, **kwargs):
    from app.ai.support_response_service import build_response
    return build_response(_INTENT_ALIASES.get(intent, intent), **kwargs)
