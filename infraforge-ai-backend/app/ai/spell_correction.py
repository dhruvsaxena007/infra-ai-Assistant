"""
Fuzzy spelling tolerance for marketplace search queries.

Uses:
  1. Synonym / typo dictionary (fast, exact)
  2. rapidfuzz fuzzy matching (strict — never blocks conversation)
  3. Groq fallback only when local match is empty AND query has marketplace signal

Score rules:
  >= 88  auto-correct silently
  < 88   do not guess — continue with original text (clarification/search as normal)

Never asks confirmation — avoids dead-end loops.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from rapidfuzz import fuzz, process

from app.ai.category_mapping import (
    CANONICAL_CATEGORIES,
    CATEGORY_SYNONYMS,
    KNOWN_BRANDS,
    KNOWN_CITIES,
    _CITY_ALIASES,
    detect_brand,
    detect_city,
    detect_listing_type,
    detect_model,
    detect_requested_category,
)
from app.core.config import settings

AUTO_CORRECT_THRESHOLD = 88

# Direct typo → canonical replacement (dictionary first).
SPELLING_SYNONYMS: dict[str, str] = {
    # Categories
    "excvator": "excavator",
    "excavtor": "excavator",
    "exkavator": "excavator",
    "excavater": "excavator",
    "crain": "crane",
    "hydra crne": "hydra crane",
    "hydra crain": "hydra crane",
    "hydra crnae": "hydra crane",
    "road rolar": "road roller",
    "road rolle": "road roller",
    "road rolr": "road roller",
    "dump truk": "dump truck",
    "dump trcuk": "dump truck",
    "crawlar dril": "crawler drill",
    "crawler dril": "crawler drill",
    "cralwer drill": "crawler drill",
    "backhoe loadr": "backhoe loader",
    "jcb chahiy": "jcb",
    "jcb chaiye": "jcb",
    # Cities
    "jaipir": "jaipur",
    "jaypur": "jaipur",
    "jaipurrr": "jaipur",
    "delih": "delhi",
    "dehli": "delhi",
    "delhii": "delhi",
    "mumabi": "mumbai",
    "puna": "pune",
    "nodia": "noida",
    "banglore": "bangalore",
    "bengluru": "bengaluru",
    "hydrabad": "hyderabad",
    "hyderbad": "hyderabad",
    "dilli": "delhi",
    "gurugram": "gurgaon",
    "gurgaon": "gurgaon",
    # Intent / listing
    "rnet": "rent",
    "rentl": "rent",
    "hir": "hire",
    "buuy": "buy",
    "bugdet": "budget",
    "budjet": "budget",
    # Hindi helpers (normalize only)
    "chahiy": "chahiye",
    "chaiye": "chahiye",
    # Brands (speech / keyboard)
    "hundai": "hyundai",
    "hyundia": "hyundai",
    "genrally": "generally",
    "wese": "waise",
}

_STOP_WORDS = frozenset({
    "in", "on", "at", "the", "a", "an", "for", "of", "to", "and", "or",
    "me", "ke", "liye", "ka", "ki", "ko", "se", "par", "pe", "hai", "hain",
    "chahiye", "chaiye", "chahiy", "under", "below", "with", "from", "is",
    "are", "best", "show", "need", "want", "same", "what", "about", "it",
    "no", "not", "yes", "ok", "okay", "please", "batao", "bataiye", "do",
    "kar", "karo", "sakta", "sakti", "hoon", "ho", "main", "mai", "mera",
})

# Common English/Hinglish — never fuzzy-match to brands/categories.
_NEVER_FUZZY = frozenset({
    "there", "here", "where", "when", "this", "that", "those", "these",
    "hello", "hey", "hola", "thanks", "thank", "sorry", "help", "again",
    "still", "just", "only", "also", "very", "much", "good", "fine",
    "namaste", "namaskar", "kaise", "kya", "haal", "bolo", "batao",
})

_SHORT_BRANDS = frozenset(b for b in KNOWN_BRANDS if len(b) <= 4)

_GREETING_LIKE_RE = re.compile(
    r"^(?:"
    r"(?:h+i+|he+l+o+|hey+|hola|namaste|namaskar|good\s*(?:morning|afternoon|evening|night))"
    r"(?:\s+there)?"
    r"|(?:hi|hello|hey)\s+there"
    r"|kaise\s*ho|kya\s*haal|how\s*are\s*you|what'?s\s*up|sup"
    r")[\s!.?,]*$",
    re.I,
)

_YES_RE = re.compile(
    r"^(yes|y|yeah|yep|haan|ha|han|ji|ok|okay|correct|right|theek|thik)\b",
    re.I,
)
_NO_RE = re.compile(
    r"^(no|n|nope|nah|nahi|na|galat|wrong)\b",
    re.I,
)

_MULTI_WORD_PHRASES: list[tuple[str, str, str]] = []
for canonical, synonyms in CATEGORY_SYNONYMS.items():
    if " " in canonical:
        _MULTI_WORD_PHRASES.append((canonical, canonical, "category"))
    for syn in synonyms:
        if " " in syn:
            _MULTI_WORD_PHRASES.append((syn, canonical, "category"))
_MULTI_WORD_PHRASES.sort(key=lambda x: len(x[0]), reverse=True)

_CATEGORY_FUZZY: list[tuple[str, str]] = sorted(
    {(syn, canon) for canon, syns in CATEGORY_SYNONYMS.items() for syn in syns}
    | {(c, c) for c in CANONICAL_CATEGORIES},
    key=lambda x: len(x[0]),
    reverse=True,
)

_CITY_FUZZY: list[tuple[str, str]] = sorted(
    {(c, c) for c in KNOWN_CITIES}
    | {(alias, canon) for alias, canon in _CITY_ALIASES.items()},
    key=lambda x: len(x[0]),
    reverse=True,
)

_BRAND_FUZZY: list[tuple[str, str]] = [(b, b) for b in KNOWN_BRANDS]

_INTENT_FUZZY: list[tuple[str, str]] = [
    ("rent", "rent"), ("rental", "rent"), ("hire", "hire"),
    ("buy", "buy"), ("sell", "sell"), ("purchase", "purchase"),
    ("budget", "budget"), ("kiraye", "kiraye"), ("kiraya", "kiraya"),
]


@dataclass
class SpellResult:
    original_query: str
    corrected_query: str
    corrections: list[dict[str, Any]] = field(default_factory=list)
    action: str = "none"  # none | auto

    def to_context(self) -> dict[str, Any]:
        if not self.corrections:
            return {}
        return {
            "original_query": self.original_query,
            "corrected_query": self.corrected_query,
            "corrections": self.corrections,
        }


def is_spell_confirmation_yes(message: str) -> bool:
    return bool(_YES_RE.match((message or "").strip()))


def is_spell_confirmation_no(message: str) -> bool:
    return bool(_NO_RE.match((message or "").strip()))


def spell_confirmation_message(corrections: list[dict], corrected_query: str) -> str:
    """Legacy helper — confirmation flow disabled; kept for API compatibility."""
    parts = [f'"{c["from"]}" → {c["to"]}' for c in corrections]
    return (
        "Continuing with your original request. "
        f"(Suggested fix: {', '.join(parts)})"
    )


def spell_confirm_pending_state(spell: SpellResult) -> dict:
    return {
        "missing_field": "spell_confirm",
        "original_query": spell.original_query,
        "corrected_query": spell.corrected_query,
        "corrections": spell.corrections,
    }


def should_apply_spelling(query: str) -> bool:
    """Return False for greetings and non-marketplace chit-chat."""
    text = (query or "").strip()
    if not text or text.isdigit():
        return False
    if _GREETING_LIKE_RE.match(text):
        return False

    tokens = re.findall(r"[a-z]+", text.lower())
    if not tokens:
        return False
    if all(t in _STOP_WORDS | _NEVER_FUZZY for t in tokens):
        return False

    # Pure rejection / acknowledgment — never spell-check.
    if _NO_RE.match(text) or _YES_RE.match(text):
        return False

    return True


def _query_has_strong_exact_match(query: str) -> dict[str, bool]:
    return {
        "category": bool(detect_requested_category(query)),
        "city": bool(detect_city(query)),
        "brand": bool(detect_brand(query)),
        "model": bool(detect_model(query)),
        "listing_type": bool(detect_listing_type(query)),
    }


def _blocked_candidate(token: str, canonical: str, field: str, query: str) -> bool:
    q = query.lower()
    tok = token.lower()

    if canonical == "excavator" and ("jcb" in q or tok == "jcb"):
        return True
    if canonical == "crane" and field == "category":
        if re.search(r"\bhydra\b", q) and tok != "hydra":
            return True
    if canonical == "crane" and "hydra" in q:
        return True
    return False


def _length_ok(token: str, label: str) -> bool:
    return abs(len(token) - len(label)) <= 2


def _field_threshold(field: str, token: str, label: str) -> int:
    if field == "city":
        return AUTO_CORRECT_THRESHOLD
    if field == "brand":
        if label in _SHORT_BRANDS or len(label) <= 4:
            return 95
        return AUTO_CORRECT_THRESHOLD
    if field == "category":
        return AUTO_CORRECT_THRESHOLD
    return AUTO_CORRECT_THRESHOLD


def _best_fuzzy_match(
    text: str,
    choices: list[tuple[str, str]],
    *,
    field: str,
    query: str,
) -> Optional[tuple[str, str, int]]:
    if not text or text.lower() in _NEVER_FUZZY or text.lower() in _STOP_WORDS:
        return None
    if len(text) < 4:
        return None

    threshold = AUTO_CORRECT_THRESHOLD
    labels = [c[0] for c in choices]
    match = process.extractOne(text, labels, scorer=fuzz.ratio, score_cutoff=threshold)
    if not match:
        return None

    label, score, _idx = match
    if not _length_ok(text, label):
        return None
    if score < _field_threshold(field, text, label):
        return None

    canonical = next(c[1] for c in choices if c[0] == label)
    if _blocked_candidate(text, canonical, field, query):
        return None
    if text.lower() == canonical.lower():
        return None

    return label, canonical, int(score)


def _find_dictionary_hits(query: str) -> list[dict[str, Any]]:
    lowered = query.lower()
    hits: list[dict[str, Any]] = []
    used_spans: list[tuple[int, int]] = []

    for typo, replacement in sorted(SPELLING_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(typo)}\b", re.I)
        for m in pattern.finditer(lowered):
            span = (m.start(), m.end())
            if any(s <= span[0] < e or s < span[1] <= e for s, e in used_spans):
                continue
            used_spans.append(span)
            hits.append({
                "from": query[m.start():m.end()],
                "to": replacement,
                "confidence": 100,
                "field": "dictionary",
                "start": m.start(),
                "end": m.end(),
            })
    return hits


def _find_phrase_hits(query: str, exact: dict[str, bool]) -> list[dict[str, Any]]:
    if exact.get("category"):
        return []

    lowered = query.lower()
    hits: list[dict[str, Any]] = []
    used_spans: list[tuple[int, int]] = []

    for phrase, canonical, field in _MULTI_WORD_PHRASES:
        if phrase in lowered:
            continue
        words = phrase.split()
        if len(words) < 2:
            continue

        q_words = re.findall(r"[a-z0-9]+", lowered)
        for i in range(len(q_words) - len(words) + 1):
            window = " ".join(q_words[i : i + len(words)])
            if window == phrase:
                continue
            score = fuzz.ratio(window, phrase)
            if score < AUTO_CORRECT_THRESHOLD:
                continue
            if _blocked_candidate(window, canonical, field, query):
                continue

            m = re.search(re.escape(window), lowered)
            if not m:
                continue
            span = (m.start(), m.end())
            if any(s <= span[0] < e or s < span[1] <= e for s, e in used_spans):
                continue
            used_spans.append(span)
            hits.append({
                "from": query[m.start():m.end()],
                "to": canonical,
                "confidence": score,
                "field": field,
                "start": m.start(),
                "end": m.end(),
            })
    return hits


def _find_token_hits(query: str, exact: dict[str, bool]) -> list[dict[str, Any]]:
    lowered = query.lower()
    hits: list[dict[str, Any]] = []
    used_spans: list[tuple[int, int]] = []

    for m in re.finditer(r"[a-z][a-z0-9]{2,}", lowered):
        token = m.group(0)
        if token in _STOP_WORDS or token in _NEVER_FUZZY:
            continue
        span = (m.start(), m.end())
        if any(s <= span[0] < e or s < span[1] <= e for s, e in used_spans):
            continue

        # City first — avoids city typos being misread as brands.
        field_order: list[tuple[str, list[tuple[str, str]]]] = []
        if not exact.get("city"):
            field_order.append(("city", _CITY_FUZZY))
        if not exact.get("category"):
            field_order.append(("category", _CATEGORY_FUZZY))
        if not exact.get("brand"):
            field_order.append(("brand", _BRAND_FUZZY))
        if not exact.get("listing_type"):
            field_order.append(("intent", _INTENT_FUZZY))

        matched = False
        for fld, corpus in field_order:
            found = _best_fuzzy_match(token, corpus, field=fld, query=query)
            if not found:
                continue
            _label, canonical, score = found
            used_spans.append(span)
            hits.append({
                "from": query[m.start():m.end()],
                "to": canonical,
                "confidence": score,
                "field": fld,
                "start": m.start(),
                "end": m.end(),
            })
            matched = True
            break
        if matched:
            continue

    return hits


def _merge_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not hits:
        return []
    hits = sorted(hits, key=lambda h: (-h["confidence"], -h.get("start", 0)))
    kept: list[dict[str, Any]] = []
    used: list[tuple[int, int]] = []

    for h in hits:
        start, end = h.get("start", -1), h.get("end", -1)
        if start >= 0 and any(s <= start < e or s < end <= e for s, e in used):
            continue
        if start >= 0:
            used.append((start, end))
        kept.append({k: v for k, v in h.items() if k not in ("start", "end")})
    return kept


def _apply_corrections(query: str, hits: list[dict[str, Any]]) -> str:
    if not hits:
        return query
    result = query
    ordered = sorted(
        hits,
        key=lambda h: query.lower().find(h["from"].lower()),
        reverse=True,
    )
    for h in ordered:
        pattern = re.compile(re.escape(h["from"]), re.I)
        result = pattern.sub(h["to"], result, count=1)
    return result


def _decide_action(corrections: list[dict[str, Any]]) -> str:
    if not corrections:
        return "none"
    if all(c["confidence"] >= AUTO_CORRECT_THRESHOLD or c.get("field") == "dictionary"
           for c in corrections):
        return "auto"
    return "none"


def _has_marketplace_signal(query: str) -> bool:
    parsed = {
        "category": detect_requested_category(query),
        "city": detect_city(query),
        "brand": detect_brand(query),
    }
    return bool(parsed["category"] or parsed["city"] or parsed["brand"])


def resolve_spelling(query: str) -> SpellResult:
    original = (query or "").strip()
    if not original or not should_apply_spelling(original):
        return SpellResult(original, original)

    exact = _query_has_strong_exact_match(original)
    hits = (
        _find_dictionary_hits(original)
        + _find_phrase_hits(original, exact)
        + _find_token_hits(original, exact)
    )
    corrections = _merge_hits(hits)
    corrected = _apply_corrections(original, corrections)
    action = _decide_action(corrections)

    if action != "auto":
        corrections = []
        corrected = original

    return SpellResult(
        original_query=original,
        corrected_query=corrected,
        corrections=corrections,
        action=action,
    )


def _groq_spell_correct(query: str) -> list[dict[str, Any]]:
    if not settings.GROQ_API_KEY:
        return []
    try:
        from app.core.groq_client import client

        prompt = f"""Fix ONLY obvious spelling typos in this construction equipment search query.
Query: "{query}"

Rules:
- JCB = backhoe loader, NEVER excavator
- hydra crane stays hydra crane (not plain crane)
- Only fix machine categories, cities, brands — NOT common English words like there/here/hello
- nodia → noida, jaipir → jaipur, excvator → excavator
- Return ONLY JSON: {{"corrections":[{{"from":"typo","to":"correct","confidence":0-100}}]}}
- confidence must be >= 88 to include, else return empty list"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        content = (response.choices[0].message.content or "").strip()
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        out = []
        for c in data.get("corrections") or []:
            conf = int(c.get("confidence") or 0)
            src = str(c.get("from") or "").strip()
            dst = str(c.get("to") or "").strip()
            if not src or not dst or conf < AUTO_CORRECT_THRESHOLD:
                continue
            if src.lower() in _NEVER_FUZZY | _STOP_WORDS:
                continue
            if _blocked_candidate(src, dst, "category", query):
                continue
            out.append({
                "from": src,
                "to": dst,
                "confidence": conf,
                "field": "groq",
            })
        return out
    except Exception:
        return []


async def resolve_spelling_async(query: str) -> SpellResult:
    spell = resolve_spelling(query)
    if spell.corrections or not should_apply_spelling(query):
        return spell

    # Groq only when local found nothing AND query looks like a real search.
    if settings.GROQ_API_KEY and _has_marketplace_signal(query) is False:
        tokens = [t for t in re.findall(r"[a-z]{4,}", query.lower())
                  if t not in _STOP_WORDS | _NEVER_FUZZY]
        if len(tokens) >= 1:
            groq_hits = _groq_spell_correct(query)
            if groq_hits:
                merged = _merge_hits([
                    {**h, "start": query.lower().find(h["from"].lower()),
                     "end": query.lower().find(h["from"].lower()) + len(h["from"])}
                    for h in groq_hits
                    if query.lower().find(h["from"].lower()) >= 0
                ])
                if merged and _decide_action(merged) == "auto":
                    return SpellResult(
                        original_query=query,
                        corrected_query=_apply_corrections(query, merged),
                        corrections=merged,
                        action="auto",
                    )
    return spell


def apply_confirmed_spelling(pending: dict) -> tuple[str, dict]:
    corrected = pending.get("corrected_query") or ""
    ctx = {
        "original_query": pending.get("original_query"),
        "corrected_query": corrected,
        "corrections": pending.get("corrections") or [],
        "confirmed": True,
    }
    return corrected, ctx
