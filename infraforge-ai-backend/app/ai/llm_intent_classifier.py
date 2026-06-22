"""
LLM-first intent classifier — rich JSON schema v1.0.

Rules used only for fast-path and fallback when LLM unavailable.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional, Protocol

from app.ai.intent_schema import (
    LLM_INTENTS,
    SCHEMA_VERSION,
    build_search_filters_from_rich,
    default_assistant_mode,
    empty_entities,
    empty_rich_payload,
    empty_search_filters,
    infer_response_goal,
    merge_flat_into_rich,
    to_legacy_classification,
)
from app.ai.query_parser import parse_query
from app.ai.text_understanding_service import extract_json_from_text
from app.core.config import settings

_LOW_CONFIDENCE = 0.55
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_RICH_PROMPT_SCHEMA = """{
  "schema_version": "1.0",
  "intent": "<allowed intent>",
  "sub_intent": null,
  "confidence": 0.0,
  "language": "english | hindi | hinglish",
  "user_sentiment": "neutral | positive | confused | frustrated | urgent",
  "assistant_mode": "conversation | machine_search | recommendation | support | document_qa | image_followup | clarification | out_of_scope",
  "response_goal": "<e.g. greet_user, acknowledge_name, collect_machine_requirements, ask_city, collect_transaction_id>",
  "requires_clarification": false,
  "requires_human_handover": false,
  "should_search_machines": false,
  "should_use_rag": false,
  "should_use_image_context": false,
  "next_best_action": "short action label",
  "entities": {
    "user": {"name": null},
    "machine": {"category": null, "brand": null, "brands": [], "model": null, "purpose": null, "listing_type": null, "rent_type": null, "condition": null},
    "location": {"city": null, "state": null, "nearby_allowed": false},
    "commercial": {"budget": null, "budget_type": null, "currency": "INR", "price_max": null, "price_min": null},
    "support": {"issue_category": null, "issue_subcategory": null, "order_id": null, "booking_id": null, "transaction_id": null, "payment_method": null, "amount": null},
    "document": {"document_reference": false, "document_type": null, "question_about_document": false},
    "image": {"image_reference": false, "detected_machine_hint": null}
  },
  "missing_fields": [],
  "validation_notes": [],
  "search_filters": {"category": null, "city": null, "max_price": null, "min_price": null, "brand": null, "brands": [], "model": null, "listing_type": null, "availability_required": true},
  "safety": {"can_answer_directly": false, "can_generate_final_response": true, "must_not_search": true, "must_not_invent_data": true},
  "reason": "brief internal reason"
}"""


def _context_hash(context: Optional[dict]) -> str:
    ctx = context or {}
    parts = [
        str(ctx.get("greeted", False)),
        str((ctx.get("pending") or {}).get("missing_field", "")),
        str(ctx.get("has_session_documents", False)),
        str(ctx.get("has_image_context", False)),
        str(ctx.get("turn_count", 0)),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    ttl = max(30, int(getattr(settings, "INTENT_CACHE_TTL_SECONDS", 120)))
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, payload = hit
    if time.time() - ts > ttl:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    if len(_CACHE) > 500:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.time(), payload)


class IntentProvider(Protocol):
    def classify(self, message: str, *, context: Optional[dict] = None) -> Optional[dict[str, Any]]: ...


class GroqIntentProvider:
    MODEL = "llama-3.3-70b-versatile"

    def classify(self, message: str, *, context: Optional[dict] = None) -> Optional[dict[str, Any]]:
        from app.core.groq_client import groq_chat_completion

        ctx = context or {}
        session_bits = []
        if ctx.get("user_name"):
            session_bits.append(f"Known user name: {ctx['user_name']}")
        if ctx.get("pending"):
            session_bits.append(f"Pending clarification: {json.dumps(ctx['pending'])[:200]}")
        if ctx.get("has_session_documents"):
            session_bits.append("User has uploaded session documents.")
        if ctx.get("has_image_context"):
            session_bits.append("User has recent image machine context.")

        allowed = ", ".join(sorted(LLM_INTENTS))
        prompt = f"""You are an intent and entity classifier for InfraForge marketplace assistant.
Return ONLY valid JSON. No markdown. No explanation.

Your job is ONLY to classify intent, extract entities, identify missing fields, language, sentiment, and safe next-action hints.
Do NOT answer the user. Do NOT search machines. Do NOT invent machine data, prices, availability, owner contact, support/refund/delivery status, or document facts.
Backend will validate everything.

Allowed intents: {allowed}

Session context:
{chr(10).join(session_bits) if session_bits else "None"}

User message: {message}

Required JSON schema:
{_RICH_PROMPT_SCHEMA}

Critical rules:
- broad_machine_request: vague machine need WITHOUT work type AND category. NEVER set machine.category=excavator. requires_clarification=true, missing_fields=["purpose_or_category","city"], response_goal=collect_machine_requirements.
- user_introduction: ANY name intro phrasing. entities.user.name filled. No search.
- machine_brand_query: user asks which brands exist for a category or brand inventory. should_search_machines=false unless checking availability with category+brand.
- machine_comparison / comparison_request: comparing brands or machines. Extract brands into machine.brands when present.
- cheaper_option_query / higher_budget_query: budget follow-up on prior search context.
- acknowledgement: short ack (ok, yes, got it) — may continue pending flow.
- frustration: user upset; should_search_machines=false, user_sentiment=frustrated.
- payment_issue: extract support.issue_subcategory if possible. should_search_machines=false. may set missing_fields for transaction/booking IDs.
- document_question: should_use_rag=true only with document.document_reference=true.
- out_of_scope: unrelated to marketplace.
- If unclear, return unknown or requires_clarification=true.
"""

        response = groq_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=self.MODEL,
            temperature=0,
            tag="llm_intent",
        )
        if not response:
            return None
        content = (response.choices[0].message.content or "").strip()
        try:
            data = extract_json_from_text(content)
        except Exception:
            return None
        return _normalize_rich_payload(data, message)


class OpenAIIntentProvider:
    def classify(self, message: str, *, context: Optional[dict] = None) -> Optional[dict[str, Any]]:
        if not settings.openai_usable:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"Classify InfraForge intent as JSON only.\n{message}"}],
                temperature=0,
                max_tokens=800,
            )
            data = extract_json_from_text((response.choices[0].message.content or "").strip())
            out = _normalize_rich_payload(data, message)
            if out:
                out["layer"] = "openai"
            return out
        except Exception as exc:
            print(f"[llm_intent] openai failed: {exc}")
            return None


def _get_provider() -> Optional[IntentProvider]:
    if settings.openai_usable and settings.AI_PROVIDER == "openai":
        return OpenAIIntentProvider()
    if settings.GROQ_API_KEY and settings.AI_PROVIDER in ("groq", "local", ""):
        return GroqIntentProvider()
    return None


def _rules_fallback_classification(message: str, context: Optional[dict] = None) -> dict[str, Any]:
    """Rules-first fallback when LLM unavailable, invalid, or low confidence."""
    from app.ai.intent_classifier import _rule_classify
    from app.ai.intent_entity_validator import validate_flat_payload

    rules = _rule_classify(message, context)
    validated = validate_flat_payload(rules, message)
    validated["layer"] = "rules_fallback"
    validated["reason"] = rules.get("reason") or "rules_fallback"
    return to_legacy_classification(validated)


async def _call_llm_classifier_raw(
    message: str,
    *,
    context: Optional[dict] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Call LLM provider and validate. Returns (legacy_classification, fallback_reason).
    fallback_reason set when LLM output cannot be used as primary.
    """
    text = (message or "").strip()
    if not text:
        return None, "empty_message"

    provider = _get_provider()
    if not provider:
        return None, "provider_unavailable"

    llm_hit = provider.classify(text, context=context)
    if not llm_hit:
        return None, "invalid_json_or_provider_error"

    from app.ai.intent_entity_validator import validate_llm_classification

    validated = validate_llm_classification(llm_hit, text)
    conf = float(validated.get("confidence") or 0)
    notes = validated.get("validation_notes") or []

    if conf < _LOW_CONFIDENCE:
        return to_legacy_classification({**validated, "layer": "llm_low_confidence"}), "low_confidence"
    if notes and validated.get("intent") == "unknown":
        return to_legacy_classification({**validated, "layer": "llm_validation_failed"}), "validation_failed"

    result = to_legacy_classification({**validated, "layer": "llm"})
    result["intent_source"] = "llm"
    return result, None


def _normalize_rich_payload(data: dict[str, Any], message: str) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None

    intent = str(data.get("intent") or "unknown").strip().lower()
    if intent not in LLM_INTENTS:
        intent = "unknown"

    entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    normalized_entities = empty_entities()
    for section in ("user", "machine", "location", "commercial", "support", "document", "image"):
        if isinstance(entities.get(section), dict):
            for k, v in entities[section].items():
                if k in normalized_entities.get(section, {}):
                    normalized_entities[section][k] = v

    result = empty_rich_payload(reason=str(data.get("reason") or "llm"), layer="llm")
    result.update({
        "schema_version": data.get("schema_version") or SCHEMA_VERSION,
        "intent": intent,
        "sub_intent": data.get("sub_intent"),
        "confidence": data.get("confidence", 0.5),
        "language": data.get("language") or "english",
        "user_sentiment": data.get("user_sentiment") or "neutral",
        "assistant_mode": data.get("assistant_mode") or default_assistant_mode(intent),
        "response_goal": data.get("response_goal") or infer_response_goal({"intent": intent, "requires_clarification": data.get("requires_clarification")}),
        "requires_clarification": bool(data.get("requires_clarification")),
        "requires_human_handover": bool(data.get("requires_human_handover")),
        "should_search_machines": bool(data.get("should_search_machines")),
        "should_use_rag": bool(data.get("should_use_rag")),
        "should_use_image_context": bool(data.get("should_use_image_context")),
        "next_best_action": data.get("next_best_action"),
        "entities": normalized_entities,
        "missing_fields": list(data.get("missing_fields") or []),
        "validation_notes": list(data.get("validation_notes") or []),
        "search_filters": {**empty_search_filters(), **(data.get("search_filters") or {})},
        "safety": data.get("safety") or result["safety"],
        "reason": str(data.get("reason") or "llm"),
        "normalized_message": message,
    })
    return result


def _deterministic_fast_path(message: str, context: Optional[dict] = None) -> Optional[dict[str, Any]]:
    from app.ai.intent_classifier import _rule_classify

    rules = _rule_classify(message, context)
    conf = float(rules.get("confidence") or 0)
    intent = rules.get("intent") or "unknown"
    parsed = parse_query(rules.get("normalized_message") or message)

    if parsed.get("category") and parsed.get("city") and conf >= 0.7:
        if intent not in {"refund_return", "payment_issue", "order_issue", "out_of_scope", "complaint", "delivery_logistics"}:
            rich = empty_rich_payload(reason="fast_path_category_city", layer="fast_path")
            rich.update({
                "intent": "machine_search",
                "confidence": 0.92,
                "assistant_mode": "machine_search",
                "response_goal": "show_machine_results",
                "should_search_machines": True,
                "requires_clarification": False,
                "entities": merge_flat_into_rich({
                    "machine_category": parsed.get("category"),
                    "city": parsed.get("city"),
                    "brand": parsed.get("brand"),
                    "budget": parsed.get("max_price"),
                    "listing_type": parsed.get("listing_type"),
                }),
                "search_filters": build_search_filters_from_rich({
                    "entities": merge_flat_into_rich({"machine_category": parsed.get("category"), "city": parsed.get("city")}),
                }),
                "normalized_message": rules.get("normalized_message") or message,
            })
            return rich

    support_map = {
        "refund_return": "refund_return",
        "payment_issue": "payment_issue",
        "order_issue": "order_issue",
        "delivery_logistics": "delivery_issue",
        "complaint": "support_request",
        "security_deposit": "security_deposit",
        "invoice_issue": "invoice_issue",
        "out_of_scope": "out_of_scope",
    }
    if conf >= 0.88 and intent in support_map:
        mapped = support_map[intent]
        rich = empty_rich_payload(reason=rules.get("reason") or "fast_path_support", layer="fast_path")
        goal = "collect_transaction_id" if mapped == "payment_issue" else "collect_booking_id"
        rich.update({
            "intent": mapped,
            "confidence": conf,
            "assistant_mode": "support",
            "response_goal": goal,
            "requires_human_handover": True,
            "entities": merge_flat_into_rich({"order_id": (rules.get("entities") or {}).get("order_id"), "issue_type": mapped}),
            "normalized_message": rules.get("normalized_message") or message,
        })
        return rich

    return None


def log_intent_debug(
    *,
    normalized_message: str,
    classification: dict[str, Any],
    action: str = "",
    tool: str = "",
    rag_used: bool = False,
    search_used: bool = False,
    fallback_used: bool = False,
) -> None:
    if settings.ENVIRONMENT not in ("development", "dev", "local"):
        return
    rich = classification.get("rich") or classification
    print(
        "[llm_intent_debug]",
        f"msg={normalized_message[:80]!r}",
        f"intent={classification.get('llm_intent') or classification.get('intent')}",
        f"confidence={classification.get('confidence')}",
        f"goal={rich.get('response_goal')}",
        f"mode={classification.get('assistant_mode')}",
        f"entities={classification.get('entities')}",
        f"search_filters={rich.get('search_filters')}",
        f"should_search={classification.get('should_search_machines')}",
        f"validation={rich.get('validation_notes')}",
        f"action={action}",
        f"tool={tool}",
        f"rag={rag_used}",
        f"search={search_used}",
        f"fallback={fallback_used}",
    )


async def classify_intent_llm(
    message: str,
    *,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    text = (message or "").strip()
    if not text:
        return to_legacy_classification(empty_rich_payload(reason="empty_message"))

    ctx = context or {}
    cache_key = hashlib.sha256(f"{text.lower()}|{_context_hash(ctx)}".encode()).hexdigest()
    cached = _cache_get(cache_key)
    if cached:
        out = to_legacy_classification({**cached, "layer": cached.get("layer", "llm") + "_cache"})
        out["intent_source"] = out.get("intent_source") or "llm"
        return out

    fast = _deterministic_fast_path(text, ctx)
    if fast and float(fast.get("confidence") or 0) >= 0.88:
        from app.ai.intent_entity_validator import validate_llm_classification
        validated = validate_llm_classification(fast, text)
        result = to_legacy_classification(validated)
        result["intent_source"] = "llm"
        log_intent_debug(normalized_message=text, classification=result, action="fast_path")
        return result

    llm_result, fallback_reason = await _call_llm_classifier_raw(text, context=ctx)
    if llm_result and not fallback_reason:
        rich = llm_result.get("rich") or {}
        _cache_set(cache_key, rich)
        log_intent_debug(normalized_message=text, classification=llm_result, action="llm_classify")
        try:
            from app.ai.assistant_debug_trace import record_llm_intent_result
            record_llm_intent_result(llm_result, validation_passed=True, fallback_reason=None)
        except Exception:
            pass
        return llm_result

    rules_result = _rules_fallback_classification(text, ctx)
    rules_result["intent_source"] = "rules_fallback"
    try:
        from app.ai.assistant_debug_trace import record_rules_intent_snapshot
        record_rules_intent_snapshot(rules_result)
    except Exception:
        pass
    log_intent_debug(
        normalized_message=text,
        classification=rules_result,
        action="rules_fallback",
        fallback_used=True,
    )
    try:
        from app.ai.assistant_debug_trace import record_llm_intent_result
        record_llm_intent_result(
            llm_result or {},
            validation_passed=False,
            fallback_reason=fallback_reason or "rules_fallback",
        )
    except Exception:
        pass
    return rules_result


async def classify_intent_llm_shadow_compare(
    message: str,
    *,
    context: Optional[dict] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (rules_classification, llm_classification) for shadow logging."""
    rules = _rules_fallback_classification(message, context)
    llm_result, _ = await _call_llm_classifier_raw(message, context=context)
    return rules, llm_result or {}


# Backward-compatible alias for tests and legacy imports.
_empty_entities = empty_entities
