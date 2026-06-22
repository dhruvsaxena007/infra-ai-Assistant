"""
Layered marketplace intent classifier.

Layer 1: deterministic keyword/rule patterns (no API)
Layer 2: fuzzy token normalization via rapidfuzz
Layer 3: optional Groq JSON classification when rule confidence is low
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from rapidfuzz import fuzz, process

from app.ai.query_parser import parse_query
from app.chatbot.assistant_intelligence import (
    is_booking_guidance_query,
    is_broad_vague_query,
    is_greeting,
    is_recommendation_query,
)
from app.core.config import settings

# ---------------------------------------------------------------------------
# Allowed intents
# ---------------------------------------------------------------------------

ALL_INTENTS = frozenset({
    "greeting",
    "machine_search",
    "machine_availability",
    "machine_recommendation",
    "rent_machine",
    "buy_machine",
    "compare_machine",
    "price_query",
    "contact_owner",
    "booking_help",
    "order_issue",
    "refund_return",
    "payment_issue",
    "delivery_logistics",
    "security_deposit",
    "document_question",
    "image_search_followup",
    "complaint",
    "support_request",
    "general_marketplace_help",
    "platform_how_to",
    "out_of_scope",
    "unknown",
})

SEARCH_INTENTS = frozenset({
    "machine_search",
    "machine_availability",
    "machine_recommendation",
    "rent_machine",
    "buy_machine",
    "image_search_followup",
    "price_query",
})

NON_SEARCH_INTENTS = ALL_INTENTS - SEARCH_INTENTS

# Marketplace vocabulary for fuzzy correction (token -> canonical)
_FUZZY_VOCAB: dict[str, str] = {
    "refnd": "refund", "refund": "refund", "return": "return", "wapas": "refund",
    "paymnt": "payment", "payment": "payment", "paisa": "payment",
    "bookng": "booking", "booking": "booking", "order": "order",
    "machin": "machine", "machine": "machine", "machines": "machine",
    "excavator": "excavator", "excvator": "excavator", "jcb": "jcb",
    "crane": "crane", "roller": "roller", "loader": "loader",
    "deliver": "delivery", "delivery": "delivery", "transport": "transport",
    "deposit": "deposit", "invoice": "invoice", "receipt": "receipt",
    "support": "support", "help": "help", "complaint": "complaint",
    "owner": "owner", "seller": "seller", "contact": "contact",
    "rent": "rent", "kiraye": "rent", "kiraya": "rent", "buy": "buy",
    "purchase": "buy", "refund": "refund", "cancel": "cancel",
    "status": "status", "issue": "issue", "problem": "problem",
    "failed": "failed", "deducted": "deducted", "confirm": "confirm",
}

# Rule groups: (intent, compiled_regex, base_score)
_RULES: list[tuple[str, re.Pattern, float]] = []

def _add(intent: str, pattern: str, score: float = 0.85) -> None:
    _RULES.append((intent, re.compile(pattern, re.I), score))


# --- Support / business (high priority) ------------------------------------
_add("support_request", r"talk\s+to\s+support|connect.*support|customer\s+care|support\s+chahiye|human\s+agent", 0.92)
_add("refund_return", r"\brefund\b|money\s+back|payment\s+wapas|paisa\s+waps|machine\s+return|return\s+karni|return\s+request|cancel.*refund|refund\s+kab|order\s+cancel", 0.9)
_add("payment_issue", r"payment\s+(?:failed|fail|stuck|pending|issue)|amount\s+deducted|paisa\s+kat|double\s+charge|transaction\s+(?:failed|issue)|payment\s+ho\s+gaya.*(?:confirm|booking).*(?:nahi|not)|booking\s+confirm\s+nahi\s+hui", 0.9)
_add("payment_issue", r"invoice\s+(?:nahi|not|missing|chahiye)|receipt\s+(?:nahi|not|missing|chahiye)|invoice\s+chahiye|receipt\s+chahiye", 0.88)
_add("security_deposit", r"security\s+deposit|deposit\s+(?:issue|refund|policy|kitna|amount)", 0.88)
_add("order_issue", r"(?:ordered|booked|booking).{0,60}(?:problem|issue|help|wrong|delay)|(?:problem|issue).{0,40}(?:order|booking)|meri\s+booking.*issue|machine\s+(?:nahi\s+aayi|abhi\s+tak\s+nahi|not\s+delivered|wrong\s+deliver\w*)|abhi\s+tak\s+nahi\s+aayi|wrong\s+machine\s+deliver\w*|rental\s+start\s+nahi", 0.9)
_add("order_issue", r"order\s+status|booking\s+status|status\s+kya\s+hai|kab\s+(?:aayega|milega|deliver)", 0.85)
_add("complaint", r"\bcomplaint\b|raise\s+complaint|report\s+(?:seller|owner|fraud)|fraud|scam", 0.88)
_add("delivery_logistics", r"deliver|delivery\s+(?:charge|cost|kab)|transport\s+(?:charge|kaun|cost)|site\s+par\s+machine|pickup\s+kaise|machine\s+kab\s+(?:aayegi|deliver)", 0.87)
_add("contact_owner", r"owner\s+se\s+baat|seller\s+se\s+baat|contact\s+owner|owner\s+ka\s+number|seller\s+ka\s+number|seller\s+contact|machine\s+owner", 0.88)

# --- Platform / help -------------------------------------------------------
_add("platform_how_to", r"kaise\s+(?:book|rent|kiraye|contact|add|list|pay|payment)|how\s+(?:to|do\s+i)\s+(?:book|rent|contact|pay|list)|machine\s+kaise\s+book|listing\s+kaise|seller\s+kaise\s+bane|payment\s+kaise", 0.86)
_add("general_marketplace_help", r"what\s+can\s+you\s+do|how\s+does\s+infraforge|infraforge\s+kaise|kaise\s+kaam\s+karta|services\s+kya|mujhe\s+help|help\s+me|help\s+chahiye|kya\s+kar\s+sakte|kaam\s+karta\s+hai", 0.84)
_add("document_question", r"document|pdf|attachment.*question|uploaded\s+(?:pdf|document)", 0.8)
_add("booking_help", r"how\s+to\s+rent|booking\s+process|rent\s+kaise|kiraye\s+kaise|proceed\s+with\s+booking", 0.82)

# --- Out of scope ----------------------------------------------------------
_add("out_of_scope", r"weather|temperature|forecast|politics|election|prime\s+minister|joke|tell\s+me\s+a\s+joke|cricket\s+score|movie|recipe|horoscope|bitcoin|homework", 0.92)

# --- Machine intents -------------------------------------------------------
_add("machine_recommendation", r"best\s+machine|recommend|suggest|kaunsi\s+machine|project\s+ke\s+liye", 0.86)
_add("compare_machine", r"\bcompare\b|comparison|difference\s+between", 0.82)
_add("price_query", r"(?:price|rate|cost|kitna|budget).{0,30}(?:excavator|jcb|crane|roller|machine)|(?:excavator|jcb|crane).{0,20}(?:price|rate|cost)", 0.8)
_add("rent_machine", r"\b(?:rent|hire|kiraye|kiraya)\b", 0.75)
_add("buy_machine", r"\b(?:buy|purchase|khareed)\b", 0.75)
_add("machine_availability", r"(?:is\s+(?:this|it|ye)|ye\s+machine).{0,30}available|available.{0,20}(?:in|me|mein)|kya\s+ye.{0,20}(?:available|milega)", 0.82)
_add("image_search_followup", r"this\s+machine|ye\s+machine|same\s+machine|this\s+type|ye\s+wali", 0.78)

_ORDER_ID_RE = re.compile(
    r"\b(?:order|booking)\s*(?:id|#)?\s*[:#]?\s*([A-Za-z0-9\-]{4,24})\b", re.I,
)

_GROQ_LOW_CONFIDENCE = 0.55


def _empty_result(intent: str = "unknown", reason: str = "") -> dict[str, Any]:
    return {
        "intent": intent,
        "confidence": 0.0,
        "should_search_machines": False,
        "requires_clarification": False,
        "requires_handover": False,
        "entities": {},
        "reason": reason,
        "layer": "rules",
    }


def _fuzzy_normalize_message(message: str) -> str:
    """Layer 2: fix common typos token-by-token."""
    tokens = re.findall(r"[A-Za-z0-9]+", message.lower())
    if not tokens:
        return message
    vocab_keys = list(_FUZZY_VOCAB.keys())
    fixed: list[str] = []
    for tok in tokens:
        if tok in _FUZZY_VOCAB:
            fixed.append(_FUZZY_VOCAB[tok])
            continue
        match = process.extractOne(tok, vocab_keys, scorer=fuzz.ratio, score_cutoff=82)
        if match:
            fixed.append(_FUZZY_VOCAB.get(match[0], tok))
        else:
            fixed.append(tok)
    return " ".join(fixed)


def _extract_entities(message: str, parsed: dict) -> dict[str, Any]:
    ents: dict[str, Any] = {
        "order_id": None,
        "machine_type": parsed.get("category"),
        "city": parsed.get("city"),
        "region": parsed.get("region"),
        "listing_type": parsed.get("listing_type"),
        "max_price": parsed.get("max_price"),
        "brand": parsed.get("brand"),
        "issue_type": None,
    }
    m = _ORDER_ID_RE.search(message)
    if m:
        ents["order_id"] = m.group(1)
    return ents


def _has_machine_signals(parsed: dict, message: str) -> bool:
    if parsed.get("category") or parsed.get("city") or parsed.get("region"):
        return True
    if parsed.get("brand") or parsed.get("model") or parsed.get("max_price") is not None:
        return True
    return bool(re.search(
        r"\b(?:excavator|jcb|crane|roller|loader|truck|drill|grader|bulldozer|mixer|backhoe)\b",
        message, re.I,
    ))


def _is_business_priority(message: str) -> bool:
    """Refund/order/payment phrases override incidental machine words."""
    for intent, pat, _ in _RULES:
        if intent in {
            "refund_return", "order_issue", "payment_issue", "complaint",
            "delivery_logistics", "security_deposit", "support_request",
        } and pat.search(message):
            return True
    return False


def _compute_should_search(intent: str, entities: dict, parsed: dict, message: str) -> bool:
    if intent in NON_SEARCH_INTENTS:
        if intent == "rent_machine" and _has_machine_signals(parsed, message):
            return True
        if intent == "buy_machine" and _has_machine_signals(parsed, message):
            return True
        if intent == "image_search_followup" and (
            entities.get("machine_type") or entities.get("city")
        ):
            return True
        return False
    if intent == "machine_recommendation":
        return True
    if intent in ("machine_search", "machine_availability", "price_query"):
        return True
    if intent == "rent_machine" or intent == "buy_machine":
        return _has_machine_signals(parsed, message)
    if intent == "image_search_followup":
        return bool(entities.get("machine_type") or entities.get("city"))
    return False


def _requires_clarification(intent: str, entities: dict, parsed: dict, message: str) -> bool:
    if intent == "unknown":
        return True
    if is_broad_vague_query(message):
        return True
    if intent in ("rent_machine", "buy_machine", "machine_search") and not _has_machine_signals(parsed, message):
        return True
    if intent == "contact_owner" and not entities.get("machine_type"):
        return True
    return False


def _requires_handover(intent: str) -> bool:
    return intent in {
        "order_issue", "refund_return", "payment_issue", "complaint",
        "delivery_logistics", "security_deposit", "support_request",
    }


def _rule_classify(message: str, context: Optional[dict] = None) -> dict[str, Any]:
    """Layer 1 + 2 rule classification."""
    raw = (message or "").strip()
    if not raw:
        return {**_empty_result("unknown", "empty_message"), "requires_clarification": True}

    ctx = context or {}
    normalized = _fuzzy_normalize_message(raw)
    combined = f"{raw} {normalized}"
    parsed = parse_query(normalized)
    entities = _extract_entities(raw, parsed)

    if is_greeting(raw):
        return {
            "intent": "greeting",
            "confidence": 0.98,
            "should_search_machines": False,
            "requires_clarification": False,
            "requires_handover": False,
            "entities": entities,
            "reason": "greeting_pattern",
            "layer": "rules",
            "normalized_message": normalized,
        }

    # Score all matching rules
    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for intent, pat, base in _RULES:
        if pat.search(combined):
            scores[intent] = max(scores.get(intent, 0), base)
            reasons[intent] = pat.pattern[:60]

    # Out-of-scope wins over weak machine signals
    if "out_of_scope" in scores and scores["out_of_scope"] >= 0.9:
        if not _is_business_priority(combined):
            intent = "out_of_scope"
            conf = scores[intent]
            return {
                "intent": intent,
                "confidence": conf,
                "should_search_machines": False,
                "requires_clarification": False,
                "requires_handover": False,
                "entities": entities,
                "reason": reasons[intent],
                "layer": "rules",
                "normalized_message": normalized,
            }

    # Business intents beat search
    if _is_business_priority(combined):
        business = [
            "support_request", "refund_return", "payment_issue", "security_deposit",
            "order_issue", "complaint", "delivery_logistics",
        ]
        best_biz = max(
            ((i, scores[i]) for i in business if i in scores),
            key=lambda x: x[1],
            default=(None, 0),
        )
        if best_biz[0]:
            intent, conf = best_biz
            if intent == "payment_issue" and "security_deposit" in scores:
                if scores["security_deposit"] > conf:
                    intent, conf = "security_deposit", scores["security_deposit"]
            entities["issue_type"] = intent
            return {
                "intent": intent,
                "confidence": conf,
                "should_search_machines": False,
                "requires_clarification": False,
                "requires_handover": _requires_handover(intent),
                "entities": entities,
                "reason": reasons.get(intent, "business_priority"),
                "layer": "rules",
                "normalized_message": normalized,
            }

    # Platform / help (no search)
    for intent in (
        "platform_how_to", "general_marketplace_help", "document_question",
        "booking_help", "contact_owner",
    ):
        if intent in scores:
            conf = scores[intent]
            has_ctx = bool(
                ctx.get("last_filters", {}).get("category")
                or ctx.get("image_context", {}).get("detected_machine_type")
            )
            return {
                "intent": intent,
                "confidence": conf,
                "should_search_machines": False,
                "requires_clarification": intent == "contact_owner" and not has_ctx,
                "requires_handover": intent == "contact_owner" and has_ctx,
                "entities": entities,
                "reason": reasons[intent],
                "layer": "rules",
                "normalized_message": normalized,
            }

    # Machine recommendation
    if is_recommendation_query(combined) or "machine_recommendation" in scores:
        return {
            "intent": "machine_recommendation",
            "confidence": scores.get("machine_recommendation", 0.82),
            "should_search_machines": True,
            "requires_clarification": False,
            "requires_handover": False,
            "entities": entities,
            "reason": "recommendation_query",
            "layer": "rules",
            "normalized_message": normalized,
        }

    if is_booking_guidance_query(combined) and "platform_how_to" not in scores:
        return {
            "intent": "booking_help",
            "confidence": 0.8,
            "should_search_machines": False,
            "requires_clarification": False,
            "requires_handover": False,
            "entities": entities,
            "reason": "booking_guidance",
            "layer": "rules",
            "normalized_message": normalized,
        }

    # Explicit machine search signals
    if _has_machine_signals(parsed, combined) and not _is_business_priority(combined):
        listing = parsed.get("listing_type")
        if listing == "rent":
            intent = "rent_machine"
        elif listing == "buy":
            intent = "buy_machine"
        elif "machine_availability" in scores:
            intent = "machine_availability"
        elif ctx.get("image_context") and (
            "image_search_followup" in scores or re.search(r"\b(this|ye|same)\b", combined, re.I)
        ):
            intent = "image_search_followup"
        else:
            intent = "machine_search"
        conf = 0.88 if parsed.get("city") and parsed.get("category") else 0.72
        return {
            "intent": intent,
            "confidence": conf,
            "should_search_machines": True,
            "requires_clarification": False,
            "requires_handover": False,
            "entities": entities,
            "reason": "machine_signals",
            "layer": "rules",
            "normalized_message": normalized,
        }

    # Follow-up phrases with session memory (same in Delhi, cheaper, city-only)
    last = ctx.get("last_filters") or {}
    if last.get("category") or last.get("city"):
        if re.search(
            r"\b(?:same\s+in|cheaper|what\s+about|show\s+more|under\s+\d|sasta)\b",
            combined, re.I,
        ):
            entities["machine_type"] = last.get("category")
            entities["city"] = parsed.get("city") or last.get("city")
            return {
                "intent": "machine_search",
                "confidence": 0.8,
                "should_search_machines": True,
                "requires_clarification": False,
                "requires_handover": False,
                "entities": entities,
                "reason": "session_follow_up",
                "layer": "rules",
                "normalized_message": normalized,
            }
        if parsed.get("city") and not parsed.get("category") and last.get("category"):
            entities["machine_type"] = last.get("category")
            return {
                "intent": "machine_search",
                "confidence": 0.78,
                "should_search_machines": True,
                "requires_clarification": False,
                "requires_handover": False,
                "entities": entities,
                "reason": "city_only_follow_up",
                "layer": "rules",
                "normalized_message": normalized,
            }

    # City-only follow-up (from context) — handled by search orchestrator
    if parsed.get("city") and ctx.get("last_filters", {}).get("category"):
        entities["machine_type"] = ctx["last_filters"]["category"]
        return {
            "intent": "machine_search",
            "confidence": 0.75,
            "should_search_machines": True,
            "requires_clarification": False,
            "requires_handover": False,
            "entities": entities,
            "reason": "city_follow_up",
            "layer": "rules",
            "normalized_message": normalized,
        }

    # Vague machine query
    if is_broad_vague_query(combined):
        return {
            "intent": "unknown",
            "confidence": 0.6,
            "should_search_machines": False,
            "requires_clarification": True,
            "requires_handover": False,
            "entities": entities,
            "reason": "vague_machine_query",
            "layer": "rules",
            "normalized_message": normalized,
        }

    # Best remaining rule match
    if scores:
        intent = max(scores, key=scores.get)
        conf = scores[intent]
        should_search = _compute_should_search(intent, entities, parsed, combined)
        return {
            "intent": intent,
            "confidence": conf,
            "should_search_machines": should_search,
            "requires_clarification": _requires_clarification(intent, entities, parsed, combined),
            "requires_handover": _requires_handover(intent),
            "entities": entities,
            "reason": reasons.get(intent, "rule_match"),
            "layer": "rules",
            "normalized_message": normalized,
        }

    return {
        "intent": "unknown",
        "confidence": 0.35,
        "should_search_machines": False,
        "requires_clarification": True,
        "requires_handover": False,
        "entities": entities,
        "reason": "no_rule_match",
        "layer": "rules",
        "normalized_message": normalized,
    }


def _groq_classify(message: str) -> Optional[dict[str, Any]]:
    """Layer 3: Groq returns JSON intent only."""
    if not settings.GROQ_API_KEY:
        return None
    if not settings.USE_GROQ_INTENT_CLASSIFIER:
        return None
    try:
        from app.core.groq_client import client
        from app.ai.text_understanding_service import extract_json_from_text

        allowed = ", ".join(sorted(ALL_INTENTS))
        prompt = f"""Classify this InfraForge construction machine marketplace user message.
Return ONLY valid JSON, no markdown.

Allowed intents: {allowed}

User message: {message}

JSON format:
{{"intent": "<one of allowed intents>", "confidence": 0.0-1.0, "reason": "brief"}}

Rules:
- refund/return/payment/order/delivery/complaint/support = NOT machine_search
- excavator in city, JCB in city = machine_search
- weather/jokes/politics = out_of_scope
- vague help = general_marketplace_help or unknown
"""
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=120,
        )
        content = response.choices[0].message.content or ""
        data = extract_json_from_text(content)
        intent = str(data.get("intent", "unknown"))
        if intent not in ALL_INTENTS:
            intent = "unknown"
        return {
            "intent": intent,
            "confidence": float(data.get("confidence", 0.5)),
            "reason": str(data.get("reason", "groq")),
            "layer": "groq",
        }
    except Exception as exc:
        print(f"[intent_classifier] groq layer failed: {exc}")
        return None


async def classify_intent(
    message: str,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Classify user message into marketplace intent with layered approach.
    """
    result = _rule_classify(message, context)

    if result["confidence"] < _GROQ_LOW_CONFIDENCE:
        groq_hit = _groq_classify(message)
        if groq_hit and groq_hit["confidence"] > result["confidence"]:
            parsed = parse_query(result.get("normalized_message", message))
            entities = _extract_entities(message, parsed)
            intent = groq_hit["intent"]
            combined = result.get("normalized_message", message)
            result = {
                "intent": intent,
                "confidence": groq_hit["confidence"],
                "should_search_machines": _compute_should_search(
                    intent, entities, parsed, combined,
                ),
                "requires_clarification": _requires_clarification(
                    intent, entities, parsed, combined,
                ),
                "requires_handover": _requires_handover(intent),
                "entities": entities,
                "reason": groq_hit.get("reason", "groq"),
                "layer": "groq",
                "normalized_message": result.get("normalized_message", message),
            }

    # Final guard: business intents never search
    if result["intent"] in {
        "refund_return", "order_issue", "payment_issue", "complaint",
        "delivery_logistics", "security_deposit", "support_request",
        "platform_how_to", "general_marketplace_help", "out_of_scope",
        "unknown", "document_question", "booking_help", "greeting",
        "contact_owner", "compare_machine",
    }:
        result["should_search_machines"] = False

    return result


def is_non_search_intent(intent: str) -> bool:
    return intent in NON_SEARCH_INTENTS or intent in {
        "refund_return", "order_issue", "payment_issue", "complaint",
        "delivery_logistics", "security_deposit", "support_request",
        "platform_how_to", "general_marketplace_help", "out_of_scope",
        "unknown", "document_question", "booking_help", "greeting",
    }
