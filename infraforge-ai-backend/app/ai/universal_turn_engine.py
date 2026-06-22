"""
Universal turn-shape engine — ONE classifier for ALL user messages.

Design principle:
  Classify by *discourse shape* and *signals*, not by memorizing example phrases.

Shapes:
  conversational  — social, name, wellbeing, thanks (no marketplace search)
  comparison      — A vs B, which is better (structural)
  machine_attribute — specs/fuel/weight OF a referenced or last-shown machine
  defer           — hand off to intent router (search, support, recommendation, …)

This scales to paraphrases like:
  "are you fine", "i am fine what about you", "people know me as Rahul",
  "tell me more about it", "what's the weight on that one", etc.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import detect_all_brands, detect_brand, detect_cheaper, detect_requested_category
from app.ai.conversation_context import resolve_referenced_machine
from app.ai.message_normalizer import normalize_user_message
from app.ai.query_parser import parse_query
from app.chatbot.assistant_intelligence import is_greeting
from app.core.config import settings

# ---------------------------------------------------------------------------
# Signal vocabularies (word families — not fixed sentences)
# ---------------------------------------------------------------------------

_WELLBEING_STATE = frozenset({
    "fine", "good", "well", "okay", "ok", "great", "awesome", "alright", "cool",
    "theek", "thik", "badhiya", "achha", "accha", "sahi", "mast", "healthy",
})

_NON_NAME = frozenset({
    "fine", "good", "ok", "okay", "well", "here", "ready", "looking", "searching",
    "trying", "going", "working", "building", "construction", "contractor",
    "interested", "new", "old", "student", "engineer", "driver", "operator",
    "excavator", "machine", "machines", "builder", "from", "the", "a", "an",
    "not", "very", "so", "just", "also", "still", "feeling", "doing", "having",
})

_ASSISTANT_DIRECTED = re.compile(
    r"(?:"
    r"\b(?:you|u|your(?:self)?|aap(?:ka|ki|ke)?|tum(?:hara|hari|he)?)\b"
    r"|(?:how\s+are\s+(?:you|u)|are\s+you\s+(?:fine|ok|okay|good|well|alright))"
    r"|(?:how\s+(?:r|do)\s+(?:you|u))"
    r"|(?:kaise\s+(?:ho|hai|hain)|kya\s+haal)"
    r"|(?:hope\s+you)"
    r")",
    re.I,
)

_RECIPROCAL = re.compile(
    r"(?:"
    r"what\s+about\s+(?:you|u)|how\s+about\s+you|and\s+(?:you|u)|about\s+you"
    r"|aur\s+(?:aap|tum)|aap\s+(?:kaise|kya)|tum\s+(?:kaise|kya)"
    r"|what\s+(?:of|with)\s+you|n\s+you\b"
    r")",
    re.I,
)

_FIRST_PERSON = re.compile(
    r"\b(?:i(?:'m|\s+am)?|im\b|me\b|my\b|myself|main\b|mai\b|mujhe|mera|meri)\b",
    re.I,
)

_THANKS = re.compile(
    r"^(?:thanks?(?:\s+a\s+lot|\s+so\s+much)?|thank\s*you|thx|ty|"
    r"dhanyavaad|shukriya|ok\s+thanks|much\s+appreciated)[\s!.?]*$",
    re.I,
)

_SATISFACTION_ACK_RE = re.compile(
    r"^(?:"
    r"ok(?:ay)?(?:\s+(?:good|nice|perfect|great|fine|cool|thanks|thank\s+you))?|"
    r"good|nice|perfect|great|cool|fine|sounds\s+good|"
    r"theek(?:\s+hai|\s+lag(?:ta|r)\s+hai)?|"
    r"achha(?:\s+hai|\s+lag(?:ta|r)\s+hai)?|"
    r"satisfied|works\s+for\s+me|"
    r"(?:that(?:'s|\s+is)|this(?:'s|\s+is))\s+(?:good|great|perfect|fine|helpful|nice)"
    r")[\s!.?]*$",
    re.I,
)

_APPRECIATION_RE = re.compile(
    r"(?:"
    r"\b(?:good(?:\s+job|\s+work|\s+one)?|great|awesome|superb|excellent|"
    r"perfect|nice|amazing|helpful|useful|well\s+done|nice\s+one|fantastic)\b|"
    r"\byou(?:'re|\s+are)\s+(?:good|great|awesome|helpful|amazing|the\s+best)\b|"
    r"\b(?:bahut|bohot)\s+(?:accha|achha|badhiya|badiya)\b"
    r")",
    re.I,
)


def _has_session_results(session_ctx: dict) -> bool:
    last = session_ctx.get("last_filters") or {}
    if last.get("category") or last.get("city") or last.get("brand"):
        return True
    if session_ctx.get("last_machines_count"):
        return True
    if session_ctx.get("last_visible_results"):
        return True
    return False

_ATTRIBUTE = re.compile(
    r"\b(?:"
    r"spec(?:ification)?s?|detail?s?|info(?:rmation)?|feature?s?|"
    r"dimension?s?|measurement?s?|size|weight|height|width|length|"
    r"capacity|power|engine|hp|torque|bucket|lifting|digging|operating|"
    r"fuel|petrol|diesel|mileage|consumption|efficiency|economy|average|"
    r"performance|output|rating|review|condition|year|"
    r"kitna|kitni|kya\s+hai|batao|bataiye|tell\s+me|show\s+me\s+(?:the\s+)?(?:spec|detail)"
    r")\b",
    re.I,
)

_FUEL_FOCUS = re.compile(
    r"\b(?:fuel|petrol|diesel|mileage|consumption|efficiency|economy|consume|average)\b",
    re.I,
)

_REFERENCE = re.compile(
    r"\b(?:"
    r"this|that|the|it|its|these|those|same|above|previous|last|shown|listed|selected|"
    r"ye|yeh|ye\s+wali|wahi|"
    r"first|second|third|one|option|result|listing|card|"
    r"machine\s+you\s+(?:showed|found|listed|gave|suggested)"
    r")\b",
    re.I,
)

_SEARCH_ACTION = re.compile(
    r"\b(?:"
    r"find|search|show\s+(?:me\s+)?(?:all\s+)?|list|need|want|looking|require|"
    r"get\s+me|dikhao|dikhaiye|chahiye|chaiye|kiraye|rent|hire|buy|purchase|"
    r"book|available|milega|mil\s+sak|dhoond|dhund"
    r")\b",
    re.I,
)

_COMPARATIVE = re.compile(
    r"\b(?:"
    r"compare|comparison|contrast|vs\.?|versus|difference|differ|"
    r"better|worse|prefer|which\s+(?:is|one|brand|machine|model)|"
    r"kaun\s+(?:sa|si|se)|best\s+(?:between|among|option)|"
    r"should\s+i\s+(?:pick|choose|take|go\s+with)|"
    r"acche|achhe|achha|achha|sahi|badhiya|zyada|kam|"
    r"kaisa|kaisi|kaise\s+(?:hai|hain|hote|hoti|better)"
    r")\b",
    re.I,
)

# Hindi/Hinglish: "X ke ... acche hote hai ya Y ke"
_HINDI_VS = re.compile(
    r"(?:"
    r"\w+\s+ke\b.*\b(?:ya|or|vs|versus)\b.*\b(?:\w+\s+ke|\w+)\b"
    r"|(?:acche|achhe|achha|accha|sahi|badhiya)\s*(?:hote|hai|hain|hoti|hot)?\s*(?:hai|hain)?\s*ya\b"
    r"|(?:generally|waise|usually|normally).*\b(?:ya|or|vs|versus)\b"
    r")",
    re.I,
)

_CONTEXT_ACTION = re.compile(
    r"^(?:"
    r"cheaper\s+options?|show\s+cheaper(?:\s+options?)?|sasta\s+options?|"
    r"lower\s+price|more\s+affordable|budget\s+options?|"
    r"compare\s+similar|similar\s+(?:machines?|options?)|"
    r"contact\s+owner|cheaper\s+alternatives?"
    r")[\s!.?]*$",
    re.I,
)

_OR_CONNECTOR = re.compile(
    r"\b(?:or|vs\.?|versus|ya|aur)\b",
    re.I,
)

_BRAND_ALIASES = {
    "cat": "CAT", "caterpillar": "CAT", "jcb": "JCB", "volvo": "Volvo",
    "komatsu": "Komatsu", "tata": "Tata", "mahindra": "Mahindra",
    "epiroc": "EPIROC", "liugong": "Liugong", "sany": "Sany", "hitachi": "Hitachi",
    "hyundai": "Hyundai", "hundai": "Hyundai", "hyundia": "Hyundai",
}

_NAME_PATTERNS = [
    re.compile(
        r"(?:people\s+(?:know|call)\s+me\s+(?:as|by))\s+(?:the\s+name\s+)?([A-Za-z][\w'.-]{1,35})",
        re.I,
    ),
    re.compile(
        r"(?:known\s+as|call\s+me|you\s+can\s+call\s+me|mera\s+naam|naam\s+hai)\s+(?:the\s+name\s+)?([A-Za-z][\w'.-]{1,35})",
        re.I,
    ),
    re.compile(r"(?:my|meri)\s+name\s+(?:is|'s)\s+([A-Za-z][\w'.-]{1,35})", re.I),
    re.compile(r"my\s+name\s+(?:is|'s|[a-z]{1,4})\s+([A-Za-z][\w'.-]{1,35})\b", re.I),
    re.compile(r"my\s+name\s+([A-Za-z][\w'.-]{1,35})\s*$", re.I),
    re.compile(r"(?:this\s+is)\s+([A-Za-z][\w'.-]{1,35})(?:\s+(?:here|speaking))?", re.I),
    re.compile(r"(?:i\s*'?m|i\s+am)\s+([A-Za-z][\w'.-]{1,35})(?:\s|$|[,.!?])", re.I),
    re.compile(
        r"(?:hello|hi|hey|namaste)\s+(?:my\s*self|myself)(?:\s+is)?\s+([A-Za-z][\w'.-]{1,35})\b",
        re.I,
    ),
    re.compile(r"^(?:my\s*self|myself)(?:\s+is)?\s+([A-Za-z][\w'.-]{1,35})\s*$", re.I),
]

_POLITE_SOCIAL = re.compile(
    r"(?:"
    r"my\s+pleasure|pleasure\s+(?:to|is)\s+(?:meet|meeting)|"
    r"(?:it'?s|its)\s+my\s+pleasure|"
    r"nice\s+to\s+meet\s+you|good\s+to\s+meet\s+you|great\s+to\s+meet\s+you|"
    r"pleasure\s+to\s+meet\s+you|likewise|same\s+here|"
    r"good\s+to\s+(?:meet|connect|talk)|"
    r"thank\s+you\s+(?:too|also)|thanks\s+(?:to\s+you|likewise)"
    r")",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z]+", text or "")}


def _clean_name(raw: str) -> Optional[str]:
    if not raw:
        return None
    word = raw.strip().split()[0]
    if len(word) < 2 or word.lower() in _NON_NAME:
        return None
    if word.lower() in _WELLBEING_STATE and len(raw.strip().split()) == 1:
        return None
    return word.title()


def extract_user_name(message: str) -> Optional[str]:
    text = (message or "").strip()
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = _clean_name(m.group(1))
            if name:
                return name
    return None


def _detect_brands(message: str) -> list[str]:
    return detect_all_brands(message)


def _detect_category(message: str) -> Optional[str]:
    cat = detect_requested_category(message)
    if cat:
        return cat
    for c in (
        "road roller", "backhoe loader", "crawler drill", "dump truck", "motor grader",
        "wheel loader", "hydra crane", "truck mounted crane", "concrete mixer",
        "excavator", "crane", "bulldozer", "compactor", "telehandler", "forklift",
    ):
        if re.search(c.replace(" ", r"\s+"), message or "", re.I):
            return c
    return None


def _is_strong_search_shape(message: str, parsed: dict) -> bool:
    text = message or ""
    if parsed.get("category") and parsed.get("city"):
        return True
    if _SEARCH_ACTION.search(text) and (parsed.get("category") or parsed.get("city")):
        return True
    if parsed.get("max_price") is not None and parsed.get("category"):
        return True
    if re.search(r"\b(?:under|below|upto|up\s+to|se\s+kam)\b", text, re.I) and parsed.get("category"):
        return True
    return False


def _conversational_subtype(message: str, parsed: dict, session_ctx: dict) -> Optional[str]:
    text = (message or "").strip()
    if not text:
        return None

    if _THANKS.match(text):
        return "thanks"

    if _SATISFACTION_ACK_RE.match(text) and _has_session_results(session_ctx):
        return "satisfaction"

    if _APPRECIATION_RE.search(text) and not _is_strong_search_shape(text, parsed):
        return "appreciation"

    if _POLITE_SOCIAL.search(text) and not _is_strong_search_shape(text, parsed):
        return "polite_social"

    from app.ai.knowledge_query_engine import detect_knowledge_query

    if detect_knowledge_query(text, parsed, session_ctx=session_ctx or {}):
        return None

    from app.ai.semantic_turn_gateway import _META_HELP_RE, _FRUSTRATION_RE, _MEMORY_QUESTION_RE

    if _META_HELP_RE.search(text) or _FRUSTRATION_RE.search(text) or _MEMORY_QUESTION_RE.search(text):
        return None

    name = extract_user_name(text)
    if name:
        return "name_intro"

    toks = _tokens(text)
    has_wellbeing_word = bool(toks & _WELLBEING_STATE)
    has_reciprocal = bool(_RECIPROCAL.search(text))
    assistant_directed = bool(_ASSISTANT_DIRECTED.search(text))
    first_person = bool(_FIRST_PERSON.search(text))

    # "how are you" / wellbeing — NOT meta-help ("how can you help me")
    if assistant_directed and re.search(
        r"(?:fine|ok|okay|well|good|alright|theek|thik|healthy|great)", text, re.I
    ):
        if not _META_HELP_RE.search(text):
            return "wellbeing"

    if assistant_directed and re.search(
        r"(?:how|kaise|kya\s+haal|doing|going)", text, re.I
    ):
        if not _META_HELP_RE.search(text):
            return "wellbeing"

    # "i am fine what about you"
    if first_person and has_wellbeing_word and has_reciprocal:
        return "wellbeing_reciprocal"

    if has_reciprocal and first_person and has_wellbeing_word and not _is_strong_search_shape(text, parsed):
        return "wellbeing_reciprocal"

    # "i am fine" / "doing good" — acknowledge, no search
    if first_person and has_wellbeing_word and not _is_strong_search_shape(text, parsed):
        if not parsed.get("category") and not parsed.get("city"):
            return "user_state"

    # Short social without marketplace entities — never hijack knowledge questions
    if (
        len(text.split()) <= 8
        and not parsed.get("category")
        and not parsed.get("city")
        and not parsed.get("brand")
        and (assistant_directed or has_reciprocal or has_wellbeing_word)
        and not _SEARCH_ACTION.search(text)
        and not detect_knowledge_query(text, parsed, session_ctx=session_ctx or {})
    ):
        return "wellbeing"

    return None


def _comparison_shape(message: str, parsed: dict) -> Optional[dict[str, Any]]:
    text = (message or "").strip()
    if not text:
        return None

    # Chip actions are contextual refine, not open-ended comparison.
    if _CONTEXT_ACTION.match(text):
        return None

    brands = _detect_brands(text)
    category = _detect_category(text)
    has_cmp = bool(_COMPARATIVE.search(text))
    has_or = bool(_OR_CONNECTOR.search(text))
    has_hindi_vs = bool(_HINDI_VS.search(text))

    if not has_cmp and not (len(brands) >= 2 and has_or) and not (
        has_hindi_vs and (len(brands) >= 2 or category)
    ):
        return None

    # Pure attribute question without compare — not comparison
    if _ATTRIBUTE.search(text) and not has_cmp and not has_hindi_vs and len(brands) < 2:
        return None

    needs_clarification = len(brands) < 2 and not category
    if (has_cmp or has_hindi_vs) and (len(brands) >= 2 or category or "which" in text.lower()):
        needs_clarification = len(brands) < 2 and not category and "which" not in text.lower()

    return {
        "shape": "comparison",
        "brands": brands,
        "category": category,
        "needs_clarification": needs_clarification and len(brands) < 2,
    }


def _contextual_refine_shape(
    message: str,
    result_ctx: dict,
    last_filters: dict,
    session_ctx: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    """Chip / short follow-ups that reuse session context (cheaper, similar, etc.)."""
    text = (message or "").strip()
    if not text:
        return None

    has_ctx = bool(result_ctx.get("last_machines")) or bool(
        last_filters.get("category") or last_filters.get("city")
    )
    if not has_ctx:
        return None

    action: Optional[str] = None
    if _CONTEXT_ACTION.match(text) or (
        detect_cheaper(text) and len(text.split()) <= 5
    ):
        if re.search(r"compare\s+similar|similar\s+(?:machines?|options?)", text, re.I):
            action = "compare_similar"
        elif re.search(r"contact\s+owner", text, re.I):
            action = "contact_owner"
        elif detect_cheaper(text) or re.search(r"cheaper|sasta|affordable|lower\s+price", text, re.I):
            action = "cheaper_options"

    if not action:
        # Signal families — NOT fixed chip sentences
        words = len(text.split())
        if words <= 12:
            if detect_cheaper(text) or re.search(
                r"\b(?:sasta|kam\s+price|low\s+budget|less\s+expensive|affordable)\b", text, re.I
            ):
                action = "cheaper_options"
            elif re.search(
                r"\b(?:similar|comparable|same\s+kind|us\s+jese|aisa\s+hi|dusra\s+option)\b",
                text,
                re.I,
            ):
                action = "compare_similar"
            elif re.search(
                r"\b(?:contact\s+owner|call\s+owner|owner\s+se|seller|phone\s+number)\b",
                text,
                re.I,
            ):
                action = "contact_owner"

    if not action:
        return None

    ref = resolve_referenced_machine(
        text,
        result_ctx,
        selected_machine=(session_ctx or {}).get("selected_machine"),
    ) or result_ctx.get("top_machine")
    filters = {
        k: last_filters.get(k)
        for k in ("category", "city", "region", "max_price", "brand", "listing_type")
        if last_filters.get(k) is not None
    }
    if action == "cheaper_options" and filters:
        from app.ai.search_refinement_engine import apply_search_refinement

        refined = apply_search_refinement(
            text,
            last_filters=filters,
            intent_family="search_refinement",
        )
        if refined.get("filters"):
            filters = refined["filters"]
    return {
        "shape": "contextual_refine",
        "action": action,
        "machine": ref,
        "filters": filters,
    }


def _attribute_shape(
    message: str,
    parsed: dict,
    result_ctx: dict,
    last_filters: dict,
) -> Optional[dict[str, Any]]:
    text = (message or "").strip()
    if not _ATTRIBUTE.search(text):
        return None

    # New search disguised as question: "what excavators are available in jaipur"
    if _is_strong_search_shape(text, parsed) and not _REFERENCE.search(text):
        if re.search(r"\b(?:available|list|show|find|search|chahiye)\b", text, re.I):
            return None

    has_context = bool(result_ctx.get("last_machines")) or bool(last_filters.get("category"))
    has_ref = bool(_REFERENCE.search(text))

    ref = resolve_referenced_machine(text, result_ctx)
    machines = result_ctx.get("last_machines") or []
    if not ref and machines and (has_ref or not _is_strong_search_shape(text, parsed)):
        ref = machines[0]

    # Explicit machine name in message with attribute ask
    if not ref and (parsed.get("brand") or parsed.get("model")) and not parsed.get("city"):
        ref = {"name": f"{parsed.get('brand') or ''} {parsed.get('model') or ''}".strip()}

    if not ref and not has_context:
        return None

    if not ref and has_context:
        return {"shape": "machine_attribute", "subtype": "need_reference"}

    subtype = "fuel" if _FUEL_FOCUS.search(text) and not re.search(
        r"\b(?:spec|dimension|weight|size)\b", text, re.I
    ) else "specs"

    return {
        "shape": "machine_attribute",
        "subtype": subtype,
        "machine": ref,
    }


def analyze_universal_turn(
    message: str,
    *,
    session_ctx: Optional[dict] = None,
    result_ctx: Optional[dict] = None,
    last_filters: Optional[dict] = None,
    greeted: bool = False,
) -> dict[str, Any]:
    """
    Single universal classifier. Returns shape + handler payload.

    Priority (first match wins):
      1. greeting / conversational — social turns
      2. selected_machine — act on UI-selected or referenced listing (no fresh search)
      3. comparison     — structural compare before search eats brands
      4. machine_attribute — ask ABOUT machine, not FIND machine
      5. defer          — router handles search/support/recommendation
    """
    text = (message or "").strip()
    norm = normalize_user_message(text)
    text = norm.corrected.strip()
    session_ctx = session_ctx or {}
    result_ctx = result_ctx or {}
    last_filters = last_filters or {}
    parsed = parse_query(text)

    base: dict[str, Any] = {
        "shape": "defer",
        "confidence": 0.5,
        "reason": "default_defer",
        "parsed": parsed,
        "original_message": (message or "").strip(),
        "normalized_message": text,
    }
    if norm.corrections:
        base["normalization"] = norm.to_dict()

    # Pure greetings — conversational shape (social draft preserved downstream)
    if is_greeting(text):
        return {
            **base,
            "shape": "conversational",
            "subtype": "greeting",
            "confidence": 0.95,
            "reason": "greeting_conversational",
            "turn_type": "greeting",
            "assistant_mode": "conversational",
            "user_name": session_ctx.get("user_name"),
        }

    # Direct knowledge answers — identity, definitions (never search)
    from app.ai.knowledge_query_engine import detect_knowledge_query

    knowledge = detect_knowledge_query(text, parsed, session_ctx=session_ctx)
    if knowledge:
        return {
            **base,
            "shape": "knowledge_answer",
            "confidence": 0.92,
            "reason": knowledge.get("reason") or "knowledge_query",
            "turn_type": "knowledge_answer",
            "assistant_mode": "advisory",
            "kind": knowledge.get("kind"),
            "subject": knowledge.get("subject"),
            "subject_type": knowledge.get("subject_type"),
        }

    # Selected / referenced machine — book or contact owner (never fresh search)
    from app.ai.selected_machine_context import detect_selected_machine_turn

    sel_turn = detect_selected_machine_turn(
        text,
        parsed,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
    )
    if sel_turn:
        return {
            **base,
            "shape": "selected_machine",
            "confidence": 0.9,
            "reason": sel_turn.get("reason") or "selected_machine",
            "turn_type": "selected_machine",
            "assistant_mode": sel_turn.get("action", "booking_guidance"),
            "action": sel_turn.get("action"),
            "machine": sel_turn.get("machine"),
        }

    # 0) Budget follow-up defer — before contextual chip refine
    from app.ai.intent_signals import (
        is_cheaper_option_signal,
        is_frustration_signal,
        is_higher_budget_signal,
        is_machine_brand_query_signal,
        is_recommendation_broad_signal,
    )
    from app.chatbot.assistant_intelligence import is_recommendation_query

    budget_ctx = {"last_filters": last_filters or {}}
    if is_higher_budget_signal(text, budget_ctx, parsed):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.86,
            "reason": "higher_budget_defer",
            "turn_type": "higher_budget_query",
            "assistant_mode": "machine_search",
        }

    if is_cheaper_option_signal(text, budget_ctx, parsed) and not _CONTEXT_ACTION.match(text):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.85,
            "reason": "cheaper_refinement_defer",
            "turn_type": "cheaper_option_query",
            "assistant_mode": "machine_search",
        }

    # 0b) Contextual chip actions (cheaper / compare similar) — before broad compare
    refine = _contextual_refine_shape(text, result_ctx, last_filters, session_ctx)
    if refine:
        return {
            **base,
            **refine,
            "confidence": 0.87,
            "reason": f"contextual_{refine.get('action')}",
            "turn_type": "contextual_refine",
            "assistant_mode": refine.get("action", "contextual_refine"),
        }

    from app.ai.intent_signals import (
        is_frustration_signal,
        is_machine_brand_query_signal,
        is_machine_comparison_signal,
        is_recommendation_broad_signal,
    )
    from app.chatbot.assistant_intelligence import is_recommendation_query

    # Defer frustration / recommendation / brand-inventory before conversational swallow
    if is_frustration_signal(text):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.9,
            "reason": "frustration_defer",
            "turn_type": "frustration",
            "assistant_mode": "support",
        }

    if is_recommendation_broad_signal(text, parsed) or (
        is_recommendation_query(text) and not _is_strong_search_shape(text, parsed)
    ):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.88,
            "reason": "recommendation_defer",
            "turn_type": "machine_recommendation",
            "assistant_mode": "recommendation_clarification",
        }

    if is_machine_brand_query_signal(text, parsed):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.87,
            "reason": "brand_query_defer",
            "turn_type": "machine_brand_query",
            "assistant_mode": "brand_query",
        }

    # Comparison — structural shape for in-chat compare (never defer to search)
    cmp = _comparison_shape(text, parsed)
    if not cmp and is_machine_comparison_signal(text, parsed):
        brands = _detect_brands(text) or list(parsed.get("brands") or [])
        category = _detect_category(text) or parsed.get("category")
        cmp = {
            "shape": "comparison",
            "brands": brands,
            "category": category,
            "needs_clarification": len(brands) < 2 and not category,
        }

    if cmp and not (
        _is_strong_search_shape(text, parsed)
        and not _COMPARATIVE.search(text)
        and not _HINDI_VS.search(text)
    ):
        return {
            **base,
            **cmp,
            "confidence": 0.88,
            "reason": "comparison_signal" if is_machine_comparison_signal(text, parsed) else "structural_comparison",
            "turn_type": "machine_comparison",
            "assistant_mode": "comparison",
            "original_message": (message or "").strip(),
        }

    # 3) Machine attribute (specs / fuel / dimensions)
    attr = _attribute_shape(text, parsed, result_ctx, last_filters)
    if attr:
        return {
            **base,
            **attr,
            "confidence": 0.86,
            "reason": "attribute_query_with_context",
            "turn_type": "machine_detail",
            "assistant_mode": attr.get("assistant_mode")
            or ("clarification" if attr.get("subtype") == "need_reference" else "machine_detail"),
        }

    # 4) Conversational — only when NOT a strong marketplace search
    from app.ai.context_routing_gate import (
        FAMILY_FRUSTRATION,
        FAMILY_RETURN_REFUND,
        FAMILY_SUPPORT,
        get_current_gate,
    )
    gate = get_current_gate() or {}
    if gate.get("family") in (FAMILY_FRUSTRATION, FAMILY_SUPPORT, FAMILY_RETURN_REFUND):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.9,
            "reason": f"gate_{gate.get('family')}_defer",
            "turn_type": gate.get("family"),
            "assistant_mode": "support",
        }
    if gate.get("features", {}).get("insult_stem") and gate.get("features", {}).get("assistant_directed"):
        return {
            **base,
            "shape": "defer",
            "confidence": 0.92,
            "reason": "gate_insult_defer",
            "turn_type": "frustration",
            "assistant_mode": "support",
        }

    if not _is_strong_search_shape(text, parsed):
        subtype = _conversational_subtype(text, parsed, session_ctx)
        if subtype:
            return {
                **base,
                "shape": "conversational",
                "subtype": subtype,
                "confidence": 0.84,
                "reason": f"conversational_{subtype}",
                "turn_type": "conversational",
                "assistant_mode": "conversational",
                "user_name": extract_user_name(text) or session_ctx.get("user_name"),
            }

    return {**base, "turn_type": "defer", "assistant_mode": "defer"}


async def analyze_universal_turn_async(
    message: str,
    *,
    session_ctx: Optional[dict] = None,
    result_ctx: Optional[dict] = None,
    last_filters: Optional[dict] = None,
    greeted: bool = False,
) -> dict[str, Any]:
    """
    Universal classifier: fast rules + Groq semantic for ANY phrasing.

    Rules handle high-confidence structural cases (fast, offline).
    Groq semantic runs when rules defer or confidence is low — handles
    typos, Hindi, indirect questions the user has NOT explicitly listed.
    """
    rules = analyze_universal_turn(
        message,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
        last_filters=last_filters,
        greeted=greeted,
    )

    rules_shape = rules.get("shape")
    rules_conf = float(rules.get("confidence") or 0)

    # Greeting — never override with semantic downgrade
    if rules.get("reason") in ("greeting_defer", "greeting_conversational"):
        return rules

    # Fast path — rules are clearly sure (no API call)
    if rules_shape != "defer" and rules_conf >= 0.86:
        return rules

    from app.ai.semantic_turn_classifier import classify_turn_semantically

    text = rules.get("normalized_message") or (message or "").strip()
    semantic = await classify_turn_semantically(
        text,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
        last_filters=last_filters,
        greeted=greeted,
        parsed=rules.get("parsed") or {},
    )
    if not semantic:
        if settings.groq_universal_enabled and rules_shape == "defer":
            rules = {**rules, "ai_fallback_used": True}
        return rules

    sem_conf = float(semantic.get("confidence") or 0)

    # Semantic wins when rules had no answer OR semantic is more confident
    if rules_shape == "defer" or sem_conf >= rules_conf:
        # Preserve rule normalization if semantic didn't add its own
        if rules.get("normalization") and not semantic.get("normalization"):
            semantic["normalization"] = rules["normalization"]
        return semantic

    return rules


# ---------------------------------------------------------------------------
# Thin adapters for assistant_brain / router (backward compatible)
# ---------------------------------------------------------------------------

def detect_conversational_turn(
    message: str,
    *,
    session_ctx: dict,
    greeted: bool,
) -> Optional[dict[str, Any]]:
    turn = analyze_universal_turn(
        message, session_ctx=session_ctx, greeted=greeted,
    )
    if turn.get("shape") == "conversational":
        return turn
    return None


def detect_comparison_turn(message: str) -> Optional[dict[str, Any]]:
    turn = analyze_universal_turn(message)
    if turn.get("shape") == "comparison":
        return turn
    return None


def detect_machine_detail_turn(
    message: str,
    *,
    result_ctx: dict,
    last_filters: dict,
) -> Optional[dict[str, Any]]:
    turn = analyze_universal_turn(
        message, result_ctx=result_ctx, last_filters=last_filters,
    )
    if turn.get("shape") == "machine_attribute":
        return turn
    return None
