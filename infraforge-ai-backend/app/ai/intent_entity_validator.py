"""
Backend validation for rich LLM intent JSON v1.0.

MongoDB/category/city maps remain source of truth.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import (
    KNOWN_CITIES,
    canonicalize_category,
    detect_requested_category,
)
from app.ai.intent_schema import (
    ASSISTANT_MODES,
    LLM_INTENTS,
    LISTING_TYPES,
    SEARCH_ALLOWED_INTENTS,
    SEARCH_BLOCKED_INTENTS,
    build_search_filters_from_rich,
    default_assistant_mode,
    empty_search_filters,
    flatten_entities,
    infer_response_goal,
    merge_flat_into_rich,
)
from app.ai.query_parser import parse_query
from app.chatbot.assistant_intelligence import resolve_purpose_key
from app.core.config import settings


def _normalize_city(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    token = str(raw).strip().lower()
    if token in KNOWN_CITIES:
        return token
    parsed = parse_query(f"in {token}")
    return parsed.get("city")


def _normalize_category(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cat = canonicalize_category(str(raw).strip())
    if cat:
        return cat
    return detect_requested_category(str(raw))


def _normalize_budget(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    digits = re.sub(r"[^\d.]", "", str(raw))
    if not digits:
        return None
    try:
        val = float(digits)
        return val if val > 0 else None
    except ValueError:
        return None


def _normalize_listing_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    token = str(raw).strip().lower()
    if token in ("rent", "hire", "kiraye", "kiraya"):
        return "rent"
    if token in ("buy", "purchase"):
        return "buy"
    if token == "sell":
        return "sell"
    if token in LISTING_TYPES:
        return token if token != "unknown" else None
    return None


def _merge_parser_hints(payload: dict[str, Any], message: str) -> dict[str, Any]:
    result = dict(payload)
    entities = result.get("entities") or {}
    machine = dict(entities.get("machine") or {})
    location = dict(entities.get("location") or {})
    commercial = dict(entities.get("commercial") or {})
    parsed = parse_query(message)

    if not machine.get("category") and parsed.get("category"):
        machine["category"] = parsed.get("category")
    if not location.get("city") and parsed.get("city"):
        location["city"] = parsed.get("city")
    if commercial.get("budget") is None and parsed.get("max_price") is not None:
        commercial["budget"] = parsed.get("max_price")
        commercial["price_max"] = parsed.get("max_price")
    if not machine.get("brand") and parsed.get("brand"):
        machine["brand"] = parsed.get("brand")
    if not machine.get("model") and parsed.get("model"):
        machine["model"] = parsed.get("model")
    if not machine.get("purpose"):
        pk = resolve_purpose_key(message)
        if pk:
            machine["purpose"] = pk

    entities["machine"] = machine
    entities["location"] = location
    entities["commercial"] = commercial
    result["entities"] = entities
    return result


def validate_llm_classification(payload: dict[str, Any], message: str) -> dict[str, Any]:
    """Validate rich LLM JSON before any backend action."""
    result = dict(payload)
    notes: list[str] = list(result.get("validation_notes") or [])
    missing = list(result.get("missing_fields") or [])

    intent = str(result.get("intent") or "unknown").strip().lower()
    if intent not in LLM_INTENTS:
        notes.append(f"invalid_intent:{intent}")
        intent = "unknown"
        result["intent"] = intent

    try:
        conf = float(result.get("confidence") or 0)
        conf = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        conf = 0.0
        notes.append("invalid_confidence")
    result["confidence"] = conf

    mode = str(result.get("assistant_mode") or "").strip().lower()
    if mode not in ASSISTANT_MODES:
        notes.append(f"invalid_assistant_mode:{mode}")
        mode = default_assistant_mode(intent)
    result["assistant_mode"] = mode

    result = _merge_parser_hints(result, message)
    entities = result.get("entities") or {}
    machine = dict(entities.get("machine") or {})
    location = dict(entities.get("location") or {})
    commercial = dict(entities.get("commercial") or {})
    support = dict(entities.get("support") or {})
    document = dict(entities.get("document") or {})
    user = dict(entities.get("user") or {})

    cat_raw = machine.get("category")
    cat = _normalize_category(cat_raw)
    if cat_raw and not cat:
        notes.append("invalid_category")
        missing.append("machine.category")
        machine["category"] = None
    else:
        machine["category"] = cat

    city_raw = location.get("city")
    city = _normalize_city(city_raw)
    if city_raw and not city:
        notes.append("invalid_city")
        missing.append("city")
        location["city"] = None
    else:
        location["city"] = city

    budget = _normalize_budget(commercial.get("budget") or commercial.get("price_max"))
    commercial["budget"] = budget
    if commercial.get("price_max") is not None:
        commercial["price_max"] = _normalize_budget(commercial.get("price_max"))
    if commercial.get("price_min") is not None:
        commercial["price_min"] = _normalize_budget(commercial.get("price_min"))

    lt = _normalize_listing_type(machine.get("listing_type"))
    if machine.get("listing_type") and not lt:
        notes.append("invalid_listing_type")
    machine["listing_type"] = lt

    brands_raw = machine.get("brands")
    if isinstance(brands_raw, list):
        machine["brands"] = [str(b).strip() for b in brands_raw if b][:6]
    elif brands_raw:
        machine["brands"] = [str(brands_raw).strip()]
    else:
        machine["brands"] = []
    if machine.get("brand") and not machine.get("brands"):
        machine["brands"] = [str(machine["brand"]).strip()]

    if user.get("name"):
        name = str(user["name"]).strip().title()
        user["name"] = name if len(name) >= 2 else None

    entities = {
        "user": user,
        "machine": machine,
        "location": location,
        "commercial": commercial,
        "support": support,
        "document": document,
        "image": entities.get("image") or {"image_reference": False, "detected_machine_hint": None},
    }
    result["entities"] = entities
    result["missing_fields"] = list(dict.fromkeys(missing))

    flat = flatten_entities(entities)
    has_category = bool(flat.get("machine_category") or flat.get("category"))
    has_purpose = bool(flat.get("purpose"))
    has_city = bool(flat.get("city"))

    should_search = bool(result.get("should_search_machines"))
    should_rag = bool(result.get("should_use_rag"))

    if intent in SEARCH_BLOCKED_INTENTS or intent == "broad_machine_request":
        should_search = False
    if intent == "broad_machine_request":
        result["requires_clarification"] = True
        machine["category"] = None
        if "purpose_or_category" not in result["missing_fields"]:
            result["missing_fields"] = ["purpose_or_category", "city"]
        result["response_goal"] = result.get("response_goal") or "collect_machine_requirements"

    if intent == "document_question":
        should_rag = bool(document.get("document_reference") or document.get("question_about_document"))
        should_search = False
        if not should_rag:
            notes.append("document_question_without_reference")
            result["requires_clarification"] = True
            result["response_goal"] = "ask_document_upload"
    else:
        should_rag = False

    if intent in SEARCH_ALLOWED_INTENTS and intent != "machine_recommendation":
        if not has_category and not has_purpose:
            should_search = False
            result["requires_clarification"] = True
            if "purpose_or_category" not in result["missing_fields"]:
                result["missing_fields"].append("purpose_or_category")
        elif not has_city:
            should_search = False
            result["requires_clarification"] = True
            if "city" not in result["missing_fields"]:
                result["missing_fields"].append("city")
        else:
            should_search = True
            result["requires_clarification"] = False

    if intent == "machine_recommendation":
        should_search = bool(has_purpose or has_category) and has_city
        if not should_search:
            result["requires_clarification"] = True

    if intent in (
        "payment_issue", "refund_return", "order_issue", "delivery_issue",
        "security_deposit", "invoice_issue", "support_request",
        "frustration", "acknowledgement", "out_of_scope", "machine_brand_query",
    ):
        should_search = False
        result["requires_human_handover"] = True
        if intent == "payment_issue" and not support.get("transaction_id") and not support.get("booking_id"):
            if "support.transaction_id" not in result["missing_fields"]:
                result["missing_fields"].append("support.transaction_id")

    if intent in ("user_introduction", "gratitude", "polite_conversation", "greeting"):
        should_search = False
        result["requires_clarification"] = False

    if intent == "frustration":
        should_search = False
        should_rag = False
        result["user_sentiment"] = "frustrated"
        result["requires_clarification"] = False
        result["response_goal"] = result.get("response_goal") or "frustration_recovery"

    if intent == "acknowledgement":
        should_search = False
        result["requires_clarification"] = False
        result["response_goal"] = result.get("response_goal") or "continue_pending_flow"

    if intent == "machine_brand_query":
        should_search = False
        should_rag = False
        result["response_goal"] = result.get("response_goal") or "show_brand_inventory"

    # LLM tool hints are suggestions — permission matrix has final say
    try:
        from app.ai.tool_permission_matrix import get_intent_permissions, is_tool_allowed
        from app.ai.tool_permission_matrix import TOOL_MONGODB_SEARCH

        perms = get_intent_permissions(intent)
        if should_search and not is_tool_allowed(intent, TOOL_MONGODB_SEARCH):
            should_search = False
            notes.append("permission_matrix_blocked_search")
            result["requires_clarification"] = True
        blocked = perms.get("blocked_tools") or []
        if should_rag and "rag" in blocked:
            should_rag = False
            notes.append("permission_matrix_blocked_rag")
    except Exception:
        pass

    if conf < 0.55:
        should_search = False
        result["requires_clarification"] = True
        notes.append("low_confidence")

    if notes:
        should_search = False

    result["should_search_machines"] = should_search
    result["should_use_rag"] = should_rag
    result["requires_handover"] = bool(result.get("requires_human_handover") or result.get("requires_handover"))
    result["validation_notes"] = notes

    sf = dict(result.get("search_filters") or empty_search_filters())
    if should_search:
        built = build_search_filters_from_rich(result)
        sf.update({k: v for k, v in built.items() if v is not None})
    result["search_filters"] = sf

    if not result.get("response_goal"):
        result["response_goal"] = infer_response_goal(result)

    result["safety"] = {
        "can_answer_directly": intent in ("greeting", "gratitude", "polite_conversation"),
        "can_generate_final_response": True,
        "must_not_search": not should_search,
        "must_not_invent_data": True,
    }

    if settings.ENVIRONMENT in ("development", "dev", "local") and notes:
        print(f"[intent_validator] notes={notes} intent={intent}")

    return result


def validate_flat_payload(flat_payload: dict[str, Any], message: str) -> dict[str, Any]:
    """Upgrade legacy flat classifier output to rich schema and validate."""
    from app.ai.intent_schema import empty_rich_payload

    rich = empty_rich_payload(layer=flat_payload.get("layer") or "fast_path")
    for key in (
        "intent", "confidence", "assistant_mode", "should_search_machines",
        "requires_clarification", "missing_fields", "reason", "layer",
        "response_goal", "user_sentiment", "language",
    ):
        if key in flat_payload:
            rich[key] = flat_payload[key]
    rich["entities"] = merge_flat_into_rich(flat_payload.get("entities") or {})
    rich["requires_human_handover"] = bool(flat_payload.get("requires_handover"))
    rich["normalized_message"] = flat_payload.get("normalized_message") or message
    return validate_llm_classification(rich, message)
