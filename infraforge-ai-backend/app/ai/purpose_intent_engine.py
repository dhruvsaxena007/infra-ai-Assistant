"""
Purpose-intent engine - map work goals (Hindi/English/Hinglish) to machine categories.

Structural patterns + verb stems + taxonomy aliases - not phrase-specific hacks.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.industry_lexicon import NOUN_WORK_PATTERNS, build_verb_stem_patterns
from app.ai.purpose_taxonomy import primary_category_for_purpose

_NEED_SIGNAL_RE = re.compile(
    r"\b(?:need(?:ed)?|want|required|looking\s+for|chahiye|chaiye|chahiy|mujhe|humko|humhein|dena|dedo)\b"
    r"|(?:ke\s+liye|karne|krne)\b",
    re.I,
)

_NUMERIC_ONLY_RE = re.compile(
    r"^[\d\s.,]+(?:k|lakh|lac|cr|per\s+day)?$",
    re.I,
)

_RECOMMENDATION_EXCLUSION_RE = re.compile(
    r"\b(?:recommend(?:ation|ed)?|suggest(?:ion|ed)?|best\s+machine|which\s+machine|what\s+machine|"
    r"kaunsi\s+machine|konsi\s+machine|suitable\s+machine)\b",
    re.I,
)

_KARNE_KE_LIYE_RE = re.compile(
    r"(?:"
    r"(?:mujhe|maine|humko|hum|i\s+need|i\s+want|need|want|looking\s+for)"
    r".{0,100}?"
    r"(?:machine|machines|equipment|machinery|truck|jcb|saman)"
    r"|"
    r"(?:machine|machines|equipment|truck|jcb).{0,60}?"
    r"(?:ke\s+liye|for|to)"
    r")",
    re.I,
)

_FOR_TO_PURPOSE_RE = re.compile(
    r"\b(?:machine|machines|equipment|truck|jcb)\s+(?:for|to)\s+(\w+(?:\s+\w+){0,4})",
    re.I,
)

_KARNE_KE_LIYE_VERB_RE = re.compile(
    r"\b([\w\s]{2,40}?)\s+(?:karne|krne)\s+ke\s+liye\b",
    re.I,
)

_VERB_STEM_PATTERNS: list[tuple[str, str]] = build_verb_stem_patterns()
_NOUN_WORK_PATTERNS: list[tuple[str, str]] = NOUN_WORK_PATTERNS

# Common English tokens — never fuzzy-match to construction purpose aliases.
_FUZZY_SKIP_WORDS = frozenset({
    "what", "when", "where", "which", "today", "tomorrow", "weather", "there",
    "their", "these", "those", "about", "would", "could", "should", "please",
    "hello", "thanks", "thank", "something", "anything", "everything",
})


def _fuzzy_purpose_from_tokens(text: str) -> Optional[str]:
    try:
        from rapidfuzz import process
        from app.chatbot.assistant_intelligence import PURPOSE_ALIASES

        choices = [
            c for c in dict.fromkeys(PURPOSE_ALIASES.keys())
            if len(c) >= 5
        ]
        words = [
            w for w in re.findall(r"[a-z]{4,}", text.lower())
            if w not in _FUZZY_SKIP_WORDS
        ]
        for word in words:
            match = process.extractOne(word, choices, score_cutoff=84)
            if match:
                return PURPOSE_ALIASES.get(match[0])
        if len(text.split()) <= 6:
            match = process.extractOne(text.lower(), choices, score_cutoff=80)
            if match:
                return PURPOSE_ALIASES.get(match[0])
    except Exception:
        pass
    return None


def _purpose_from_karne_ke_liye(text: str) -> Optional[str]:
    """Extract work purpose from '<verb> karne ke liye' structural pattern."""
    m = _KARNE_KE_LIYE_VERB_RE.search(text or "")
    if not m:
        return None
    phrase = m.group(1).strip().lower()
    if not phrase:
        return None
    for pattern, purpose in _VERB_STEM_PATTERNS:
        if re.search(pattern, phrase, re.I):
            return purpose
    for pattern, purpose in _NOUN_WORK_PATTERNS:
        if re.search(pattern, phrase, re.I):
            return purpose
    return _fuzzy_purpose_from_tokens(phrase)


def detect_purpose_from_message(message: str) -> Optional[str]:
    from app.chatbot.assistant_intelligence import (
        detect_all_work_purposes,
        resolve_purpose_key,
    )

    text = (message or "").strip()
    if not text:
        return None

    lower = text.lower()

    purposes = detect_all_work_purposes(text)
    if purposes:
        return purposes[0]

    resolved = resolve_purpose_key(text)
    if resolved and not str(resolved).startswith("machine:"):
        return resolved

    for pattern, purpose in _VERB_STEM_PATTERNS:
        if re.search(pattern, lower, re.I):
            return purpose

    for pattern, purpose in _NOUN_WORK_PATTERNS:
        if re.search(pattern, lower, re.I):
            return purpose

    m = _FOR_TO_PURPOSE_RE.search(lower)
    if m:
        phrase = m.group(1).strip()
        sub = detect_purpose_from_message(phrase)
        if sub:
            return sub
        fuzzy = _fuzzy_purpose_from_tokens(phrase)
        if fuzzy:
            return fuzzy

    if _KARNE_KE_LIYE_RE.search(lower):
        for pattern, purpose in _VERB_STEM_PATTERNS:
            if re.search(pattern, lower, re.I):
                return purpose
        karne_purpose = _purpose_from_karne_ke_liye(lower)
        if karne_purpose:
            return karne_purpose

    karne_purpose = _purpose_from_karne_ke_liye(lower)
    if karne_purpose:
        return karne_purpose

    return _fuzzy_purpose_from_tokens(lower)


def is_purpose_based_machine_need(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _NUMERIC_ONLY_RE.match(text.strip()):
        return False
    if _RECOMMENDATION_EXCLUSION_RE.search(text):
        return False
    if not _NEED_SIGNAL_RE.search(text):
        return False
    if detect_purpose_from_message(text):
        return True
    if _FOR_TO_PURPOSE_RE.search(text):
        return True
    if re.search(
        r"\b(?:need|want|chahiye|chaiye|required|looking\s+for)\b.{0,80}\b(?:machine|truck|equipment|jcb)\b",
        text,
        re.I,
    ) and re.search(
        r"\b(?:for|to|ke\s+liye|karne|krne)\b",
        text,
        re.I,
    ):
        return True
    return False


def enrich_parsed_with_purpose(parsed: dict[str, Any], message: str) -> dict[str, Any]:
    out = dict(parsed or {})
    text = (message or "").strip()
    if _NUMERIC_ONLY_RE.match(text):
        return out
    purpose = detect_purpose_from_message(message)
    if purpose:
        out["purpose_key"] = purpose
        if not out.get("category"):
            derived = primary_category_for_purpose(purpose)
            if derived:
                out["category"] = derived
                out["category_source"] = "derived_from_purpose"
    return out


def purpose_search_intent(message: str, *, parsed: dict | None = None) -> dict[str, Any]:
    parsed = dict(parsed or {})
    purpose = parsed.get("purpose_key") or detect_purpose_from_message(message)
    category = parsed.get("category")
    if purpose and not category:
        category = primary_category_for_purpose(purpose)
    return {
        "purpose_key": purpose,
        "category": category,
        "should_search": bool(purpose or category),
        "needs_city": bool((purpose or category) and not parsed.get("city")),
    }
