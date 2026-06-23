# -*- coding: utf-8 -*-
"""
Centralized industry vocabulary for Indian construction / earthmoving domain.

Single source of truth for purpose aliases, category terms, construction nouns,
material hints, Hindi verb stems, work-phrase patterns, and typo corrections.

Mechanism-first: regex families are built from lexicon groups - not per-query hacks.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

# ---------------------------------------------------------------------------
# Canonical purpose keys
# ---------------------------------------------------------------------------

CANONICAL_PURPOSES: tuple[str, ...] = (
    "digging",
    "demolition",
    "compaction",
    "leveling",
    "transport",
    "lifting",
    "loading",
    "drilling",
    "concrete",
    "mining",
)

# ---------------------------------------------------------------------------
# PURPOSE_TERMS: spoken / written alias -> canonical purpose key
# ---------------------------------------------------------------------------

PURPOSE_TERMS: dict[str, str] = {
    # digging / earthwork
    "digging": "digging",
    "excavation": "digging",
    "excavate": "digging",
    "excavating": "digging",
    "excavator work": "digging",
    "earthwork": "digging",
    "earth moving": "digging",
    "earthmoving": "digging",
    "trenching": "digging",
    "trench": "digging",
    "khudai": "digging",
    "khodai": "digging",
    "khodna": "digging",
    "khodne": "digging",
    "khodni": "digging",
    "khodana": "digging",
    "gaddha": "digging",
    "gaddhe": "digging",
    "khadda": "digging",
    "foundation digging": "digging",
    "foundation excavation": "digging",
    "site excavation": "digging",
    "basement excavation": "digging",
    "pipeline trench": "digging",
    "cable trench": "digging",
    "drainage trench": "digging",
    "nali khodna": "digging",
    "mitti khodna": "digging",
    "road khodna": "digging",
    "road digging": "digging",
    # demolition
    "demolition": "demolition",
    "demolish": "demolition",
    "demolishing": "demolition",
    "wrecking": "demolition",
    "breakdown": "demolition",
    "break down": "demolition",
    "dismantling": "demolition",
    "dismantle": "demolition",
    "todna": "demolition",
    "todne": "demolition",
    "todni": "demolition",
    "todana": "demolition",
    "girana": "demolition",
    "girane": "demolition",
    "girana ka kaam": "demolition",
    "building demolition": "demolition",
    "structure demolition": "demolition",
    "imarat todna": "demolition",
    "makaan todna": "demolition",
    "building todna": "demolition",
    # compaction
    "compaction": "compaction",
    "compact": "compaction",
    "compacting": "compaction",
    "soil compaction": "compaction",
    "road compaction": "compaction",
    "dabana": "compaction",
    "dabane": "compaction",
    "dabai": "compaction",
    "kootna": "compaction",
    "flatten": "compaction",
    "flattening": "compaction",
    "road work": "compaction",
    "roadwork": "compaction",
    "paving": "compaction",
    "bitumen laying": "compaction",
    "asphalt work": "compaction",
    "wbm work": "compaction",
    "sub base compaction": "compaction",
    # leveling / grading
    "leveling": "leveling",
    "levelling": "leveling",
    "level": "leveling",
    "grading": "leveling",
    "grade": "leveling",
    "grader work": "leveling",
    "road leveling": "leveling",
    "road levelling": "leveling",
    "road grading": "leveling",
    "seedhi": "leveling",
    "sidha": "leveling",
    "sidi": "leveling",
    "seedha": "leveling",
    "sidhi karna": "leveling",
    "seedhi karna": "leveling",
    "surface leveling": "leveling",
    "finish grading": "leveling",
    # transport / hauling
    "transport": "transport",
    "transporting": "transport",
    "hauling": "transport",
    "haulage": "transport",
    "haul": "transport",
    "carry": "transport",
    "carrying": "transport",
    "shifting": "transport",
    "material shifting": "transport",
    "material transport": "transport",
    "saman le jana": "transport",
    "samaan le jana": "transport",
    "mal le jana": "transport",
    "pathar": "transport",
    "patthar": "transport",
    "patther": "transport",
    "boulder hauling": "transport",
    "rock hauling": "transport",
    "aggregate transport": "transport",
    "malwa transport": "transport",
    "debris removal": "transport",
    "muck hauling": "transport",
    "overburden removal": "transport",
    # lifting
    "lifting": "lifting",
    "lift": "lifting",
    "lift work": "lifting",
    "height work": "lifting",
    "height": "lifting",
    "erection": "lifting",
    "steel erection": "lifting",
    "structural erection": "lifting",
    "crane work": "lifting",
    "upar uthana": "lifting",
    "upar uthane": "lifting",
    "uthana": "lifting",
    "uthane": "lifting",
    "chadana": "lifting",
    "material lifting": "lifting",
    "prefab lifting": "lifting",
    "beam lifting": "lifting",
    "column lifting": "lifting",
    # loading
    "loading": "loading",
    "unload": "loading",
    "unloading": "loading",
    "material handling": "loading",
    "bharne": "loading",
    "bharana": "loading",
    "bharai": "loading",
    "stockpiling": "loading",
    "aggregate loading": "loading",
    # drilling
    "drilling": "drilling",
    "drill": "drilling",
    "boring": "drilling",
    "blast hole": "drilling",
    "blast hole drilling": "drilling",
    "foundation boring": "drilling",
    "pile boring": "drilling",
    "borewell": "drilling",
    "bore well": "drilling",
    "boring work": "drilling",
    # concrete
    "concrete": "concrete",
    "cement": "concrete",
    "rcc": "concrete",
    "rmc": "concrete",
    "ready mix": "concrete",
    "ready mix concrete": "concrete",
    "concrete pouring": "concrete",
    "concrete placement": "concrete",
    "slab casting": "concrete",
    "foundation concreting": "concrete",
    "column concreting": "concrete",
    "beam concreting": "concrete",
    "concreting": "concrete",
    # mining / quarry
    "mining": "mining",
    "quarry": "mining",
    "quarrying": "mining",
    "stone quarry": "mining",
    "mineral extraction": "mining",
    "overburden": "mining",
    "khan": "mining",
    "khani": "mining",
    "pathar khan": "mining",
    "stone mining": "mining",
    "blasting": "mining",
}

# ---------------------------------------------------------------------------
# CATEGORY_TERMS: alias -> canonical machine category (DB lowercase)
# ---------------------------------------------------------------------------

CATEGORY_TERMS: dict[str, str] = {
    "excavator": "excavator",
    "excavators": "excavator",
    "poclain": "excavator",
    "poklain": "excavator",
    "poclain machine": "excavator",
    "hydraulic excavator": "excavator",
    "crawler excavator": "excavator",
    "digger": "excavator",
    "digging machine": "excavator",
    "khudai machine": "excavator",
    "khodai machine": "excavator",
    "backhoe": "backhoe loader",
    "backhoe loader": "backhoe loader",
    "loader backhoe": "backhoe loader",
    "jcb": "backhoe loader",
    "jcb machine": "backhoe loader",
    "crane": "crane",
    "mobile crane": "crane",
    "tower crane": "crane",
    "truck crane": "crane",
    "hydra": "hydra crane",
    "hydra crane": "hydra crane",
    "hydra crain": "hydra crane",
    "pick and carry": "hydra crane",
    "truck mounted crane": "truck mounted crane",
    "roller": "road roller",
    "road roller": "road roller",
    "roadroller": "road roller",
    "vibratory roller": "road roller",
    "tandem roller": "drum roller",
    "drum roller": "drum roller",
    "compactor": "compactor",
    "soil compactor": "compactor",
    "plate compactor": "compactor",
    "sadak roller": "road roller",
    "dump truck": "dump truck",
    "dumper": "dump truck",
    "tipper": "dump truck",
    "tata tipper": "dump truck",
    "haul truck": "dump truck",
    "10 wheeler": "dump truck",
    "12 wheeler": "dump truck",
    "wheel loader": "wheel loader",
    "loader": "wheel loader",
    "front loader": "wheel loader",
    "shovel loader": "wheel loader",
    "grader": "motor grader",
    "motor grader": "motor grader",
    "road grader": "motor grader",
    "bulldozer": "bulldozer",
    "dozer": "bulldozer",
    "crawler dozer": "bulldozer",
    "concrete mixer": "concrete mixer",
    "mixer": "concrete mixer",
    "rmc truck": "concrete mixer truck",
    "transit mixer": "concrete mixer truck",
    "concrete pump": "concrete pump",
    "boom pump": "concrete pump",
    "crawler drill": "crawler drill",
    "drill rig": "drill rig",
    "blast hole drill": "crawler drill",
    "rock drill": "crawler drill",
    "forklift": "forklift",
    "fork lift": "forklift",
    "boom lift": "boom lift",
    "scissor lift": "scissor lift",
    "man lift": "boom lift",
    "mobile crusher": "mobile crusher",
    "crusher": "mobile crusher",
    "rock breaker": "rock breaker",
    "breaker": "rock breaker",
    "trencher": "trencher",
    "paver": "asphalt paver",
    "asphalt paver": "asphalt paver",
}

# ---------------------------------------------------------------------------
# CONSTRUCTION_NOUNS: site / structure vocabulary (context, not purpose)
# ---------------------------------------------------------------------------

CONSTRUCTION_NOUNS: frozenset[str] = frozenset({
    "building", "structure", "site", "construction site", "project site",
    "foundation", "footing", "basement", "slab", "column", "beam", "pillar",
    "roof", "floor", "wall", "retaining wall", "bridge", "flyover", "viaduct",
    "culvert", "tunnel", "dam", "canal", "pipeline", "sewer", "drainage",
    "road", "highway", "expressway", "nh", "national highway", "state highway",
    "pavement", "footpath", "shoulder", "embankment", "subgrade", "sub base",
    "parking", "warehouse", "factory", "plant", "industrial shed",
    "high rise", "multistorey", "tower", "commercial complex", "mall",
    "metro", "railway", "airport", "port", "jetty",
    "imarat", "makaan", "ghar", "building site", "nirman",
    "nirmaan", "nirman sthal", "construction", "site ka kaam",
    "pul", "puliya", "setu", "sarak", "sadak", "rasta", "marg",
    "nh road", "highway ka kaam", "flyover ka kaam",
    "neev", "buniyad", "foundation ka kaam", "chabutra", "plinth",
    "chhat", "chhajja", "deewar", "diwar", "khamba", "column ka kaam",
    "nali", "gutter", "sewer line", "water line",
    "khet", "zameen", "plot", "layout", "township", "colony",
    "quarry site", "mine site", "khan", "stone quarry",
    "rcc structure", "steel structure", "prefab",
})

# ---------------------------------------------------------------------------
# MATERIAL_TERMS: material -> purpose hint (None = context only)
# ---------------------------------------------------------------------------

MATERIAL_TERMS: dict[str, Optional[str]] = {
    "mitti": "digging",
    "mitta": "digging",
    "soil": "digging",
    "earth": "digging",
    "clay": "digging",
    "sand": "digging",
    "balu": "digging",
    "rora": "digging",
    "murrum": "compaction",
    "kankar": "compaction",
    "pathar": "transport",
    "patthar": "transport",
    "patther": "transport",
    "rock": "transport",
    "boulder": "transport",
    "stone": "transport",
    "gitti": "transport",
    "aggregate": "transport",
    "malwa": "transport",
    "rubble": "transport",
    "debris": "transport",
    "muck": "transport",
    "overburden": "mining",
    "cement": "concrete",
    "concrete": "concrete",
    "rcc": "concrete",
    "rmc": "concrete",
    "mortar": "concrete",
    "bitumen": "compaction",
    "asphalt": "compaction",
    "tar": "compaction",
    "wbm": "compaction",
    "gsb": "compaction",
    "steel": "lifting",
    "rebar": "lifting",
    "tmt": "lifting",
    "iron": "lifting",
    "structural steel": "lifting",
    "beam": "lifting",
    "girder": "lifting",
    "saman": None,
    "samaan": None,
    "mal": None,
    "material": None,
}

# ---------------------------------------------------------------------------
# VERB_STEMS_HINDI: romanized verb stem -> purpose
# ---------------------------------------------------------------------------

VERB_STEMS_HINDI: dict[str, str] = {
    "khod": "digging",
    "khodna": "digging",
    "khodne": "digging",
    "khodni": "digging",
    "khodana": "digging",
    "khudai": "digging",
    "khodai": "digging",
    "gaddha": "digging",
    "khadda": "digging",
    "tod": "demolition",
    "todna": "demolition",
    "todne": "demolition",
    "todni": "demolition",
    "todana": "demolition",
    "gira": "demolition",
    "girana": "demolition",
    "girane": "demolition",
    "udana": "demolition",
    "dabana": "compaction",
    "dabane": "compaction",
    "dabai": "compaction",
    "kootna": "compaction",
    "kootne": "compaction",
    "daba": "compaction",
    "seedha": "leveling",
    "seedhi": "leveling",
    "sidha": "leveling",
    "sidi": "leveling",
    "lejana": "transport",
    "le jana": "transport",
    "shift": "transport",
    "shift karna": "transport",
    "uthana": "lifting",
    "uthane": "lifting",
    "upar": "lifting",
    "chadana": "lifting",
    "bharana": "loading",
    "bharne": "loading",
    "bharai": "loading",
    "dalna": "concrete",
    "dalne": "concrete",
}

ENGLISH_VERB_STEMS: dict[str, str] = {
    "excavate": "digging",
    "excavating": "digging",
    "dig": "digging",
    "digging": "digging",
    "trench": "digging",
    "demolish": "demolition",
    "demolishing": "demolition",
    "wreck": "demolition",
    "compact": "compaction",
    "compacting": "compaction",
    "flatten": "compaction",
    "grade": "leveling",
    "grading": "leveling",
    "level": "leveling",
    "leveling": "leveling",
    "levelling": "leveling",
    "haul": "transport",
    "hauling": "transport",
    "carry": "transport",
    "carrying": "transport",
    "transport": "transport",
    "transporting": "transport",
    "lift": "lifting",
    "lifting": "lifting",
    "erect": "lifting",
    "erection": "lifting",
    "load": "loading",
    "loading": "loading",
    "unload": "loading",
    "unloading": "loading",
    "drill": "drilling",
    "drilling": "drilling",
    "bore": "drilling",
    "boring": "drilling",
    "pour": "concrete",
    "pouring": "concrete",
    "mine": "mining",
    "mining": "mining",
    "quarry": "mining",
}

# ---------------------------------------------------------------------------
# COMMON_TYPOS: industry-specific typo -> correction
# ---------------------------------------------------------------------------

COMMON_TYPOS: dict[str, str] = {
    "exavator": "excavator",
    "excvator": "excavator",
    "excavtor": "excavator",
    "excavater": "excavator",
    "excavetor": "excavator",
    "excevator": "excavator",
    "excavtion": "excavation",
    "excavatoin": "excavation",
    "rolar": "roller",
    "rolle": "roller",
    "truk": "truck",
    "crne": "crane",
    "crain": "crane",
    "crawlar dril": "crawler drill",
    "crawler dril": "crawler drill",
    "backhoe loadr": "backhoe loader",
    "tippr": "tipper",
    "compctor": "compactor",
    "buldozer": "bulldozer",
    "bulldozr": "bulldozer",
    "concret": "concrete",
    "cemnt": "cement",
    "chaiye": "chahiye",
    "chahiy": "chahiye",
    "machne": "machine",
    "mashine": "machine",
    "masheen": "machine",
    "foundaton": "foundation",
    "foudation": "foundation",
    "demoliton": "demolition",
    "demolision": "demolition",
    "compactiong": "compaction",
    "excavting": "excavating",
    "dril": "drill",
    "driling": "drilling",
    "borring": "boring",
    "bitumun": "bitumen",
    "asphault": "asphalt",
}

COMMON_PHRASE_TYPOS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhydra\s+crne\b", re.I), "hydra crane"),
    (re.compile(r"\bhydra\s+crain\b", re.I), "hydra crane"),
    (re.compile(r"\broad\s+rolar\b", re.I), "road roller"),
    (re.compile(r"\bdump\s+truk\b", re.I), "dump truck"),
    (re.compile(r"\bcrawlar\s+dril\b", re.I), "crawler drill"),
    (re.compile(r"\bcrawler\s+dril\b", re.I), "crawler drill"),
    (re.compile(r"\bbackhoe\s+loadr\b", re.I), "backhoe loader"),
    (re.compile(r"\bexavator\b", re.I), "excavator"),
    (re.compile(r"\bexcavtion\b", re.I), "excavation"),
    (re.compile(r"\bmachne\b", re.I), "machine"),
    (re.compile(r"\bimarat\s+todne\b", re.I), "imarat todne"),
]

NOUN_WORK_PATTERNS: list[tuple[str, str]] = [
    (r"\bexcavat(?:ion|ing|or)?\b", "digging"),
    (r"\bearth(?:mov|work)\b", "digging"),
    (r"\bdemolition\b", "demolition"),
    (r"\bcompaction\b", "compaction"),
    (r"\bgrading\b", "leveling"),
    (r"\bhauling\b", "transport"),
    (r"\blifting\b", "lifting"),
    (r"\bquarry(?:ing)?\b", "mining"),
    (r"\bmining\b", "mining"),
    (r"\bconcreting\b", "concrete"),
]


def _group_stems_by_purpose(stems: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for stem, purpose in stems.items():
        grouped[purpose].append(re.escape(stem))
    return grouped


def build_verb_stem_patterns() -> list[tuple[str, str]]:
    """Regex patterns from Hindi + English verb stem families."""
    all_stems = {**VERB_STEMS_HINDI, **ENGLISH_VERB_STEMS}
    grouped = _group_stems_by_purpose(all_stems)
    patterns: list[tuple[str, str]] = []

    for purpose, stems in grouped.items():
        if not stems:
            continue
        alt = "|".join(sorted(set(stems), key=len, reverse=True))
        patterns.append((rf"\b(?:{alt})\b", purpose))

    patterns.extend([
        (r"\b(?:demolish(?:ing)?|demolition|wrecking|breakdown)\b", "demolition"),
        (r"\b(?:building|imarat|makaan|structure)\s+.{0,20}(?:tod|gira|demolish)\w*\b", "demolition"),
        (r"\b(?:khod(?:na|ne|ni)?|khudai|khodai|trench(?:ing)?|excavat(?:e|ion|ing)?|earthwork|dig(?:ging)?)\b", "digging"),
        (r"\broad\s+(?:khod|dig)\w*\b", "digging"),
        (r"\b(?:seedhi|sidha|sidi|straighten(?:ing)?|level(?:l)?ing|levelling|grading|grade|grader)\b", "leveling"),
        (r"\broad\s+(?:seedhi|sidha|level|grade)\w*\b", "leveling"),
        (r"\b(?:dabana|dabane|compact(?:ion|ing)?|compactor|flatten)\b", "compaction"),
        (r"\b(?:patthar|pathar|patther|rock|boulder).{0,25}(?:utha\w*|le\s*jana|carry|haul|shift)\b", "transport"),
        (r"\b(?:utha\w*|carry|haul|le\s*jana).{0,25}(?:patthar|pathar|patther|rock|boulder|mitti|material)\b", "transport"),
        (r"\b(?:le\s*jana|carry(?:ing)?|haul(?:ing)?|transport(?:ing)?|shift(?:ing)?|deliver)\b", "transport"),
        (r"\b(?:upar\s+utha\w*|lift(?:ing)?|erection|crane\s+work)\b", "lifting"),
        (r"\b(?:uthana|uthane)\b(?![^\s]{0,30}(?:patthar|pathar|patther|rock|boulder|mitti|material|truck|tipper))", "lifting"),
        (r"\b(?:load(?:ing)?|unload(?:ing)?|material\s+handling|bharne|bharana)\b", "loading"),
        (r"\b(?:drill(?:ing)?|boring|bor(?:ing)?|blast\s+hole)\b", "drilling"),
        (r"\b(?:concrete|cement|rcc|rmc|mixer|concreting)\b", "concrete"),
        (r"\b(?:mining|quarry(?:ing)?|overburden|stone\s+quarry)\b", "mining"),
    ])
    return patterns


def _materials_for_purpose(purpose: str) -> list[str]:
    return [m for m, hint in MATERIAL_TERMS.items() if hint == purpose and m]


def build_work_phrase_patterns() -> list[tuple[str, str]]:
    """Regex patterns derived from material + construction noun families."""
    patterns: list[tuple[str, str]] = []

    transport_mats = _materials_for_purpose("transport")
    if transport_mats:
        mats = "|".join(re.escape(m) for m in transport_mats)
        patterns.extend([
            (rf"\b(?:{mats}).{{0,25}}(?:utha\w*|le\s*jana|carry|haul|shift)\b", "transport"),
            (rf"\b(?:utha\w*|carry|haul).{{0,25}}(?:{mats})\b", "transport"),
        ])

    digging_mats = [m for m in _materials_for_purpose("digging") if len(m) >= 4]
    if digging_mats:
        mats = "|".join(re.escape(m) for m in digging_mats[:6])
        patterns.append(
            (rf"\b(?:{mats})\s+.{0,15}(?:khod|dig|excavat)\w*\b", "digging"),
        )

    demo_nouns = "|".join(re.escape(n) for n in ("building", "imarat", "makaan", "structure", "bridge", "flyover"))
    patterns.extend([
        (rf"\b(?:{demo_nouns})\s+.{0,20}(?:tod|gira|demolish|wreck|break)\w*\b", "demolition"),
        (r"\b(?:boulder|rock|stone|patthar|pathar).{0,25}(?:haul(?:ing)?|carry(?:ing)?|transport)\b", "transport"),
        (r"\b(?:haul(?:ing)?|carry(?:ing)?|transport(?:ing)?).{0,40}(?:boulder|rock|stone|quarry|patthar|pathar)\b", "transport"),
        (r"\b(?:mining|quarrying|stone\s+quarry|pathar\s+khan|overburden)\b", "mining"),
        (r"\bquarry\b(?![^\s]{0,40}(?:haul|carry|transport))", "mining"),
        (r"\b(?:mitti\s+khod|road\s+khod|khodne|khodna|khodni|trench(?:ing)?)\b", "digging"),
        (r"\b(?:road\s+dig(?:ging)?|digging\s+road|for\s+digging)\b", "digging"),
        (r"\b(?:digging|excavation|excavate|khudai|earthwork)\b", "digging"),
        (r"\bexcavator\b(?![^\s]{0,40}(?:mining|quarry|khan))", "digging"),
        (r"\b(?:road\s+seedhi|seedhi\s+karne|sidha\s+karne|road\s+sidha|level(?:ing|ling)\s+(?:the\s+)?road|road\s+level(?:ing|ling)|grading)\b", "leveling"),
        (r"\b(?:dabana|dabane|compact(?:ion|ing)?|compactor|compacting)\b", "compaction"),
        (r"\b(?:roller|road\s+roller)\b", "compaction"),
        (r"\bconcrete\b", "concrete"),
        (r"\b(?:upar\s+utha\w*|crane\s+work|lifting|erection|height\s+work)\b", "lifting"),
        (r"\b(?:drilling|boring|blast\s+hole)\b", "drilling"),
        (r"\b(?:saman\s+le\s+jana|material\s+shift(?:ing)?|transport|hauling|haulage|carry(?:ing)?\s+rocks?)\b", "transport"),
        (r"\b(?:loading|material\s+handling|unload(?:ing)?)\b", "loading"),
        (r"\b(?:road\s+work|highway|expressway|nh\s*\d*|paving|bitumen|asphalt)\b", "compaction"),
        (r"\b(?:foundation|neev|buniyad|slab|column|beam)\s+.{0,20}(?:concret|rcc|cement|dal)\w*\b", "concrete"),
        (r"\b(?:borewell|bore\s+well|pile\s+boring)\b", "drilling"),
    ])
    return patterns


def build_purpose_signal_patterns() -> list[tuple[str, str]]:
    """Ordered purpose signal patterns for multi-purpose detection."""
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    for pattern, purpose in build_work_phrase_patterns():
        key = (pattern, purpose)
        if key not in seen:
            seen.add(key)
            ordered.append((pattern, purpose))
    return ordered


def build_purpose_aliases() -> dict[str, str]:
    """Flat alias map for fuzzy / substring purpose resolution."""
    return dict(PURPOSE_TERMS)


def merge_category_synonyms(
    existing: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Extend category synonym lists with lexicon CATEGORY_TERMS."""
    merged = {k: list(v) for k, v in existing.items()}
    for alias, canon in CATEGORY_TERMS.items():
        if canon not in merged:
            continue
        low_alias = alias.lower()
        existing_low = {s.lower() for s in merged[canon]}
        if low_alias not in existing_low:
            merged[canon].append(alias)
    return merged


def lexicon_stats() -> dict[str, int]:
    """Return term counts per section (for diagnostics / tests)."""
    return {
        "purpose_terms": len(PURPOSE_TERMS),
        "category_terms": len(CATEGORY_TERMS),
        "construction_nouns": len(CONSTRUCTION_NOUNS),
        "material_terms": len(MATERIAL_TERMS),
        "verb_stems_hindi": len(VERB_STEMS_HINDI),
        "english_verb_stems": len(ENGLISH_VERB_STEMS),
        "common_typos": len(COMMON_TYPOS),
        "common_phrase_typos": len(COMMON_PHRASE_TYPOS),
        "noun_work_patterns": len(NOUN_WORK_PATTERNS),
        "work_phrase_patterns": len(build_work_phrase_patterns()),
        "verb_stem_patterns": len(build_verb_stem_patterns()),
    }
