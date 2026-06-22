"""
Smart marketplace assistant behaviors: greetings, clarification, recommendations,
no-result enrichment, too-many-results guardrails, and human handover.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.core.config import settings
from app.ai.category_mapping import category_label, detect_requested_category
from app.ai.query_parser import parse_query
from app.chatbot.language import (
    localized_city_category,
    localized_clarification,
    localized_greeting,
    localized_irrelevant,
    localized_purpose_clarification,
    localized_recommendation_clarification,
    localized_too_many_results,
)

# ---------------------------------------------------------------------------
# Greetings
# ---------------------------------------------------------------------------

_GREETING_RE = re.compile(
    r"^(?:"
    r"(?:h+i+|he+l+o+|hey+|hola|namaste|namaskar|good\s*(?:morning|afternoon|evening|night))"
    r"(?:\s+there)?"
    r"|(?:hi|hello|hey)\s+there"
    r")[\s!.?,]*$",
    re.I,
)

_GREETING_CHIPS = [
    "Search Machine",
    "Upload Image",
    "Ask About Rental",
    "Upload Document",
]

# ---------------------------------------------------------------------------
# Recommendation / advisory intents
# ---------------------------------------------------------------------------

_RECOMMENDATION_RE = re.compile(
    r"(?:"
    r"best\s+machine|kaunsi\s+machine|which\s+machine|recommend|suggest|advice|salah|"
    r"project\s+ke\s+liye|ke\s+liye\s+best|"
    r"help\s+(?:me\s+)?(?:find(?:ing)?|choos(?:e|ing))\s+(?:a\s+)?machine|"
    r"machine\s+suggest|suggest\s+karo|sahi\s+rahegi|should\s+i\s+use"
    r")",
    re.I,
)

_PROJECT_TYPES = {
    "highway": {
        "label": "Highway",
        "categories": ["motor grader", "road roller", "excavator", "dump truck"],
    },
    "urban": {
        "label": "Urban road",
        "categories": ["road roller", "compactor", "backhoe loader"],
    },
    "earthwork": {
        "label": "Earthwork",
        "categories": [
            "excavator", "backhoe loader", "dump truck", "wheel loader", "crawler drill",
        ],
    },
    "compaction": {
        "label": "Compaction",
        "categories": ["road roller", "compactor", "drum roller"],
    },
    "concrete": {
        "label": "Concrete road",
        "categories": ["concrete mixer", "concrete mixer truck", "concrete pump"],
    },
    "transport": {
        "label": "Material transport",
        "categories": ["dump truck", "tipper", "wheel loader"],
    },
    "lifting": {
        "label": "Lifting / crane work",
        "categories": ["crane", "hydra crane", "truck mounted crane"],
    },
    "building": {
        "label": "Building construction",
        "categories": [
            "crane", "concrete mixer", "boom lift", "scissor lift",
            "forklift", "backhoe loader",
        ],
    },
    "mining": {
        "label": "Mining",
        "categories": [
            "excavator", "dump truck", "wheel loader", "crawler drill", "mobile crusher",
        ],
    },
    "demolition": {
        "label": "Demolition",
        "categories": [
            "excavator", "mobile crusher", "crane", "backhoe loader",
        ],
    },
}

_PROJECT_TYPE_OPTIONS = {
    "1": "highway",
    "2": "urban",
    "3": "earthwork",
    "4": "compaction",
    "5": "concrete",
    "6": "transport",
    "7": "lifting",
    "highway": "highway",
    "urban road": "urban",
    "urban": "urban",
    "earthwork": "earthwork",
    "compaction": "compaction",
    "concrete road": "concrete",
    "concrete": "concrete",
    "material transport": "transport",
    "transport": "transport",
    "lifting": "lifting",
    "lifting / crane work": "lifting",
    "crane work": "lifting",
}

_PROJECT_KEYWORDS = {
    "highway": ("highway", "nh", "expressway"),
    "urban": ("urban", "city road", "internal road"),
    "earthwork": ("earthwork", "excavation", "digging", "khudai"),
    "compaction": ("compaction", "compact", "soil compaction"),
    "leveling": ("leveling", "levelling", "grading", "road leveling", "road levelling"),
    "concrete": ("concrete road", "concrete", "cement", "rcc"),
    "transport": ("transport", "haul", "material transport"),
    "lifting": ("lifting", "lift work", "crane work", "erection"),
    "building": (
        "building construction", "building project", "construction project",
        "high rise", "structure",
    ),
    "mining": ("mining", "mine", "quarry", "mineral"),
    "demolition": ("demolition", "wrecking", "breakdown", "todna"),
}

_CATEGORY_CHIPS = [
    "Excavator",
    "JCB / Backhoe Loader",
    "Crane",
    "Road Roller",
    "Dump Truck",
    "Crawler Drill",
]

# Purpose-based alternatives when exact category unavailable in a city.
_PURPOSE_OPTIONS = {
    "1": "digging",
    "2": "loading",
    "3": "lifting",
    "4": "compaction",
    "5": "transport",
    "6": "drilling",
    "digging": "digging",
    "excavation": "digging",
    "earthwork": "digging",
    "khudai": "digging",
    "khodna": "digging",
    "khodni": "digging",
    "loading": "loading",
    "material handling": "loading",
    "lifting": "lifting",
    "height": "lifting",
    "erection": "lifting",
    "compaction": "compaction",
    "road work": "compaction",
    "leveling": "leveling",
    "levelling": "leveling",
    "grading": "leveling",
    "transport": "transport",
    "hauling": "transport",
    "drilling": "drilling",
    "boring": "drilling",
}

_PURPOSE_LABELS = {
    "digging": "Digging / excavation / earthwork",
    "loading": "Loading / material handling",
    "lifting": "Lifting / height work",
    "compaction": "Compaction / road work",
    "leveling": "Road leveling / grading",
    "transport": "Transport / hauling",
    "drilling": "Drilling / boring",
    "concrete": "Concrete pouring / placement",
}

# Canonical purpose → machine categories (single source of truth)
PURPOSE_TO_MACHINE: dict[str, list[str]] = {
    "digging": ["excavator", "backhoe loader"],
    "loading": ["wheel loader", "backhoe loader", "forklift"],
    "lifting": ["crane", "hydra crane"],
    "compaction": ["road roller", "compactor"],
    "leveling": ["motor grader"],
    "transport": ["dump truck", "tipper"],
    "drilling": ["crawler drill"],
    "concrete": ["concrete mixer", "concrete pump", "concrete mixer truck"],
}

# Alias map — spoken terms → canonical purpose key
PURPOSE_ALIASES: dict[str, str] = {
    "digging": "digging",
    "excavation": "digging",
    "excavate": "digging",
    "earthwork": "digging",
    "khudai": "digging",
    "khodna": "digging",
    "khodni": "digging",
    "loading": "loading",
    "material handling": "loading",
    "lifting": "lifting",
    "height": "lifting",
    "erection": "lifting",
    "compaction": "compaction",
    "compact": "compaction",
    "compacting": "compaction",
    "dabana": "compaction",
    "road work": "compaction",
    "road leveling": "leveling",
    "road levelling": "leveling",
    "leveling": "leveling",
    "levelling": "leveling",
    "grading": "leveling",
    "transport": "transport",
    "saman le jana": "transport",
    "material shifting": "transport",
    "hauling": "transport",
    "haulage": "transport",
    "drilling": "drilling",
    "boring": "drilling",
    "upar uthana": "lifting",
    "crane work": "lifting",
    "concrete": "concrete",
}

_PURPOSE_CATEGORIES = PURPOSE_TO_MACHINE  # backward compat

# Ordered patterns — first match per purpose key only once.
_PURPOSE_SIGNAL_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:mitti\s+khod|khodni|khodna|trench(?:ing)?)\b", "digging"),
    (r"\b(?:road\s+dig(?:ging)?|digging\s+road|for\s+digging)\b", "digging"),
    (r"\b(?:digging|excavation|excavate|khudai|earthwork)\b", "digging"),
    (r"\b(?:level(?:ing|ling)\s+(?:the\s+)?road|road\s+level(?:ing|ling)|grading)\b", "leveling"),
    (r"\b(?:dabana|compact(?:ion|ing)?|compactor|compacting|roller)\b", "compaction"),
    (r"\bconcrete\b", "concrete"),
    (r"\b(?:upar\s+utha|crane\s+work|lifting|erection|height\s+work)\b", "lifting"),
    (r"\b(?:drilling|boring)\b", "drilling"),
    (r"\b(?:saman\s+le\s+jana|material\s+shift(?:ing)?|transport|hauling|haulage)\b", "transport"),
    (r"\b(?:loading|material\s+handling|unload(?:ing)?)\b", "loading"),
    (r"\b(?:road\s+work|highway|paving)\b", "compaction"),
]

_VAGUE_QUERY_RE = re.compile(
    r"^(?:"
    r"machine|machines|equipment|machinery|saman|"
    r"machine\s+chahiye|machines?\s+chahiye|equipment\s+chahiye|machinery\s+chahiye|"
    r"i\s+(?:need|want)\s+(?:a?\s+)?(?:machine|machines|equipment|machinery)|"
    r"need\s+(?:a?\s+)?(?:machine|machines|equipment|machinery)|"
    r"machine\s+(?:needed|required)|machinery\s+(?:needed|required)|"
    r"mujhe\s+(?:machine|equipment|machinery)\s+chahiye|"
    r"construction\s+machine(?:\s+chahiye)?"
    r")[\s!.?]*$",
    re.I,
)

_BROAD_VAGUE_RE = re.compile(
    r"(?:^show\s+me\s+)?(?:everything|all\s+machines?|anything|kuch\s+bhi|koi\s+bhi)",
    re.I,
)
_KUCH_BHI_MACHINE_RE = re.compile(
    r"(?:kuch\s+bhi|koi\s+bhi|anything).{0,30}\bmachine|machine\s+dedo|dedo\s+.*machine",
    re.I,
)
_CHEAPEST_VAGUE_RE = re.compile(
    r"\b(?:cheapest|sasta|lowest\s+price|sabse\s+sasta)\b.{0,40}\b(?:thing|available|option|machine|equipment)\b",
    re.I,
)

_REAL_ESTATE_RE = re.compile(
    r"\b(?:house|flat|apartment|property|plot|villa|bungalow|real\s*estate|"
    r"rent\s+a\s+house|sell\s+(?:my\s+)?house|buy\s+(?:a\s+)?house)\b",
    re.I,
)
_FOOD_ORDER_RE = re.compile(
    r"\b(?:pizza|burger|biryani\s+order|food\s+delivery|order\s+food|zomato|swiggy)\b",
    re.I,
)

_NEGATIVE_PIVOT_RE = re.compile(
    r"^(?:no|nahi|na|nah|nope|mat|cancel)[\s!.?]*$",
    re.I,
)

_CITY_ONLY_RE = re.compile(
    r"^(?:in\s+)?([a-z\s]+)[\s!.?]*$",
    re.I,
)

_CHAHIYE_RE = re.compile(r"(?:\bchahiye\b|चाहिए)", re.I)

# ---------------------------------------------------------------------------
# Off-topic / abusive / irrelevant message handling
# ---------------------------------------------------------------------------

_ACKNOWLEDGMENT_RE = re.compile(
    r"^(?:thanks?|thank\s*you|thx|ok(?:ay)?|done|got\s*it|fine|cool|"
    r"theek(?:\s*hai)?|dhanyavaad|shukriya|accha)[\s!.?]*$",
    re.I,
)

_DISRESPECTFUL_RE = re.compile(
    r"\b("
    r"chutiy\w*|bsdk|bc\b|madarchod|behenchod|bhenchod|gandu|randi|"
    r"saala|kutta|kamine|harami|idiot|stupid|dumbass|moron|shut\s*up|"
    r"get\s*lost|go\s*to\s*hell|fuck\w*|shit|asshole"
    r")\b",
    re.I,
)

_OFF_TOPIC_RE = re.compile(
    r"(weather|temperature|cricket\s*score|ipl|who\s+won|tell\s+me\s+a\s+joke|"
    r"sing\s+a\s+song|play\s+music|movie|film|bollywood|hollywood|netflix|"
    r"prime\s*video|web\s*series|tv\s*show|action\s+movie|comedy\s+movie|"
    r"song|album|recipe\s+for|girlfriend|boyfriend|dating|politics|election|"
    r"bitcoin|stock\s+market|homework|assignment\s+help|write\s+an\s+essay|"
    r"translate\s+this|horoscope|astrology|lottery|gaming|video\s+game|"
    r"order\s+pizza|book\s+flight|sell\s+my\s+house)",
    re.I,
)

# Entertainment / lifestyle queries that must never trigger machine search.
_ENTERTAINMENT_RE = re.compile(
    r"\b(movie|movies|film|films|bollywood|hollywood|netflix|series|"
    r"actor|actress|celebrity|song|singer|cricket|football|match\s+score|"
    r"horoscope|recipe|restaurant|hotel\s+booking|flight|train\s+ticket)\b",
    re.I,
)

_SERVICE_SIGNAL_RE = re.compile(
    r"\b("
    r"machine|machines|equipment|saman|excavator|jcb|crane|loader|roller|truck|"
    r"tipper|drill|grader|bulldozer|compactor|mixer|forklift|"
    r"rent|buy|purchase|kiraye|kiraya|chahiye|budget|price|support|help|"
    r"infraforge|search|compare|comparison|recommend|suggest|project|construction|"
    r"image|voice|upload|owner|contact|deal|similar|"
    r"spec|specification|dimension|weight|fuel|petrol|diesel|consumption|mileage|average|"
    r"better|versus|vs\b"
    r")\b",
    re.I,
)

_FOLLOW_UP_SIGNAL_RE = re.compile(
    r"\b(same|what\s+about|cheaper|under|show|options|instead|also)\b",
    re.I,
)

_CITY_INVENTORY_RE = re.compile(
    r"(?:"
    r"(?:what|which|kya|kon\s?si|konsi)"
    r".{0,40}(?:machine|equipment|saman).{0,40}(?:available|availab|hai|hain|milega|milti|list)"
    r"|(?:available|availab).{0,30}(?:machine|equipment).{0,30}(?:in|me|mein)"
    r"|(?:machine|equipment).{0,20}(?:available|list).{0,20}(?:in|me|mein)"
    r")",
    re.I,
)

_BOOKING_GUIDANCE_RE = re.compile(
    r"(?:"
    r"how\s+(?:to|do\s+i|can\s+i)\s+(?:rent|hire|book|contact|call|reach|get|proceed)"
    r"|(?:rent|hire|book|booking)\s+(?:process|procedure|steps?)"
    r"|contact\s+(?:the\s+)?owner|call\s+(?:the\s+)?owner|talk\s+to\s+(?:the\s+)?owner"
    r"|owner\s+(?:contact|details|number|phone|ka\s+number)"
    r"|(?:want|need)\s+to\s+(?:rent|hire|book)\s+(?:it|this|that)"
    r"|(?:rent|hire|book)\s+(?:it|this|that|the\s+machine)"
    r"|kiraye?\s+(?:kaise|ke\s+liye\s+kaise)|booking\s+kaise|rent\s+kaise"
    r"|(?:this|that)\s+machine\s+is\s+good"
    r"|proceed\s+with\s+(?:rent|booking)|next\s+step"
    r"|machine\s+(?:acchi|sahi)\s+hai.*(?:rent|kiraye|book)"
    r")",
    re.I,
)


def _parsed_has_search_fields(parsed: dict) -> bool:
    return bool(
        parsed.get("category")
        or parsed.get("city")
        or parsed.get("region")
        or parsed.get("brand")
        or parsed.get("model")
        or parsed.get("listing_type")
        or parsed.get("max_price") is not None
    )


def has_service_signal(message: str, parsed: dict) -> bool:
    """True when the message relates to InfraForge marketplace services."""
    text = (message or "").strip()
    if not text:
        return False
    # Entertainment/lifestyle without equipment terms is never a service query.
    if _ENTERTAINMENT_RE.search(text) and not detect_requested_category(text):
        if not _SERVICE_SIGNAL_RE.search(text):
            return False
    if is_greeting(text):
        return True
    if is_recommendation_query(text):
        return True
    if _parsed_has_search_fields(parsed):
        return True
    if parsed.get("listing_type"):
        return True
    if detect_requested_category(text):
        return True
    if _SERVICE_SIGNAL_RE.search(text):
        return True
    if _FOLLOW_UP_SIGNAL_RE.search(text):
        return True
    if _CHAHIYE_RE.search(text):
        return True
    return False


def is_city_inventory_query(message: str) -> bool:
    """User wants to browse what's available in a city."""
    return bool(_CITY_INVENTORY_RE.search((message or "").strip()))


def is_booking_guidance_query(message: str) -> bool:
    """User wants steps to rent/book/contact owner — not a new machine search."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_BOOKING_GUIDANCE_RE.search(text))


def booking_guidance_message(
    *,
    category: Optional[str] = None,
    city: Optional[str] = None,
    lang: str = "english",
) -> str:
    from app.chatbot.language import localized_booking_guidance

    label = category_label(category) if category else None
    return localized_booking_guidance(label=label, city=city, lang=lang)


def is_broad_vague_query(
    message: str,
    *,
    session_collected: dict | None = None,
) -> bool:
    """True when the user must specify city and/or machine type before any search."""
    from app.ai.session_requirement_context import should_skip_broad_clarification

    text = (message or "").strip()
    if not text:
        return True
    from app.ai.query_parser import parse_query

    parsed = parse_query(text)
    fake_state = {"collected_fields": session_collected or {}} if session_collected else None
    if fake_state and should_skip_broad_clarification(text, fake_state, parsed):
        return False
    if parsed.get("city") or parsed.get("category"):
        return False
    if resolve_purpose_key(text) or detect_requested_category(text):
        return False
    if _VAGUE_QUERY_RE.match(text):
        return True
    if _BROAD_VAGUE_RE.search(text):
        return True
    if _KUCH_BHI_MACHINE_RE.search(text):
        return True
    if _CHEAPEST_VAGUE_RE.search(text):
        return True
    return False


BROAD_MACHINE_CHIPS = [
    "Digging",
    "Compaction",
    "Lifting",
    "Transport",
    "Loading",
    "Road work",
]


def build_broad_machine_request_pending() -> dict:
    return {
        "missing_field": "machine_purpose",
        "type": "machine_purpose",
        "missing": ["purpose", "city"],
        "source": "broad_machine_request",
    }


def broad_machine_clarification_message(*, lang: str = "english") -> str:
    msg = (
        "Sure. What work do you need the machine for — digging, lifting, compaction, "
        "transport, loading — and which city?"
    )
    if lang == "hinglish":
        msg = (
            "Theek hai. Kaunsa kaam hai — digging, lifting, compaction, transport, "
            "loading — aur kaunsa sheher?"
        )
    return msg


def machine_purpose_city_message(purpose_key: str, *, lang: str = "english") -> str:
    label = _PURPOSE_LABELS.get(purpose_key, purpose_key.replace("_", " "))
    cats = map_purpose_to_categories(purpose_key)
    cat_part = ", ".join(category_label(c) for c in cats[:2]) if cats else "the right machine"
    msg = f"Got it — {label}. I'd suggest {cat_part}. Which city is your site in?"
    if lang == "hinglish":
        msg = (
            f"Theek hai — {label}. Main {cat_part} suggest karunga. "
            f"Site kaunse sheher me hai?"
        )
    return msg


def build_broad_machine_request_response(*, lang: str = "english") -> dict:
    return {
        "message": broad_machine_clarification_message(lang=lang),
        "assistant_mode": "clarification",
        "suggestions": list(BROAD_MACHINE_CHIPS),
        "pending": build_broad_machine_request_pending(),
    }


def is_negative_pivot(message: str) -> bool:
    """Short 'no' / 'nahi' — user rejecting a clarification option."""
    return bool(_NEGATIVE_PIVOT_RE.match((message or "").strip()))


def classify_non_service_message(
    message: str,
    parsed: dict,
    *,
    pending: Optional[dict] = None,
) -> Optional[str]:
    """
    Classify irrelevant input.

    Returns:
        "abusive" | "off_topic" | "acknowledgment" | None (service-related)
    """
    text = (message or "").strip()
    if not text:
        return "off_topic"

    # Abuse is never a valid clarification answer — handle immediately.
    if _DISRESPECTFUL_RE.search(text):
        return "abusive"

    if pending and is_clarification_answer(text, pending):
        return None

    if pending and is_negative_pivot(text):
        return None

    # Real estate / food delivery — never machine search even if a city appears.
    if _REAL_ESTATE_RE.search(text):
        return "off_topic"
    if _FOOD_ORDER_RE.search(text):
        return "off_topic"

    # Budget-only vague marketplace queries need clarification, not redirect.
    if _CHEAPEST_VAGUE_RE.search(text):
        return None

    # Off-topic patterns win even when words like "price" appear (e.g. bitcoin price).
    if _OFF_TOPIC_RE.search(text):
        return "off_topic"

    if has_service_signal(text, parsed):
        return None

    if _ACKNOWLEDGMENT_RE.match(text):
        return "acknowledgment"

    if _ENTERTAINMENT_RE.search(text) and not detect_requested_category(text):
        return "off_topic"

    # Default: no marketplace signal → off-topic (never search with stale memory).
    return "off_topic"


def irrelevant_response_message(kind: str, *, lang: str = "english") -> str:
    """Professional reply for non-service messages — never triggers search."""
    return localized_irrelevant(kind, lang)


def is_greeting(message: str) -> bool:
    return bool(_GREETING_RE.match((message or "").strip()))


def greeting_message(*, first_time: bool = True, lang: str = "english") -> str:
    return localized_greeting(first_time=first_time, lang=lang)


def parse_project_type_option(message: str) -> Optional[str]:
    """Map numeric or label replies to a project type key."""
    text = (message or "").strip().lower()
    if not text:
        return None
    if text in _PROJECT_TYPE_OPTIONS:
        return _PROJECT_TYPE_OPTIONS[text]
    for label, key in _PROJECT_TYPE_OPTIONS.items():
        if len(label) > 2 and label in text:
            return key
    return None


def is_recommendation_query(message: str) -> bool:
    text = message or ""
    if _ENTERTAINMENT_RE.search(text) and not detect_requested_category(text):
        return False
    if re.search(
        r"\b(?:demolition|mining|earthwork)\b.{0,40}\b(?:machine|chahiye|chaiye)\b",
        text,
        re.I,
    ):
        return True
    return bool(_RECOMMENDATION_RE.search(text))


def detect_project_type(message: str) -> Optional[str]:
    lower = (message or "").lower()
    for key, words in _PROJECT_KEYWORDS.items():
        if any(w in lower for w in words):
            return key
    return None


def recommendation_clarification_message(*, lang: str = "english") -> str:
    return localized_recommendation_clarification(lang)


def project_type_pending_state() -> dict:
    return {
        "missing_field": "project_type",
        "options": dict(_PROJECT_TYPE_OPTIONS),
    }


def project_categories(project_key: str) -> list[str]:
    return list(_PROJECT_TYPES.get(project_key, {}).get("categories", []))


def build_handover(reason: str, *, lang: str = "english") -> dict:
    from app.ai.assistant_response_style import guided_handover_message

    phone = settings.SUPPORT_PHONE or ""
    whatsapp = settings.SUPPORT_WHATSAPP or phone
    actions = []
    if phone:
        actions.append({"label": "Call", "type": "call", "value": phone})
    if whatsapp:
        actions.append({"label": "WhatsApp", "type": "whatsapp", "value": whatsapp})
    actions.append({"label": "Raise Request", "type": "request", "value": "support"})
    intent_key = reason.split()[0].lower() if reason else "support"
    for key in ("refund", "payment", "order", "delivery", "booking"):
        if key in (reason or "").lower():
            intent_key = f"{key}_issue" if key != "refund" else "refund_return"
            break
    return {
        "enabled": True,
        "reason": reason,
        "message": guided_handover_message(intent_key, lang=lang),
        "actions": actions,
    }


def clarification_question(
    category: Optional[str],
    missing_field: str,
    *,
    city: Optional[str] = None,
    listing_type: Optional[str] = None,
    lang: str = "english",
) -> str:
    label = category_label(category) if category else "machine"
    return localized_clarification(
        lang=lang,
        missing_field=missing_field,
        label=label,
        city=city,
        listing_type=listing_type,
    )


def category_clarification_chips() -> list[str]:
    return list(_CATEGORY_CHIPS)


def city_category_clarification_message(
    city: str,
    available: list[str],
    *,
    lang: str = "english",
    max_show: int = 10,
    nearby_cities: Optional[list[str]] = None,
) -> str:
    """Ask user to pick from categories that actually exist in the city."""
    show = available[:max_show]
    labels = [category_label(c) for c in show]
    more = max(0, len(available) - len(show))
    return localized_city_category(
        city, labels, lang, more_count=more, nearby_cities=nearby_cities,
    )


def chips_from_categories(categories: list[str]) -> list[str]:
    return [category_label(c) for c in categories if c]


def parse_purpose_option(message: str) -> Optional[str]:
    text = (message or "").strip().lower()
    if not text:
        return None
    if text in _PURPOSE_OPTIONS:
        return _PURPOSE_OPTIONS[text]
    for label, key in _PURPOSE_OPTIONS.items():
        if len(label) > 2 and label in text:
            return key
    # User may reply with an alternative machine name directly.
    cat = detect_requested_category(message)
    if cat:
        return f"machine:{cat}"
    return None


def purpose_clarification_message(
    category: str, city: Optional[str], *, lang: str = "english",
) -> str:
    return localized_purpose_clarification(category_label(category), city, lang)


def purpose_clarification_chips() -> list[str]:
    return list(_PURPOSE_LABELS.values())


def build_purpose_pending(
    requested_category: str,
    city: Optional[str],
    *,
    max_price=None,
    listing_type=None,
    brand=None,
    model=None,
) -> dict:
    return {
        "missing_field": "purpose",
        "requested_category": requested_category,
        "category": requested_category,
        "city": city,
        "max_price": max_price,
        "listing_type": listing_type,
        "brand": brand,
        "model": model,
        "options": dict(_PURPOSE_OPTIONS),
    }


def _fuzzy_purpose_key(text: str) -> Optional[str]:
    """Single-word typo tolerance against canonical purpose keys (mechanism-level)."""
    import re
    from rapidfuzz.distance import Levenshtein
    from app.ai.purpose_taxonomy import PURPOSE_TO_CATEGORIES

    raw = (text or "").strip().lower()
    if not raw or len(raw.split()) > 2 or len(raw) < 4:
        return None
    variants = list({raw, re.sub(r"(.)\1+", r"\1", raw)})
    keys = list(PURPOSE_TO_CATEGORIES.keys())
    ranked: list[tuple[int, str]] = []
    for key in keys:
        dist = min(Levenshtein.distance(variant, key) for variant in variants)
        ranked.append((dist, key))
    ranked.sort()
    if not ranked or ranked[0][0] > 3:
        return None
    best_dist = ranked[0][0]
    ties = [key for dist, key in ranked if dist == best_dist]
    if len(ties) == 1:
        return ties[0]
    # Break ties by longest common prefix with collapsed input
    collapsed = variants[-1]
    ties.sort(
        key=lambda key: sum(1 for a, b in zip(collapsed, key) if a == b),
        reverse=True,
    )
    if sum(1 for a, b in zip(collapsed, ties[0]) if a == b) >= 2:
        return ties[0]
    return None


def resolve_purpose_key(message: str) -> Optional[str]:
    """Map free text or alias to canonical purpose key."""
    text = (message or "").strip().lower()
    if not text:
        return None
    if text in PURPOSE_ALIASES:
        return PURPOSE_ALIASES[text]
    for label, key in PURPOSE_ALIASES.items():
        if len(label) > 3 and label in text:
            return key
    key = parse_purpose_option(message)
    if key and not str(key).startswith("machine:"):
        return key
    found = detect_all_work_purposes(message)
    if found:
        return found[0]

    # Fuzzy typo tolerance for short purpose replies (e.g. gidding → digging)
    if text and len(text.split()) <= 2:
        fuzzy = _fuzzy_purpose_key(text)
        if fuzzy:
            return fuzzy
        try:
            from rapidfuzz import process

            choices = list(
                dict.fromkeys(
                    list(PURPOSE_ALIASES.keys()) + list(_PURPOSE_OPTIONS.keys()),
                )
            )
            match = process.extractOne(text, choices, score_cutoff=82)
            if match:
                hit = match[0]
                return PURPOSE_ALIASES.get(hit) or _PURPOSE_OPTIONS.get(hit)
        except Exception:
            pass
    return None


def map_purpose_to_categories(purpose_key: str) -> list[str]:
    """Return machine categories for a canonical purpose key."""
    from app.ai.purpose_taxonomy import categories_for_purpose as _cats_for_purpose
    return _cats_for_purpose(purpose_key)


def categories_for_purpose(purpose_key: str, requested_category: str) -> list[str]:
    """Return alternative categories for a purpose, excluding the one already tried."""
    if purpose_key and purpose_key.startswith("machine:"):
        return [purpose_key.split(":", 1)[1]]

    cats = map_purpose_to_categories(purpose_key or "")
    req = (requested_category or "").lower()
    return [c for c in cats if c != req]


def all_categories_for_purpose(purpose_key: str) -> list[str]:
    """All machine categories suitable for a work purpose."""
    return map_purpose_to_categories(purpose_key)


def detect_work_purpose(message: str) -> Optional[str]:
    """Map free text to a work purpose key (digging, lifting, …)."""
    found = detect_all_work_purposes(message)
    return found[0] if found else None


def detect_all_work_purposes(message: str) -> list[str]:
    """Detect every work purpose mentioned (supports multi-task queries)."""
    text = (message or "").strip().lower()
    if not text:
        return []

    found: list[str] = []
    for pattern, key in _PURPOSE_SIGNAL_PATTERNS:
        if re.search(pattern, text, re.I) and key not in found:
            found.append(key)

    key = parse_purpose_option(message)
    if key and not str(key).startswith("machine:") and key not in found:
        found.insert(0, key)

    for label, purpose in _PURPOSE_OPTIONS.items():
        if len(label) > 3 and label in text and purpose not in found:
            found.append(purpose)

    return found


def primary_category_for_purpose(purpose_key: str) -> Optional[str]:
    """Best default category to search for a work purpose."""
    from app.ai.purpose_taxonomy import primary_category_for_purpose as _primary
    return _primary(purpose_key)


def category_suits_purpose(category: str, purpose_key: str) -> bool:
    cat = (category or "").lower().strip()
    return cat in all_categories_for_purpose(purpose_key)


def needs_clarification(
    merged: dict,
    *,
    list_all: bool,
    message: str,
    pending: Optional[dict],
    last_filters: Optional[dict] = None,
) -> Optional[dict]:
    """Return pending_clarification dict if we should ask before searching."""
    if list_all or pending:
        return None

    category = merged.get("category")
    city = merged.get("city")
    brand = merged.get("brand")
    model = merged.get("model")
    max_price = merged.get("max_price")
    listing_type = merged.get("listing_type")

    # Category / brand only (e.g. "road roller chaiye") — do not guess city.
    if (category or brand) and not city and not model:
        lower = (message or "").strip().lower()
        if (
            _CHAHIYE_RE.search(lower)
            or len(lower.split()) <= 6
            or re.search(r"\b(chaiye|chahiy|need|want)\b", lower)
        ):
            pending_city = {
                "missing_field": "city",
                "category": category,
            }
            if brand:
                pending_city["brand"] = brand
            if max_price is not None:
                pending_city["max_price"] = max_price
            if listing_type:
                pending_city["listing_type"] = listing_type
            return pending_city

    # Rent/buy + city but no category.
    if listing_type and city and not category and not brand and not model:
        return {
            "missing_field": "category",
            "city": city,
            "listing_type": listing_type,
        }

    # City only: ask machine type unless completing a prior category-only query.
    if city and not category and not brand and not model:
        lower = (message or "").strip().lower()
        prior = last_filters or {}
        if prior.get("category") and not prior.get("city"):
            return None
        if (
            is_city_inventory_query(message)
            or (len(lower.split()) <= 12 and not _has_same_reference(lower))
        ):
            return {"missing_field": "category", "city": city}

    # Pincode without machine type — ask category before searching.
    if merged.get("pincode") and not category and not brand:
        return {"missing_field": "category", "pincode": merged.get("pincode")}

    # Budget-only with no prior context — ask machine + city.
    if (
        merged.get("max_price") is not None
        and not category
        and not city
        and not brand
        and not model
    ):
        prior = last_filters or {}
        if not (prior.get("category") or prior.get("city")):
            return {"missing_field": "filters"}

    # Too vague — never run a blind nationwide search.
    if not category and not city and not brand and not model:
        if is_broad_vague_query(message):
            return build_broad_machine_request_pending()

    # Purpose known from pending merge but city missing.
    if merged.get("purpose_key") and merged.get("category") and not city:
        return {
            "missing_field": "machine_purpose",
            "type": "machine_purpose",
            "purpose_key": merged.get("purpose_key"),
            "category": merged.get("category"),
            "missing": ["city"],
            "source": "purpose_without_city",
        }

    # Unknown city token (e.g. "abc city") — ask for a valid city.
    from app.ai.category_mapping import has_unknown_city_phrase

    if has_unknown_city_phrase(message) and not city:
        return {"missing_field": "city", "category": category}

    return None


def apply_pending_answer(
    pending: dict,
    message: str,
    new_filters: dict,
) -> dict:
    """Merge a clarification answer into filters."""
    merged = {
        "category": pending.get("category"),
        "city": pending.get("city"),
        "max_price": None,
        "brand": None,
        "model": None,
        "condition": None,
        "pincode": None,
        "listing_type": None,
        "rent_type": None,
    }
    field = pending.get("missing_field")

    parsed = parse_query(message)
    if field == "project_type":
        project_key = parse_project_type_option(message)
        cats = project_categories(project_key) if project_key else []
        merged["category"] = cats[0] if cats else None
        return merged
    if field == "purpose":
        purpose_key = parse_purpose_option(message)
        alt_cats = categories_for_purpose(
            purpose_key or "", pending.get("requested_category") or "",
        )
        merged["city"] = pending.get("city")
        merged["max_price"] = pending.get("max_price")
        merged["listing_type"] = pending.get("listing_type")
        merged["requested_category"] = pending.get("requested_category")
        merged["purpose_key"] = purpose_key
        merged["alternative_categories"] = alt_cats
        merged["category"] = alt_cats[0] if alt_cats else None
        return merged
    if field == "machine_purpose":
        purpose_key = pending.get("purpose_key") or resolve_purpose_key(message)
        if not purpose_key:
            purpose_key = parse_purpose_option(message)
            if purpose_key and str(purpose_key).startswith("machine:"):
                merged["category"] = purpose_key.split(":", 1)[1]
                purpose_key = None
        parsed = parse_query(message)
        city = pending.get("city") or parsed.get("city") or new_filters.get("city")
        merged["purpose_key"] = purpose_key
        merged["city"] = city
        merged["max_price"] = (
            parsed.get("max_price")
            or pending.get("max_price")
            or new_filters.get("max_price")
        )
        merged["listing_type"] = (
            new_filters.get("listing_type")
            or parsed.get("listing_type")
            or pending.get("listing_type")
        )
        if purpose_key:
            cats = map_purpose_to_categories(purpose_key)
            merged["category"] = cats[0] if cats else None
            merged["alternative_categories"] = cats[1:4] if len(cats) > 1 else []
        elif detect_requested_category(message):
            merged["category"] = detect_requested_category(message)
        return merged
    if field == "city":
        merged["category"] = pending.get("category") or new_filters.get("category")
        merged["city"] = new_filters.get("city") or parsed.get("city")
        merged["max_price"] = (
            pending.get("max_price")
            or new_filters.get("max_price")
            or parsed.get("max_price")
        )
        merged["listing_type"] = new_filters.get("listing_type") or parsed.get("listing_type")
    elif field == "category":
        merged["city"] = pending.get("city") or new_filters.get("city")
        merged["category"] = new_filters.get("category") or parsed.get("category")
        merged["max_price"] = new_filters.get("max_price") or parsed.get("max_price")
        merged["listing_type"] = new_filters.get("listing_type") or parsed.get("listing_type")
    else:
        for key in merged:
            merged[key] = new_filters.get(key) or parsed.get(key)

    # Budget-only follow-up: "budget 10000"
    if parsed.get("max_price") is not None:
        merged["max_price"] = parsed.get("max_price")
    if new_filters.get("max_price") is not None:
        merged["max_price"] = new_filters.get("max_price")

    return merged


def _has_same_reference(lower: str) -> bool:
    return any(p in lower for p in ("same", "what about", "wahi", "bhi"))


def is_clarification_answer(
    message: str,
    pending: dict,
    *,
    parsed: Optional[dict] = None,
) -> bool:
    """True when a short reply likely answers a pending clarification."""
    if not pending:
        return False
    raw_parsed = parse_query(message)
    parsed = parsed or raw_parsed
    field = pending.get("missing_field")
    if field == "project_type":
        return bool(parse_project_type_option(message))
    if field == "purpose":
        # Full new query (e.g. "excavator in delhi") is not a purpose reply.
        if parsed.get("city") or parsed.get("region"):
            return False
        if parsed.get("category") and len((message or "").split()) > 3:
            return False
        return bool(parse_purpose_option(message))
    if field == "machine_purpose":
        if resolve_purpose_key(message) or parse_purpose_option(message):
            return True
        if parsed.get("city") or parsed.get("max_price") is not None:
            return True
        if detect_requested_category(message):
            return True
        text = (message or "").strip().lower()
        if text in _PURPOSE_OPTIONS or text in PURPOSE_ALIASES:
            return True
        for label in _PURPOSE_OPTIONS:
            if len(label) > 2 and label in text:
                return True
        return False
    if field == "spell_confirm":
        from app.ai.spell_correction import (
            is_spell_confirmation_no,
            is_spell_confirmation_yes,
        )
        return is_spell_confirmation_yes(message) or is_spell_confirmation_no(message)
    if field == "city":
        if _DISRESPECTFUL_RE.search(message or ""):
            return False
        # New explicit category in the same message starts a fresh search.
        if parsed.get("category") or detect_requested_category(message):
            return False
        return bool(parsed.get("city") or parsed.get("max_price") is not None)
    if field == "category":
        return bool(
            parsed.get("category")
            or detect_requested_category(message)
        )
    return bool(parsed.get("category") or parsed.get("city") or parsed.get("max_price"))


def nearby_cities_from_alternatives(alternatives: list, exclude_city: Optional[str]) -> list[str]:
    seen = set()
    out = []
    ex = (exclude_city or "").lower()
    for m in alternatives:
        c = str(m.get("city") or "").strip()
        if not c:
            continue
        key = c.lower()
        if key == ex or key in seen:
            continue
        seen.add(key)
        out.append(c.title())
    return out[:5]


_SIMILAR_CATEGORY_MAP = {
    "backhoe loader": ["excavator", "wheel loader", "compact loader"],
    "jcb": ["backhoe loader", "excavator"],
    "excavator": ["backhoe loader", "crawler drill", "bulldozer"],
    "crane": ["hydra crane", "truck mounted crane"],
    "road roller": ["compactor", "drum roller", "motor grader"],
    "dump truck": ["tipper", "articulated hauler"],
    "crawler drill": ["drill rig", "rock breaker"],
    "bulldozer": ["excavator", "wheel loader"],
    "wheel loader": ["backhoe loader", "compact loader"],
    "motor grader": ["road roller", "compactor"],
    "concrete mixer": ["concrete mixer truck", "concrete pump"],
    "hydra crane": ["crane", "truck mounted crane"],
}


def similar_category_keys(category: str) -> list[str]:
    """Canonical related categories for in-city fallback search."""
    key = (category or "").lower()
    return list(_SIMILAR_CATEGORY_MAP.get(key, []))[:4]


def similar_category_suggestions(category: str) -> list[str]:
    """Lightweight related categories for no-result UX."""
    key = (category or "").lower()
    labels = [category_label(c) for c in _SIMILAR_CATEGORY_MAP.get(key, [])]
    return [l for l in labels if l][:4]


def enrich_no_result_message(
    category: Optional[str],
    city: Optional[str],
    alternatives: list,
    *,
    fallback_reason: Optional[str],
    purpose_based: bool = False,
    requested_category: Optional[str] = None,
    lang: str = "english",
) -> tuple[str, dict]:
    from app.chatbot.language import localized_no_exact_in_city, pick_lang

    label = category_label(category) if category else "machines"
    req_label = category_label(requested_category) if requested_category else label
    city_title = str(city or "").title()
    similar = similar_category_suggestions(category or requested_category or "")

    if not alternatives and city_title and (category or requested_category):
        nearby: list[str] = []
        for m in alternatives:
            c = str(m.get("city") or "").strip()
            if c and c.lower() != (city or "").lower():
                nearby.append(c.title())
        head = localized_no_exact_in_city(
            label=req_label,
            city=city or "",
            similar=similar,
            nearby_cities=nearby,
            lang=lang,
        )
        meta = {
            "nearby_cities": nearby[:5],
            "similar_categories": similar,
            "handover_suggested": True,
            "purpose_based": purpose_based,
        }
        return head, meta

    if purpose_based and city_title:
        head = pick_lang(
            lang,
            english=(
                f"No exact {req_label} in {city_title}. "
                f"Here are purpose-based {label} options:"
            ),
            hindi=(
                f"{city_title} में सटीक {req_label} नहीं मिला। "
                f"Purpose के अनुसार {label} विकल्प:"
            ),
            hinglish=(
                f"No exact {req_label} {city_title} me. "
                f"Purpose ke hisaab se {label} options:"
            ),
        )
    elif city:
        head = pick_lang(
            lang,
            english=f"I couldn't find an exact {label} in {city_title}.",
            hindi=f"{city_title} में सटीक {label} नहीं मिला।",
            hinglish=f"Exact {label} {city_title} me nahi mila.",
        )
    else:
        head = pick_lang(
            lang,
            english=f"I couldn't find an exact {label} for your filters.",
            hindi=f"आपके फ़िल्टर के लिए सटीक {label} नहीं मिला।",
            hinglish=f"Exact {label} aapke filters ke liye nahi mila.",
        )

    parts = [head]
    if fallback_reason and alternatives:
        parts.append(fallback_reason)
    elif similar and not alternatives:
        similar_line = pick_lang(
            lang,
            english=f"Similar categories: {', '.join(similar)}. Would you like to see those?",
            hindi=f"मिलते-जुलते विकल्प: {', '.join(similar)}। क्या आप ye देखना चाहेंगे?",
            hinglish=f"Similar categories: {', '.join(similar)}. Kya aap ye dekhna chahenge?",
        )
        parts.append(similar_line)

    meta = {
        "nearby_cities": nearby_cities_from_alternatives(alternatives, city),
        "similar_categories": similar,
        "handover_suggested": not alternatives,
        "purpose_based": purpose_based,
    }
    return " ".join(parts), meta


def too_many_results_message(count: int, *, lang: str = "english") -> str:
    return localized_too_many_results(count, lang)


def build_response_context(
    *,
    assistant_mode: str,
    used_previous_context: bool = False,
    used_image_context: bool = False,
    pending_clarification: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> dict:
    ctx = {
        "assistant_mode": assistant_mode,
        "used_previous_context": used_previous_context,
        "used_image_context": used_image_context,
        "pending_clarification": pending_clarification,
    }
    if extra:
        ctx.update(extra)
    return ctx
