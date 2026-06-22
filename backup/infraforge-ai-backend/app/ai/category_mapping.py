"""
Deterministic, rule-based understanding for marketplace search queries.

This module is the single source of truth for:
  - category synonym mapping (JCB -> Backhoe Loader, etc.)
  - city detection
  - budget / price detection
  - special intent detection (free request, list-all, override, cheaper)

It is intentionally LLM-free so the chatbot behaves correctly even when the
OpenAI / Groq parsers are unavailable. The LLM parsers are still used elsewhere
to *fill gaps*, but category resolution always goes through here so a query
like "JCB 3DX" can never be mis-classified as an excavator.

Canonical category strings MUST match the values stored in MongoDB (lowercase).
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Canonical categories (must match the seed data / DB values exactly).
# ---------------------------------------------------------------------------

CANONICAL_CATEGORIES = [
    # Lifting & access
    "boom lift",
    "scissor lift",
    "single man lift",
    "forklift",
    "walkie stacker",
    "telehandler",
    "knuckleboom loader",
    # Earthmoving
    "excavator",
    "dragline excavator",
    "backhoe loader",
    "bulldozer",
    "motor grader",
    "wheel loader",
    "compact loader",
    "compact track loader",
    "wheel tractor scraper",
    "trencher",
    # Hauling
    "dump truck",
    "articulated hauler",
    "off highway truck",
    # Road / compaction
    "road roller",
    "drum roller",
    "compactor",
    "asphalt paver",
    "cold planer",
    # Cranes
    "crane",
    "hydra crane",
    "truck mounted crane",
    "carry deck crane",
    # Concrete
    "concrete mixer",
    "concrete mixer truck",
    "concrete pump",
    "batching plant",
    # Drilling
    "crawler drill",
    "drill rig",
    # Forestry
    "feller buncher",
    "harvester",
    "skidder",
    "forwarder",
    # Specialized
    "tunnel boring machine",
    "rock breaker",
    "pipe layer",
    "mobile crusher",
    "air compressor",
    "towable light tower",
    "utility vehicle",
]

# ---------------------------------------------------------------------------
# Synonym -> canonical category.
#
# IMPORTANT: "jcb", "3dx", "backhoe" all map to "backhoe loader" and never to
# excavator. Matching is performed longest-synonym-first (see _SYNONYM_LOOKUP)
# so multi-word terms win over single words ("backhoe loader" beats "loader",
# "hydra crane" beats "crane", "concrete mixer" beats "mixer").
# ---------------------------------------------------------------------------

CATEGORY_SYNONYMS = {
    "backhoe loader": [
        "backhoe loader", "loader backhoe", "backhoe",
        "jcb 3dx", "jcb 4dx", "jcb 3 dx", "jcb 4 dx",
        "3dx", "4dx", "jcb",
    ],
    "excavator": [
        "excavator", "earth excavator", "hydraulic excavator",
        "digging machine", "digger", "poclain", "poklain",
    ],
    "hydra crane": [
        "hydra crane", "hydra",
    ],
    "crane": [
        "mobile crane", "truck crane", "tower crane", "crane",
    ],
    "bulldozer": [
        "bulldozer", "dozer", "crawler dozer",
    ],
    "road roller": [
        "road roller", "roller", "steamroller", "vibratory roller",
    ],
    "drum roller": [
        "drum roller", "tandem roller", "double drum roller",
    ],
    "compactor": [
        "compactor", "soil compactor", "vibratory compactor", "plate compactor",
    ],
    "boom lift": [
        "boom lift", "articulating boom", "aerial lift", "man lift", "cherry picker",
    ],
    "scissor lift": [
        "scissor lift", "scissor platform", "electric scissor",
    ],
    "single man lift": [
        "single man lift", "personnel lift", "one man lift",
    ],
    "forklift": [
        "forklift", "fork lift", "lift truck", "counterbalance forklift",
    ],
    "walkie stacker": [
        "walkie stacker", "walkie stacker forklift", "stacker",
    ],
    "telehandler": [
        "telehandler", "telescopic handler", "tele handler",
    ],
    "knuckleboom loader": [
        "knuckleboom loader", "knuckle boom", "hiab", "loader crane",
    ],
    "compact loader": [
        "compact loader", "skid steer", "skid loader",
    ],
    "compact track loader": [
        "compact track loader", "multi terrain loader", "tracked loader", "ctl",
    ],
    "wheel tractor scraper": [
        "wheel tractor scraper", "motor scraper", "scraper",
    ],
    "trencher": [
        "trencher", "chain trencher", "ditch witch",
    ],
    "articulated hauler": [
        "articulated hauler", "adt", "articulated dump truck",
    ],
    "off highway truck": [
        "off highway truck", "haul truck", "mining truck", "rigid dump truck",
    ],
    "asphalt paver": [
        "asphalt paver", "road paver", "paver",
    ],
    "cold planer": [
        "cold planer", "road miller", "milling machine", "wirtgen",
    ],
    "dragline excavator": [
        "dragline excavator", "dragline", "mining excavator",
    ],
    "truck mounted crane": [
        "truck mounted crane", "truck crane", "mobile truck crane",
    ],
    "carry deck crane": [
        "carry deck crane", "carrydeck", "industrial crane",
    ],
    "concrete mixer truck": [
        "concrete mixer truck", "transit mixer truck", "cement mixer truck",
    ],
    "drill rig": [
        "drill rig", "drilling rig", "boring rig", "piling rig",
    ],
    "feller buncher": [
        "feller buncher", "feller-buncher", "tree harvester",
    ],
    "harvester": [
        "harvester", "forestry harvester", "timber harvester",
    ],
    "skidder": [
        "skidder", "log skidder", "timber skidder",
    ],
    "forwarder": [
        "forwarder", "log forwarder", "timber forwarder",
    ],
    "tunnel boring machine": [
        "tunnel boring machine", "tbm", "tunnel borer",
    ],
    "rock breaker": [
        "rock breaker", "hydraulic breaker", "hammer attachment", "breaker",
    ],
    "pipe layer": [
        "pipe layer", "pipelayer", "sideboom",
    ],
    "towable light tower": [
        "towable light tower", "light tower", "lighting tower", "generator light",
    ],
    "utility vehicle": [
        "utility vehicle", "utv", "side by side", "gator",
    ],
    "dump truck": [
        "dump truck", "tipper truck", "dumper", "tipper",
    ],
    "concrete mixer": [
        "concrete mixer", "transit mixer", "cement mixer", "mixer",
    ],
    "batching plant": [
        "batching plant", "concrete batching", "batch plant",
    ],
    "motor grader": [
        "motor grader", "grader",
    ],
    "wheel loader": [
        "front end loader", "wheel loader", "front loader", "loader",
    ],
    "crawler drill": [
        "crawler drill", "drill machine", "drilling machine", "drill",
        "pneumatic drill", "rock drill", "air roc", "roc d-35", "roc d35",
        "d-35", "d35", "lm-100", "lm100", "epiroc air roc",
    ],
    "concrete pump": [
        "concrete pump", "boom pump", "trailer pump", "schwing stetter",
    ],
    "air compressor": [
        "air compressor", "portable compressor", "compressor",
    ],
    "mobile crusher": [
        "mobile crusher", "crusher screen", "crushing plant", "chieftain",
    ],
}

KNOWN_BRANDS = [
    "epiroc", "jcb", "caterpillar", "cat", "tata", "volvo", "komatsu",
    "hyundai", "hitachi", "schwing stetter", "atlas copco", "ammann apollo",
    "terex", "sany", "liebherr", "case", "mahindra", "ace", "kobelco",
]

BRAND_CANONICAL = {
    "epiroc": "EPIROC",
    "jcb": "JCB",
    "cat": "CAT",
    "caterpillar": "Caterpillar",
    "tata": "Tata",
    "volvo": "Volvo",
    "komatsu": "Komatsu",
    "hyundai": "Hyundai",
    "hitachi": "Hitachi",
    "schwing stetter": "Schwing Stetter",
    "atlas copco": "Atlas Copco",
    "ammann apollo": "Ammann Apollo",
    "terex": "Terex",
    "sany": "SANY",
    "liebherr": "Liebherr",
    "case": "CASE",
    "mahindra": "Mahindra",
    "ace": "ACE",
    "kobelco": "Kobelco",
}

# Flat (synonym, canonical) list sorted by synonym length descending so that
# specific multi-word synonyms are always tested before generic single words.
_SYNONYM_LOOKUP = sorted(
    (
        (synonym, canonical)
        for canonical, synonyms in CATEGORY_SYNONYMS.items()
        for synonym in synonyms
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# ---------------------------------------------------------------------------
# Cities present in the dataset (extend as the catalogue grows).
# ---------------------------------------------------------------------------

KNOWN_CITIES = [
    "delhi", "mumbai", "jaipur", "pune", "ahmedabad",
    "gurgaon", "noida", "bangalore", "bengaluru", "hyderabad", "chennai",
    "kolkata", "chandigarh", "lucknow", "kota", "ajmer", "indore", "bhopal",
    "nagpur", "surat", "coimbatore", "faridabad", "ghaziabad", "ranchi",
    "patna", "bhubaneswar", "kochi", "nashik", "vadodara",
]

# Hindi / Hinglish city aliases → canonical lowercase city.
_CITY_ALIASES = {
    "जयपुर": "jaipur", "जैपुर": "jaipur", "jaypur": "jaipur",
    "दिल्ली": "delhi", "dilli": "delhi",
    "मुंबई": "mumbai", "mumabi": "mumbai", "bombay": "mumbai",
    "पुणे": "pune", "puna": "pune",
    "अहमदाबाद": "ahmedabad", "ahmedabad": "ahmedabad",
    "गुड़गांव": "gurgaon", "गुरुग्राम": "gurgaon", "gurugram": "gurgaon",
    "नोएडा": "noida",
    "बैंगलोर": "bangalore", "बेंगलुरु": "bangalore",
    "हैदराबाद": "hyderabad",
    "चेन्नई": "chennai",
    "कोलकाता": "kolkata", "calcutta": "kolkata",
    "चंडीगढ़": "chandigarh",
    "लखनऊ": "lucknow", "lucknow": "lucknow",
    "कोटा": "kota",
    "अजमेर": "ajmer",
    "इंदौर": "indore",
    "भोपाल": "bhopal",
    "नागपुर": "nagpur",
    "सूरत": "surat",
    "कोयंबटूर": "coimbatore",
}

# Regional search — maps region token to city list (lowercase).
REGION_MAP = {
    "north_india": [
        "delhi", "gurgaon", "noida", "jaipur", "chandigarh", "lucknow",
        "faridabad", "ghaziabad",
    ],
    "west_india": [
        "jaipur", "ahmedabad", "surat", "mumbai", "pune", "nashik",
        "vadodara", "kota", "ajmer",
    ],
    "south_india": [
        "bangalore", "chennai", "hyderabad", "kochi", "coimbatore",
    ],
    "east_india": [
        "kolkata", "patna", "ranchi", "bhubaneswar",
    ],
    "central_india": [
        "indore", "bhopal", "nagpur", "raipur",
    ],
}

_REGION_ALIASES = {
    "north india": "north_india",
    "uttar bharat": "north_india",
    "northern india": "north_india",
    "west india": "west_india",
    "paschim bharat": "west_india",
    "western india": "west_india",
    "south india": "south_india",
    "dakshin bharat": "south_india",
    "southern india": "south_india",
    "east india": "east_india",
    "purv bharat": "east_india",
    "eastern india": "east_india",
    "central india": "central_india",
    "madhya bharat": "central_india",
}

# ---------------------------------------------------------------------------
# Intent keyword sets.
# ---------------------------------------------------------------------------

FREE_PHRASES = [
    "free of cost", "free of charge", "zero cost", "no cost",
    "without payment", "without paying", "0 cost", "zero rupee",
    "zero rupees", "muft", "bina paise", "bina kisi kharch",
]

LIST_ALL_PHRASES = [
    "list all", "show all", "all machines", "all the machines",
    "every machine", "list them all", "show me all", "list everything",
    "give me all", "see all", "show every",
]

OVERRIDE_PHRASES = [
    "instead of", "instead", "rather than", "rather", "replace",
    "change to", "switch to", "actually i want", "no i want",
    "not interested in",
]

CHEAPER_PHRASES = [
    "cheaper", "cheap", "lower", "less", "sasta", "low price",
    "more affordable", "affordable", "budget friendly",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _word_in_text(word: str, text: str) -> bool:
    """Whole-word / phrase match using word boundaries."""
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _contains_any(text: str, phrases) -> bool:
    return any(phrase in text for phrase in phrases)


def detect_category(text: str):
    """
    Return the canonical category for a piece of text, or None.

    JCB / 3DX / backhoe always resolve to "backhoe loader".
    """
    if not text:
        return None

    lowered = text.lower()

    for synonym, canonical in _SYNONYM_LOOKUP:
        if _word_in_text(synonym, lowered):
            return canonical

    return None


def canonicalize_category(raw):
    """
    Normalize a (possibly LLM-produced) category string to a canonical value.
    Returns None when it cannot be confidently mapped.
    """
    if not raw:
        return None

    raw_lower = str(raw).strip().lower()

    if raw_lower in CANONICAL_CATEGORIES:
        return raw_lower

    return detect_category(raw_lower)


def detect_city(text: str):
    """Return a canonical city name (lowercase) or None."""
    if not text:
        return None

    lowered = text.lower()

    for alias, canonical in sorted(_CITY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if _word_in_text(alias, lowered) or alias in lowered:
            return canonical

    for city in sorted(KNOWN_CITIES, key=len, reverse=True):
        if _word_in_text(city, lowered):
            return "bangalore" if city == "bengaluru" else city

    return None


# Tokens that look like "in <word>" but are not cities.
_NON_CITY_LOCATION_WORDS = frozenset({
    "rent", "buy", "sale", "sell", "purchase", "the", "a", "an", "my", "your",
    "this", "that", "under", "below", "free", "used", "new", "delhi", "mumbai",
    "jaipur", "pune", "india", "me", "mein", "city",
})

_CITY_ATTEMPT_RE = re.compile(
    r"\bin\s+([a-z]{2,})(?:\s+city)?\b",
    re.I,
)


def has_unknown_city_phrase(text: str) -> bool:
    """
    True when the user named a location that is not a known marketplace city.

    Catches queries like "xyz machine in abc city" where detect_city() is None.
    """
    if not text:
        return False
    if detect_city(text):
        return False
    lowered = text.lower()
    for match in _CITY_ATTEMPT_RE.finditer(lowered):
        token = match.group(1).lower()
        if token in _NON_CITY_LOCATION_WORDS:
            continue
        if token in KNOWN_CITIES or token in _CITY_ALIASES:
            continue
        return True
    if re.search(r"\b[a-z]{2,}\s+city\b", lowered) and not detect_city(text):
        return True
    return False


def detect_region(text: str) -> Optional[str]:
    """Return canonical region key (north_india, west_india, ...) or None."""
    if not text:
        return None
    lowered = text.lower()
    for alias, region_key in sorted(_REGION_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in lowered:
            return region_key
    return None


def region_cities(region_key: str) -> list[str]:
    """Return the city list for a region key."""
    return list(REGION_MAP.get(region_key, []))


# Budget patterns, tried in order. Each capture group 1 is the number, and an
# optional trailing "k" multiplies by 1000.
_PRICE_PATTERNS = [
    r"under\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"below\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"less\s+than\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"max(?:imum)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"budget\s*(?:of)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"within\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"up\s*to\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
    r"upto\s*(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(k)?",
]


def detect_max_price(text: str):
    """Extract a maximum budget from natural language, or None."""
    if not text:
        return None

    lowered = text.lower()

    for pattern in _PRICE_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            number = int(match.group(1).replace(",", ""))
            if match.lastindex and match.group(match.lastindex) == "k":
                number *= 1000
            return number

    # Currency-prefixed bare number: "rs 8000", "₹8000".
    match = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+)", lowered)
    if match:
        return int(match.group(1).replace(",", ""))

    # Number followed by a money/rate word: "8000 rupees", "8000/day".
    match = re.search(r"([\d,]+)\s*(?:rs|rupees|/\s*day|per\s*day)", lowered)
    if match:
        return int(match.group(1).replace(",", ""))

    # Bare number after budget keyword: "budget 10000", "my budget is 1000".
    match = re.search(r"budget\s*(?:is|of)?\s*([\d,]+)", lowered)
    if match:
        return int(match.group(1).replace(",", ""))

    return None


def detect_free_request(text: str) -> bool:
    """True when the user is asking for a free / zero-cost machine."""
    if not text:
        return False
    lowered = text.lower()
    if _word_in_text("free", lowered):
        return True
    return _contains_any(lowered, FREE_PHRASES)


def detect_list_all(text: str) -> bool:
    """True when the user wants to see all/many results, not just the top few."""
    if not text:
        return False
    return _contains_any(text.lower(), LIST_ALL_PHRASES)


def detect_override(text: str) -> bool:
    """True when the user is replacing a previous choice (instead of / rather than)."""
    if not text:
        return False
    return _contains_any(text.lower(), OVERRIDE_PHRASES)


def detect_cheaper(text: str) -> bool:
    """True when the user asks for cheaper / lower-priced options."""
    if not text:
        return False
    return _contains_any(text.lower(), CHEAPER_PHRASES)


def detect_negated_category(text: str):
    """
    Detect a category the user is rejecting, e.g. "instead of excavator",
    "not excavator", "rather than crane". Returns the canonical category to
    drop, or None.
    """
    if not text:
        return None

    lowered = text.lower()

    match = re.search(
        r"(?:instead of|rather than|other than|except|don'?t want|do not want|not|no)\s+"
        r"(?:a\s+|an\s+|the\s+)?([a-z0-9][a-z0-9 ]{1,30})",
        lowered,
    )
    if not match:
        return None

    return detect_category(match.group(1))


def _all_categories_present(text: str) -> list:
    """All canonical categories mentioned in text, de-duplicated, first-seen order."""
    lowered = (text or "").lower()
    found = []
    for synonym, canonical in _SYNONYM_LOOKUP:
        if canonical not in found and _word_in_text(synonym, lowered):
            found.append(canonical)
    return found


def detect_requested_category(text: str):
    """
    The category the user POSITIVELY wants, ignoring any category they are
    rejecting.

    Example: "want a JCB 3DX instead of excavator" mentions both excavator and
    backhoe loader. The excavator is negated ("instead of excavator"), so this
    returns "backhoe loader". This is what prevents the override bug where the
    rejected category would otherwise win.
    """
    if not text:
        return None

    present = _all_categories_present(text)
    if not present:
        return None

    negated = detect_negated_category(text)

    if negated:
        positives = [c for c in present if c != negated]
        return positives[0] if positives else None

    return present[0]


def category_label(category) -> str:
    """Human-friendly label for replies (Backhoe Loader shown as JCB / Backhoe Loader)."""
    if not category:
        return "machines"
    if category == "backhoe loader":
        return "JCB / Backhoe Loader"
    return category.title()


# ---------------------------------------------------------------------------
# Marketplace category name -> canonical category
# (equipmentcategories.category values are UPPERCASE, e.g. "AIR COMPRESSOR")
# ---------------------------------------------------------------------------

_MARKETPLACE_CATEGORY_PATTERNS = [
    ("boom lift", ["boom lift", "aerial lift", "cherry picker"]),
    ("scissor lift", ["scissor lift", "scissor platform"]),
    ("single man lift", ["single man lift", "personnel lift"]),
    ("forklift", ["forklift", "fork lift", "lift truck"]),
    ("walkie stacker", ["walkie stacker", "stacker"]),
    ("telehandler", ["telehandler", "telescopic handler"]),
    ("knuckleboom loader", ["knuckleboom", "knuckle boom", "hiab"]),
    ("dragline excavator", ["dragline"]),
    ("tunnel boring machine", ["tunnel boring", "tbm"]),
    ("rock breaker", ["rock breaker", "hydraulic breaker"]),
    ("pipe layer", ["pipe layer", "pipelayer", "sideboom"]),
    ("towable light tower", ["light tower", "lighting tower"]),
    ("utility vehicle", ["utility vehicle", "utv", "gator"]),
    ("articulated hauler", ["articulated hauler", "adt"]),
    ("off highway truck", ["off highway", "haul truck", "mining truck"]),
    ("asphalt paver", ["asphalt paver", "road paver"]),
    ("cold planer", ["cold planer", "road miller"]),
    ("drum roller", ["drum roller", "tandem roller"]),
    ("compactor", ["compactor", "soil compactor"]),
    ("compact track loader", ["compact track loader", "multi terrain loader"]),
    ("compact loader", ["compact loader", "skid steer"]),
    ("wheel tractor scraper", ["tractor scraper", "motor scraper"]),
    ("trencher", ["trencher", "ditch witch"]),
    ("feller buncher", ["feller buncher"]),
    ("harvester", ["forestry harvester", "harvester"]),
    ("skidder", ["skidder", "log skidder"]),
    ("forwarder", ["forwarder", "log forwarder"]),
    ("carry deck crane", ["carry deck", "carrydeck"]),
    ("concrete mixer truck", ["concrete mixer truck", "transit mixer truck"]),
    ("drill rig", ["drill rig", "drilling rig"]),
    ("truck mounted crane", ["truck mounted crane"]),
    ("crawler drill", ["crawler drill", "roc", "pneumatic drill", "air roc"]),
    ("backhoe loader", ["backhoe", "jcb", "loader backhoe", "3dx", "4dx"]),
    ("excavator", ["excavator", "poclain", "poklain", "hydraulic excavator"]),
    ("hydra crane", ["hydra crane", "hydra"]),
    ("crane", ["mobile crane", "tower crane", "crawler crane", "crane"]),
    ("bulldozer", ["bulldozer", "dozer", "crawler dozer"]),
    ("road roller", ["road roller", "steamroller"]),
    ("dump truck", ["dump truck", "tipper", "dumper", "tipper truck", "signa"]),
    ("concrete mixer", ["concrete mixer", "transit mixer", "cement mixer"]),
    ("concrete pump", ["concrete pump", "boom pump", "trailer pump"]),
    ("motor grader", ["motor grader", "grader"]),
    ("wheel loader", ["wheel loader", "front loader", "front end loader"]),
    ("air compressor", ["air compressor", "compressor"]),
    ("mobile crusher", ["crusher", "screen", "chieftain"]),
]


def marketplace_category_to_canonical(raw_name: str) -> str:
    """
    Map a real marketplace equipment category label to a canonical AI category.

    Falls back to detect_category() and then lowercase raw name when no pattern
    matches — so unmapped categories (e.g. "AIR COMPRESSOR") still work as
    their own category string.
    """
    if not raw_name:
        return ""

    lowered = str(raw_name).strip().lower()

    for canonical, patterns in _MARKETPLACE_CATEGORY_PATTERNS:
        for pattern in patterns:
            if pattern in lowered:
                return canonical

    detected = detect_category(lowered)
    if detected:
        return detected

    if lowered in CANONICAL_CATEGORIES:
        return lowered

    return lowered


def detect_brand(text: str):
    """Detect equipment brand mentioned in query text."""
    if not text:
        return None
    lowered = text.lower()
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if _word_in_text(brand, lowered):
            return BRAND_CANONICAL.get(brand, brand.title())
    return None


def detect_model(text: str):
    """Detect model token patterns like AIR ROC D-35, 3DX, 120K2."""
    if not text:
        return None
    patterns = [
        r"\bepiroc\s+air\s*roc\s*d[- ]?35\b",
        r"\bair\s*roc\s*d[- ]?35\b",
        r"\bair\s*roc\b",
        r"\blm[- ]?100\b",
        r"\b3dx\b",
        r"\b4dx\b",
        r"\b120k2\b",
        r"\bxa[- ]?157\b",
        r"\bscs800a\b",
        r"\bbp\s*350\b",
        r"\b432\s*zx\b",
    ]
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0).upper().replace("  ", " ")
    return None


def detect_condition(text: str):
    if not text:
        return None
    lowered = text.lower()
    if _word_in_text("used", lowered):
        return "used"
    if _word_in_text("new", lowered):
        return "new"
    return None


def detect_pincode(text: str):
    if not text:
        return None
    match = re.search(r"\b(\d{6})\b", text)
    return match.group(1) if match else None


_LISTING_TYPE_HOW_TO_RE = re.compile(
    r"\b(how\s+(?:to|do\s+i|can\s+i)|kaise|kese|process|procedure|steps?)\b",
    re.I,
)


def detect_listing_type(text: str):
    if not text:
        return None
    lowered = text.lower()
    # "how to rent it" is a guidance question — not a rent-preference filter.
    if _LISTING_TYPE_HOW_TO_RE.search(lowered):
        return None
    rent_tokens = (
        "rent", "rental", "hire", "kiraye", "kiraya", "kiraye pe",
        "on rent", "lease", "leasing",
    )
    buy_tokens = (
        "sell", "sale", "buy", "purchase", "kharidna", "khareedna",
        "kharid", "khareed", "for sale", "khareedna", "khreedna",
    )
    if any(tok in lowered for tok in rent_tokens):
        return "rent"
    if any(tok in lowered for tok in buy_tokens):
        return "sell"
    return None


def detect_rent_type(text: str):
    if not text:
        return None
    lowered = text.lower()
    if "hourly" in lowered or "per hour" in lowered:
        return "hourly"
    if "daily" in lowered or "per day" in lowered:
        return "daily"
    return None


def category_matches(machine_category: str, search_category: str) -> bool:
    """True when normalized machine category matches a search category token."""
    if not search_category:
        return False
    mc = str(machine_category or "").lower().strip()
    sc = str(search_category or "").lower().strip()
    if not mc or not sc:
        return False
    return sc in mc or mc in sc or sc == mc
