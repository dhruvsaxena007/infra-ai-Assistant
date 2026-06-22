"""
Central intent router for InfraForge Marketplace Assistant.

Classifies user messages before machine search runs. Support, refund, payment,
and out-of-scope queries must never trigger search.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.query_parser import parse_query
from app.chatbot.assistant_intelligence import (
    is_booking_guidance_query,
    is_broad_vague_query,
    is_greeting,
    is_recommendation_query,
)

# ---------------------------------------------------------------------------
# Pattern groups (order matters — more specific intents checked first)
# ---------------------------------------------------------------------------

_HUMAN_HANDOVER_RE = re.compile(
    r"(?:"
    r"talk\s+to\s+(?:support|human|agent|person)"
    r"|connect\s+(?:me\s+)?(?:to|with)\s+support"
    r"|(?:need|want)\s+(?:help\s+from\s+)?support"
    r"|human\s+(?:support|agent|handover)"
    r"|call\s+support|speak\s+to\s+(?:someone|support)"
    r"|customer\s+(?:care|support)"
    r"|support\s+(?:team|se\s+baat|chahiye)"
    r")",
    re.I,
)

_REFUND_RETURN_RE = re.compile(
    r"(?:"
    r"\brefund\b|\breturn\b|money\s+back|payment\s+wapas|paisa\s+waps"
    r"|machine\s+return|return\s+(?:the\s+)?machine|wapas\s+karna"
    r"|cancel\s+(?:booking|order).{0,30}(?:refund|money)"
    r"|refund\s+kab|return\s+karni"
    r")",
    re.I,
)

_PAYMENT_ISSUE_RE = re.compile(
    r"(?:"
    r"payment\s+(?:failed|fail|stuck|pending|issue|problem)"
    r"|amount\s+deducted|money\s+deducted|paisa\s+kat\s+gaya"
    r"|security\s+deposit\s+(?:issue|problem|refund|not\s+returned)"
    r"|payment\s+ho\s+gaya.{0,40}(?:confirm|booking).{0,20}(?:nahi|not)"
    r"|booking\s+confirm\s+nahi|transaction\s+(?:failed|issue)"
    r"|double\s+(?:payment|charge)|charged\s+twice"
    r")",
    re.I,
)

_ORDER_SUPPORT_RE = re.compile(
    r"(?:"
    r"(?:ordered|order\s+ki|booked|booking).{0,50}(?:problem|issue|help|complaint)"
    r"|(?:problem|issue).{0,40}(?:order|booking|machine\s+order)"
    r"|meri\s+booking.{0,30}(?:issue|problem)"
    r"|booking\s+ke\s+baad.{0,30}(?:machine|delivery).{0,20}(?:nahi|not|delay)"
    r"|machine\s+(?:nahi\s+aayi|not\s+(?:delivered|arrived))"
    r"|order\s+(?:status|problem|issue|help)"
    r"|delivery\s+(?:issue|problem|delay|late)"
    r")",
    re.I,
)

_COMPLAINT_RE = re.compile(
    r"(?:"
    r"\bcomplaint\b|raise\s+(?:a\s+)?complaint|file\s+complaint"
    r"|report\s+(?:seller|owner|listing|fraud)"
    r"|fraud|scam|cheat"
    r"|owner\s+(?:misbehav|fraud)"
    r")",
    re.I,
)

_BOOKING_STATUS_RE = re.compile(
    r"(?:"
    r"(?:booking|order)\s+status|track\s+(?:my\s+)?(?:order|booking)"
    r"|where\s+is\s+my\s+(?:order|booking|machine)"
    r"|kab\s+(?:aayega|milega|deliver)|delivery\s+status"
    r"|booking\s+confirm\s+hui\s+kya|order\s+id"
    r")",
    re.I,
)

_RENTAL_POLICY_RE = re.compile(
    r"(?:"
    r"(?:rental|rent|booking|cancellation|return)\s+policy"
    r"|security\s+deposit\s+(?:policy|kitna|amount|rules)"
    r"|refund\s+policy|cancellation\s+(?:policy|charge|fee)"
    r"|terms\s+(?:and\s+conditions|of\s+rental)"
    r")",
    re.I,
)

_SELLER_CONTACT_RE = re.compile(
    r"(?:"
    r"(?:owner|seller).{0,20}(?:contact|number|phone|baat|call)"
    r"|contact\s+(?:the\s+)?(?:owner|seller)"
    r"|(?:owner|seller)\s+ka\s+(?:number|contact)"
    r"|owner\s+se\s+baat|seller\s+se\s+baat"
    r"|baat\s+karni\s+hai.{0,30}(?:owner|seller)"
    r"|machine\s+owner\s+contact"
    r")",
    re.I,
)

_DOCUMENT_QA_RE = re.compile(
    r"(?:"
    r"(?:document|pdf|file|attachment).{0,30}(?:question|ask|me|mein)"
    r"|(?:is|in)\s+(?:document|pdf|file).{0,30}(?:kya|what|which)"
    r"|uploaded\s+(?:document|pdf)"
    r")",
    re.I,
)

_AVAILABILITY_RE = re.compile(
    r"(?:"
    r"(?:is\s+(?:this|it|ye)|ye\s+machine|this\s+machine).{0,30}(?:available|availab)"
    r"|(?:available|availab).{0,20}(?:in|me|mein)\s+\w+"
    r"|kya\s+(?:ye|yeh|ye\s+machine).{0,20}(?:available|milega|milti)"
    r")",
    re.I,
)

_OUT_OF_SCOPE_RE = re.compile(
    r"(?:"
    r"weather|temperature|forecast|rain\s+today"
    r"|politics|election|prime\s+minister|who\s+won"
    r"|cricket\s+score|ipl|football\s+match"
    r"|movie|bollywood|netflix|recipe|horoscope"
    r"|bitcoin|stock\s+market|homework|essay"
    r"|girlfriend|boyfriend|dating\s+advice"
    r")",
    re.I,
)

_ORDER_ID_RE = re.compile(
    r"\b(?:order\s*(?:id|#)?|booking\s*(?:id|#)?)\s*[:#]?\s*([A-Za-z0-9\-]{4,20})\b",
    re.I,
)


def _empty_entities() -> dict[str, Any]:
    return {
        "order_id": None,
        "machine_type": None,
        "city": None,
        "issue_type": None,
    }


def _extract_order_id(message: str) -> Optional[str]:
    m = _ORDER_ID_RE.search(message or "")
    return m.group(1).strip() if m else None


def _has_search_signals(parsed: dict, message: str) -> bool:
    """True when message clearly requests a machine listing search."""
    if parsed.get("category") or parsed.get("city") or parsed.get("region"):
        return True
    if parsed.get("brand") or parsed.get("model"):
        return True
    if parsed.get("max_price") is not None:
        return True
    if re.search(
        r"\b(?:excavator|jcb|crane|roller|loader|truck|drill|grader|bulldozer|mixer)\b",
        message,
        re.I,
    ):
        return True
    if re.search(r"\b(?:in|me|mein|under|below)\b", message, re.I) and re.search(
        r"\d", message
    ):
        return True
    return False


def _is_support_priority(message: str) -> bool:
    """Support/refund/payment phrases override incidental machine words."""
    return bool(
        _REFUND_RETURN_RE.search(message)
        or _PAYMENT_ISSUE_RE.search(message)
        or _ORDER_SUPPORT_RE.search(message)
        or _COMPLAINT_RE.search(message)
        or _BOOKING_STATUS_RE.search(message)
    )


def route_user_intent(
    message: str,
    context: Optional[dict] = None,
    image_context: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Classify user input into a marketplace intent.

    Returns intent metadata including whether machine search should run.
    """
    text = (message or "").strip()
    ctx = context or {}
    last_filters = ctx.get("last_filters") or {}
    entities = _empty_entities()
    order_id = _extract_order_id(text)
    if order_id:
        entities["order_id"] = order_id

    parsed = parse_query(text)
    if parsed.get("category"):
        entities["machine_type"] = parsed.get("category")
    if parsed.get("city"):
        entities["city"] = parsed.get("city")

    base: dict[str, Any] = {
        "intent": "unknown",
        "confidence": "low",
        "should_search_machines": False,
        "requires_handover": False,
        "missing_fields": [],
        "entities": entities,
        "assistant_mode": "clarification",
        "parsed": parsed,
    }

    if not text:
        base.update(
            intent="clarification",
            confidence="high",
            assistant_mode="clarification",
            missing_fields=["machine_type", "city"],
        )
        return base

    if is_greeting(text):
        base.update(
            intent="greeting",
            confidence="high",
            assistant_mode="greeting",
        )
        return base

    # --- Support & marketplace operations (never search) --------------------
    if _HUMAN_HANDOVER_RE.search(text):
        base.update(
            intent="human_handover",
            confidence="high",
            assistant_mode="handover",
            requires_handover=True,
        )
        return base

    if _REFUND_RETURN_RE.search(text):
        entities["issue_type"] = "refund"
        missing = [] if order_id else ["order_id"]
        base.update(
            intent="refund_return",
            confidence="high",
            assistant_mode="refund_return",
            requires_handover=True,
            missing_fields=missing,
            entities=entities,
        )
        return base

    if _PAYMENT_ISSUE_RE.search(text):
        entities["issue_type"] = "payment"
        missing = [] if order_id else ["order_id"]
        base.update(
            intent="payment_issue",
            confidence="high",
            assistant_mode="payment_issue",
            requires_handover=True,
            missing_fields=missing,
            entities=entities,
        )
        return base

    if _ORDER_SUPPORT_RE.search(text) and not _has_search_signals(parsed, text):
        entities["issue_type"] = "order"
        missing = [] if order_id else ["order_id"]
        base.update(
            intent="order_support",
            confidence="high",
            assistant_mode="support",
            requires_handover=True,
            missing_fields=missing,
            entities=entities,
        )
        return base

    if _is_support_priority(text):
        intent = "order_support"
        if _REFUND_RETURN_RE.search(text):
            intent = "refund_return"
            entities["issue_type"] = "refund"
        elif _PAYMENT_ISSUE_RE.search(text):
            intent = "payment_issue"
            entities["issue_type"] = "payment"
        elif _COMPLAINT_RE.search(text):
            intent = "complaint_issue"
            entities["issue_type"] = "complaint"
        else:
            entities["issue_type"] = "order"
        missing = [] if order_id else ["order_id"]
        base.update(
            intent=intent,
            confidence="high",
            assistant_mode=intent if intent != "order_support" else "support",
            requires_handover=True,
            missing_fields=missing,
            entities=entities,
        )
        return base

    if _COMPLAINT_RE.search(text):
        entities["issue_type"] = "complaint"
        base.update(
            intent="complaint_issue",
            confidence="high",
            assistant_mode="support",
            requires_handover=True,
            missing_fields=[] if order_id else ["order_id"],
            entities=entities,
        )
        return base

    if _BOOKING_STATUS_RE.search(text):
        entities["issue_type"] = "booking_status"
        base.update(
            intent="booking_status",
            confidence="high",
            assistant_mode="support",
            requires_handover=True,
            missing_fields=[] if order_id else ["order_id"],
            entities=entities,
        )
        return base

    if _RENTAL_POLICY_RE.search(text):
        base.update(
            intent="rental_policy",
            confidence="high",
            assistant_mode="support",
            requires_handover=False,
        )
        return base

    if _SELLER_CONTACT_RE.search(text) and not is_booking_guidance_query(text):
        has_machine_ctx = bool(
            last_filters.get("category")
            or last_filters.get("brand")
            or (image_context or {}).get("detected_machine_type")
        )
        base.update(
            intent="seller_contact",
            confidence="high",
            assistant_mode="handover" if has_machine_ctx else "support",
            requires_handover=has_machine_ctx,
            missing_fields=[] if has_machine_ctx else ["machine_listing"],
        )
        return base

    if _OUT_OF_SCOPE_RE.search(text):
        base.update(
            intent="out_of_scope",
            confidence="high",
            assistant_mode="out_of_scope",
        )
        return base

    if _DOCUMENT_QA_RE.search(text):
        base.update(
            intent="document_question",
            confidence="medium",
            assistant_mode="document_qa",
        )
        return base

    # --- Machine marketplace intents ----------------------------------------
    if is_recommendation_query(text):
        base.update(
            intent="machine_recommendation",
            confidence="high",
            should_search_machines=True,
            assistant_mode="recommendation",
        )
        return base

    if _AVAILABILITY_RE.search(text):
        base.update(
            intent="machine_availability",
            confidence="high",
            should_search_machines=True,
            assistant_mode="machine_search",
        )
        return base

    if _has_search_signals(parsed, text) and not _is_support_priority(text):
        base.update(
            intent="machine_search",
            confidence="high" if parsed.get("city") and parsed.get("category") else "medium",
            should_search_machines=True,
            assistant_mode="machine_search",
        )
        return base

    if is_broad_vague_query(text) or re.match(
        r"^(?:machine|machines|equipment|saman)(?:\s+chahiye)?[\s!.?]*$",
        text,
        re.I,
    ):
        base.update(
            intent="clarification",
            confidence="high",
            assistant_mode="clarification",
            missing_fields=["machine_type", "city"],
        )
        return base

    # Weak service signal — ask what they need instead of searching.
    if not _has_search_signals(parsed, text):
        base.update(
            intent="unknown",
            confidence="medium",
            assistant_mode="clarification",
            missing_fields=["intent"],
        )
        return base

    base.update(
        intent="machine_search",
        confidence="low",
        should_search_machines=True,
        assistant_mode="machine_search",
    )
    return base
