"""
Semantic Turn Understanding Gateway — LLM-first with deterministic fallback.

Produces structured turn understanding BEFORE routing in assistant_router /
universal_turn_engine. Mechanism-level — not phrase-specific hacks.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.ai.numeric_normalizer import normalize_message_numerics
from app.ai.query_parser import parse_query
from app.chatbot.language import detect_query_language
from app.core.config import settings

PRIMARY_INTENTS = frozenset({
    "machine_search",
    "recommendation",
    "comparison",
    "support",
    "domain_knowledge",
    "meta_help",
    "memory_question",
    "conversational",
    "off_topic",
    "clarification_answer",
    "frustration",
    "search_refinement",
    "greeting",
})

RESPONSE_MODES = frozenset({
    "greeting",
    "meta_help",
    "memory_answer",
    "domain_knowledge",
    "recommendation",
    "comparison",
    "machine_search",
    "search_refinement",
    "support",
    "clarification",
    "frustration_recovery",
    "off_topic_redirect",
    "safe_error_fallback",
    "conversational",
})

_DOMAIN_IN = "in_domain"
_DOMAIN_ADJACENT = "adjacent"
_DOMAIN_OFF = "off_topic"

# Structural signals (families, not example sentences)
_META_HELP_RE = re.compile(
    r"(?:"
    r"how\s+can\s+you\s+help|what\s+can\s+you\s+do|how\s+do\s+you\s+work|"
    r"what\s+do\s+you\s+support|kya\s+kar\s+sakte|kaise\s+madad|"
    r"how\s+does\s+(?:this|infraforge)\s+work|what\s+are\s+your\s+capabilities"
    r")",
    re.I,
)

_MEMORY_QUESTION_RE = re.compile(
    r"(?:"
    r"what(?:'s|s|\s+is)\s+my\s+name|whats\s+my\s+name|who\s+am\s+i|mera\s+naam|"
    r"my\s+name\s*\??\s*$|do\s+you\s+(?:know|remember)\s+my\s+name|"
    r"naam\s+yaad\s+hai|remember\s+me"
    r")",
    re.I,
)

_FRUSTRATION_RE = re.compile(
    r"(?:"
    r"\b(?:useless|worthless|stupid|dumb|idiot|moron|hopeless|bekar|pagal|"
    r"are\s+you\s+mad|you\s+are\s+mad|kya\s+pagal|nonsense|garbage|worst)\b"
    r")",
    re.I,
)

_FRAGMENT_LOCATION_RE = re.compile(
    r"^(?:in|at|near|around|me|mein|mai|par)\s+[A-Za-z\u0900-\u097F]{2,}",
    re.I,
)

_FRAGMENT_BUDGET_RE = re.compile(
    r"^(?:under|below|upto|up\s+to|within|budget|max)\b",
    re.I,
)

_FRAGMENT_BEST_AMONG_RE = re.compile(
    r"(?:inme\s+se|in\s+me\s+se|isme\s+se|among\s+these|best\s+konsa|best\s+kaunsa|"
    r"kaun\s+sa\s+best|which\s+is\s+best)",
    re.I,
)

_COMPARISON_RE = re.compile(
    r"\b(?:vs\.?|versus|compare|comparison|difference\s+between)\b"
    r"|(?:better|best|behtar|acch[ae]|badiya).{0,40}\b(?:or|ya|aur)\b"
    r"|\b(?:or|ya|aur)\b.{0,40}\b(?:better|best|behtar)\b",
    re.I,
)

_RECOMMENDATION_RE = re.compile(
    r"\b(?:recommend|suggest|best\s+machine|which\s+machine|what\s+machine|"
    r"kaunsi\s+machine|konsi\s+machine|suitable\s+for|ke\s+liye\s+(?:best|kaunsi))\b",
    re.I,
)

_SUPPORT_RE = re.compile(
    r"\b(?:refund|payment\s+(?:issue|failed|stuck)|booking\s+(?:issue|problem)|"
    r"order\s+(?:issue|problem)|complaint|transaction|invoice|receipt|"
    r"cancel|money\s+back|not\s+working|broken|support|help\s+with\s+my|"
    r"double\s+charged?|delivery\s+delayed?|deposit\s+issue)\b",
    re.I,
)

_OFF_TOPIC_RE = re.compile(
    r"\b(?:weather|temperature|joke|cricket|movie|recipe|bitcoin|homework|"
    r"politics|election|horoscope)\b",
    re.I,
)


@dataclass
class SemanticTurnUnderstanding:
    raw_message: str = ""
    normalized_message: str = ""
    language: str = "english"
    primary_intent: str = "conversational"
    domain_status: str = _DOMAIN_IN
    response_mode: str = "conversational"
    entities: dict[str, Any] = field(default_factory=dict)
    context_reference: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    should_search: bool = False
    should_recommend: bool = False
    should_compare: bool = False
    should_answer_knowledge: bool = False
    confidence: float = 0.5
    reason: str = ""
    layer: str = "rules"
    is_fragment: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def is_short_context_fragment(message: str, *, parsed: dict | None = None) -> bool:
    """True when message is a short follow-up fragment needing prior context."""
    text = (message or "").strip()
    if not text:
        return False
    words = text.split()
    if len(words) > 6:
        return False
    p = parsed or parse_query(text)
    if _FRAGMENT_BEST_AMONG_RE.search(text):
        return True
    if _FRAGMENT_LOCATION_RE.match(text) and not p.get("category"):
        return True
    if _FRAGMENT_BUDGET_RE.match(text):
        return True
    if len(words) <= 3 and (p.get("city") or p.get("max_price") is not None) and not p.get("category"):
        return True
    from app.ai.numeric_normalizer import extract_budget_amount
    if len(words) <= 4 and extract_budget_amount(text) and not p.get("category"):
        return True
    return False


def resolve_fragment_context(
    message: str,
    *,
    conv_state: dict | None = None,
    last_filters: dict | None = None,
    parsed: dict | None = None,
) -> dict[str, Any]:
    """Attach prior recommendation/search/comparison context to fragment messages."""
    text = (message or "").strip()
    p = dict(parsed or parse_query(text))
    state = conv_state or {}
    last = dict(last_filters or state.get("last_search_filters") or {})
    collected = dict(state.get("collected_fields") or {})
    ref: dict[str, Any] = {"type": None, "source": None}

    if _FRAGMENT_BEST_AMONG_RE.search(text):
        cmp_ctx = state.get("last_comparison_context") or {}
        brands = cmp_ctx.get("brands") or collected.get("brands") or []
        if not brands and last.get("brand"):
            brands = [last["brand"]]
        ref = {"type": "best_among_previous", "brands": brands, "category": cmp_ctx.get("category") or last.get("category")}
        if brands:
            p["brands"] = brands
        if ref.get("category") and not p.get("category"):
            p["category"] = ref["category"]

    if p.get("city") and not collected.get("city"):
        ref.setdefault("type", "location_fragment")
        ref["city"] = p["city"]
    elif _FRAGMENT_LOCATION_RE.match(text) and p.get("city"):
        ref = {"type": "location_fragment", "city": p["city"]}

    if p.get("max_price") is None:
        from app.ai.numeric_normalizer import extract_budget_amount
        budget = extract_budget_amount(text)
        if budget:
            p["max_price"] = budget
            ref.setdefault("type", "budget_fragment")
            ref["budget"] = budget
    elif p.get("max_price") is not None:
        ref.setdefault("type", "budget_fragment")
        ref["budget"] = p["max_price"]

    for key in ("category", "city", "brand", "listing_type"):
        if not p.get(key) and (collected.get(key) or last.get(key)):
            p[key] = collected.get(key) or last.get(key)

    purpose = collected.get("purpose") or state.get("last_recommendation_context", {}).get("purpose_key")
    if purpose and not p.get("purpose_key"):
        p["purpose_key"] = purpose

    return {"parsed": p, "context_reference": ref, "merged_from_session": bool(ref.get("type"))}


def _rules_understand(
    message: str,
    *,
    parsed: dict | None = None,
    context: dict | None = None,
) -> SemanticTurnUnderstanding:
    ctx = context or {}
    numeric = normalize_message_numerics(message)
    text = numeric["normalized_message"]
    raw = numeric["raw_message"]
    parsed = dict(parsed or parse_query(text))
    if numeric.get("budget_amount") and parsed.get("max_price") is None:
        parsed["max_price"] = numeric["budget_amount"]

    lang = detect_query_language(text)
    conv_state = ctx.get("conversation_state") or {}
    last_filters = ctx.get("last_search_filters") or conv_state.get("last_search_filters") or {}

    understanding = SemanticTurnUnderstanding(
        raw_message=raw,
        normalized_message=text,
        language=lang,
        entities=parsed,
        layer="rules",
    )

    if is_short_context_fragment(text, parsed=parsed) and conv_state:
        frag = resolve_fragment_context(
            text, conv_state=conv_state, last_filters=last_filters, parsed=parsed,
        )
        understanding.is_fragment = True
        understanding.entities = frag["parsed"]
        understanding.context_reference = frag["context_reference"]
        understanding.reason = "short_context_fragment"
        if _FRAGMENT_BEST_AMONG_RE.search(text):
            understanding.primary_intent = "comparison"
            understanding.response_mode = "comparison"
            understanding.should_compare = True
            understanding.confidence = 0.88
            return understanding
        if frag["parsed"].get("city") or frag["parsed"].get("max_price") is not None:
            understanding.primary_intent = "clarification_answer"
            understanding.response_mode = "search_refinement"
            understanding.should_search = True
            understanding.confidence = 0.86
            return understanding

    if _FRUSTRATION_RE.search(text):
        understanding.primary_intent = "frustration"
        understanding.response_mode = "frustration_recovery"
        understanding.domain_status = _DOMAIN_IN
        understanding.confidence = 0.9
        understanding.reason = "frustration_signal"
        return understanding

    if _MEMORY_QUESTION_RE.search(text):
        understanding.primary_intent = "memory_question"
        understanding.response_mode = "memory_answer"
        understanding.should_answer_knowledge = True
        understanding.confidence = 0.92
        understanding.reason = "memory_question_signal"
        name = (
            ctx.get("user_name")
            or conv_state.get("user_name")
            or (ctx.get("collected_fields") or {}).get("name")
        )
        understanding.context_reference = {"user_name": name}
        return understanding

    if _META_HELP_RE.search(text):
        understanding.primary_intent = "meta_help"
        understanding.response_mode = "meta_help"
        understanding.should_answer_knowledge = True
        understanding.confidence = 0.9
        understanding.reason = "meta_help_signal"
        return understanding

    if _OFF_TOPIC_RE.search(text) and not parsed.get("category"):
        understanding.primary_intent = "off_topic"
        understanding.response_mode = "off_topic_redirect"
        understanding.domain_status = _DOMAIN_OFF
        understanding.confidence = 0.88
        understanding.reason = "off_topic_signal"
        return understanding

    from app.ai.knowledge_query_engine import knowledge_turn_from_message

    kq = knowledge_turn_from_message(text, parsed, session_ctx=ctx)
    if kq:
        kind = kq.get("kind") or "domain_definition"
        understanding.primary_intent = "domain_knowledge"
        understanding.response_mode = "domain_knowledge"
        understanding.should_answer_knowledge = True
        understanding.confidence = 0.9
        understanding.reason = kq.get("reason") or "knowledge_query"
        understanding.context_reference = {"knowledge": kq}
        return understanding

    from app.chatbot.assistant_intelligence import is_greeting

    if is_greeting(text):
        understanding.primary_intent = "greeting"
        understanding.response_mode = "greeting"
        understanding.confidence = 0.93
        understanding.reason = "greeting_signal"
        return understanding

    if _SUPPORT_RE.search(text):
        understanding.primary_intent = "support"
        understanding.response_mode = "support"
        understanding.domain_status = _DOMAIN_IN
        understanding.confidence = 0.88
        understanding.reason = "support_signal"
        return understanding

    if _FRAGMENT_BEST_AMONG_RE.search(text):
        understanding.primary_intent = "comparison"
        understanding.response_mode = "comparison"
        understanding.should_compare = True
        understanding.confidence = 0.86
        understanding.reason = "best_among_signal"
        if conv_state:
            frag = resolve_fragment_context(
                text, conv_state=conv_state, last_filters=last_filters, parsed=parsed,
            )
            understanding.entities = frag["parsed"]
            understanding.context_reference = frag["context_reference"]
        return understanding

    if _RECOMMENDATION_RE.search(text):
        understanding.primary_intent = "recommendation"
        understanding.response_mode = "recommendation"
        understanding.should_recommend = True
        understanding.confidence = 0.84
        understanding.reason = "recommendation_signal"
        missing = []
        if not parsed.get("city"):
            missing.append("city")
        if not parsed.get("category") and not parsed.get("purpose_key"):
            missing.append("purpose_or_category")
        understanding.missing_fields = missing
        return understanding

    if _COMPARISON_RE.search(text) or len(parsed.get("brands") or []) >= 2:
        understanding.primary_intent = "comparison"
        understanding.response_mode = "comparison"
        understanding.should_compare = True
        understanding.confidence = 0.85
        understanding.reason = "comparison_signal"
        return understanding

    from app.ai.domain_recommendation_engine import is_domain_recommendation_query

    if is_domain_recommendation_query(text, parsed=parsed):
        understanding.primary_intent = "recommendation"
        understanding.response_mode = "recommendation"
        understanding.should_recommend = True
        understanding.confidence = 0.82
        understanding.reason = "domain_recommendation_signal"
        return understanding

    from app.ai.capability_registry import has_marketplace_action_signal
    from app.ai.social_turn_detector import detect_social_turn

    has_search_entities = bool(
        parsed.get("category") or parsed.get("city") or parsed.get("brand") or parsed.get("max_price")
    )
    if has_search_entities or has_marketplace_action_signal(text):
        understanding.primary_intent = "machine_search"
        understanding.response_mode = "machine_search"
        understanding.should_search = True
        understanding.confidence = 0.82
        understanding.reason = "machine_search_signal"
        return understanding

    social = detect_social_turn(text, ctx)
    if social:
        understanding.primary_intent = "conversational"
        understanding.response_mode = "conversational"
        understanding.confidence = social.get("confidence", 0.85)
        understanding.reason = f"social:{social.get('kind')}"
        understanding.context_reference = {"social": social}
        return understanding

    understanding.primary_intent = "conversational"
    understanding.response_mode = "clarification"
    understanding.confidence = 0.5
    understanding.reason = "default_clarification"
    return understanding


def _validate_llm_payload(data: dict) -> dict:
    intent = (data.get("primary_intent") or "conversational").strip().lower()
    if intent not in PRIMARY_INTENTS:
        intent = "conversational"
    mode = (data.get("response_mode") or intent).strip().lower()
    if mode not in RESPONSE_MODES:
        mode = "conversational"
    domain = (data.get("domain_status") or _DOMAIN_IN).strip().lower()
    if domain not in (_DOMAIN_IN, _DOMAIN_ADJACENT, _DOMAIN_OFF):
        domain = _DOMAIN_IN
    return {
        "primary_intent": intent,
        "response_mode": mode,
        "domain_status": domain,
        "should_search": bool(data.get("should_search")),
        "should_recommend": bool(data.get("should_recommend")),
        "should_compare": bool(data.get("should_compare")),
        "should_answer_knowledge": bool(data.get("should_answer_knowledge")),
        "confidence": min(1.0, max(0.0, float(data.get("confidence") or 0.7))),
        "reason": str(data.get("reason") or "llm_semantic"),
        "missing_fields": list(data.get("missing_fields") or []),
        "corrected_message": (data.get("corrected_message") or "").strip(),
    }


async def understand_turn_semantically(
    message: str,
    *,
    parsed: dict | None = None,
    context: dict | None = None,
) -> SemanticTurnUnderstanding:
    """
    LLM-first semantic understanding with strict JSON validation + rules fallback.
    """
    rules_result = _rules_understand(message, parsed=parsed, context=context)

    if not settings.groq_universal_enabled or not settings.GROQ_API_KEY:
        return rules_result

    text = (message or "").strip()
    if not text:
        return rules_result

    ctx = context or {}
    state_summary = json.dumps({
        "active_flow": (ctx.get("conversation_state") or {}).get("active_flow"),
        "collected": {k: v for k, v in ((ctx.get("conversation_state") or {}).get("collected_fields") or {}).items() if v},
        "last_filters": {k: v for k, v in (ctx.get("last_search_filters") or {}).items() if v},
        "greeted": ctx.get("greeted"),
        "user_name": ctx.get("user_name"),
    }, default=str)[:800]

    prompt = f"""You classify user turns for InfraForge — Indian construction equipment marketplace assistant.
Users write English, Hindi, Hinglish, typos, fragments.

SESSION:
{state_summary}

MESSAGE:
{text}

Return ONLY JSON:
{{
  "corrected_message": "typo-fixed message or empty if unchanged",
  "primary_intent": "machine_search|recommendation|comparison|support|domain_knowledge|meta_help|memory_question|conversational|off_topic|clarification_answer|frustration|greeting",
  "domain_status": "in_domain|adjacent|off_topic",
  "response_mode": "greeting|meta_help|memory_answer|domain_knowledge|recommendation|comparison|machine_search|search_refinement|support|clarification|frustration_recovery|off_topic_redirect|conversational",
  "should_search": false,
  "should_recommend": false,
  "should_compare": false,
  "should_answer_knowledge": false,
  "confidence": 0.0,
  "reason": "one line",
  "missing_fields": []
}}

RULES:
- support/refund/payment/booking issues → support (NOT unsupported listing)
- brand comparisons (JCB vs Komatsu) → comparison
- best machine for digging/road project → recommendation in_domain
- "how can you help" → meta_help NOT wellbeing
- "what is my name" → memory_question
- "are you mad" → frustration NOT wellbeing
- short fragments ("in jaipur", "under 7k") → clarification_answer with should_search true if session has context
- off_topic ONLY for clearly non-construction topics
"""

    try:
        from app.core.groq_client import groq_chat_completion

        response = groq_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            tag="semantic_turn_gateway",
        )
        if not response or not response.choices:
            return rules_result
        content = response.choices[0].message.content or ""
        validated = _validate_llm_payload(_extract_json(content))
        numeric = normalize_message_numerics(validated.get("corrected_message") or text)
        norm_text = numeric["normalized_message"]
        merged_parsed = dict(parsed or parse_query(norm_text))
        if numeric.get("budget_amount") and merged_parsed.get("max_price") is None:
            merged_parsed["max_price"] = numeric["budget_amount"]

        result = SemanticTurnUnderstanding(
            raw_message=text,
            normalized_message=norm_text,
            language=detect_query_language(norm_text),
            primary_intent=validated["primary_intent"],
            domain_status=validated["domain_status"],
            response_mode=validated["response_mode"],
            entities=merged_parsed,
            missing_fields=validated["missing_fields"],
            should_search=validated["should_search"],
            should_recommend=validated["should_recommend"],
            should_compare=validated["should_compare"],
            should_answer_knowledge=validated["should_answer_knowledge"],
            confidence=validated["confidence"],
            reason=validated["reason"],
            layer="groq_semantic",
            is_fragment=rules_result.is_fragment,
            context_reference=rules_result.context_reference,
        )
        if rules_result.is_fragment:
            frag = resolve_fragment_context(
                norm_text,
                conv_state=ctx.get("conversation_state"),
                last_filters=ctx.get("last_search_filters"),
                parsed=merged_parsed,
            )
            result.entities = frag["parsed"]
            result.context_reference = {**rules_result.context_reference, **frag["context_reference"]}
        print(
            "[semantic_gateway]",
            f"intent={result.primary_intent}",
            f"mode={result.response_mode}",
            f"conf={result.confidence}",
        )
        return result
    except Exception as exc:
        print(f"[semantic_gateway] llm_failed -> rules_fallback: {exc}")
        return rules_result
