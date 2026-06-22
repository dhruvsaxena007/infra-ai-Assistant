"""
Universal message normalization — typos, Hinglish, speech-to-text errors.

Runs BEFORE turn classification so one fix covers greetings, compare, search,
support, and chip follow-ups (not per-intent patches).

Layers:
  1. Structural regex (discourse shape — e.g. "my name id X" → "my name is X")
  2. Token dictionary (brands, cities, Hinglish)
  3. Optional Groq when USE_GROQ_MESSAGE_NORMALIZER=true and rules made no change
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings

# Structural fixes — shape-based, not example sentences.
_STRUCTURAL: list[tuple[re.Pattern, str]] = [
    # Name intro typos (speech / keyboard)
    (re.compile(r"\bmy\s+name\s+(?:id|iz|i'd|its|it's|i\s*am)\s+", re.I), "my name is "),
    (re.compile(r"\bmera\s+naam\s+(?:id|iz|hai|he|h)\s+", re.I), "mera naam hai "),
    (re.compile(r"\b(?:people|they)\s+(?:know|call)\s+me\s+(?:as|by|id|iz)\s+", re.I), "people know me as "),
    (re.compile(r"\bcall\s+me\s+(?:as|by|id|iz)\s+", re.I), "call me "),
    # Hinglish prepositions / common STT
    (re.compile(r"\b(rent|buy|purchase|kiraye?)\s+pai\b", re.I), r"\1 pe"),
    (re.compile(r"\bjaipur\s+mai\b", re.I), "jaipur mein"),
    (re.compile(r"\bdelhi\s+mai\b", re.I), "delhi mein"),
    (re.compile(r"\bmumbai\s+mai\b", re.I), "mumbai mein"),
    # Compare connectors
    (re.compile(r"\bacche\s+hote\s+hai\s+ya\b", re.I), "acche hote hain ya"),
]

# Multi-word typo fixes (marketplace search phrases).
_PHRASE_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhydra\s+crne\b", re.I), "hydra crane"),
    (re.compile(r"\bhydra\s+crain\b", re.I), "hydra crane"),
    (re.compile(r"\broad\s+rolar\b", re.I), "road roller"),
    (re.compile(r"\bdump\s+truk\b", re.I), "dump truck"),
    (re.compile(r"\bcrawlar\s+dril\b", re.I), "crawler drill"),
    (re.compile(r"\bcrawler\s+dril\b", re.I), "crawler drill"),
    (re.compile(r"\bbackhoe\s+loadr\b", re.I), "backhoe loader"),
]

# Single-token replacements (word-boundary safe).
_TOKEN_FIXES: dict[str, str] = {
    # Brands / equipment
    "hundai": "hyundai",
    "hyundia": "hyundai",
    "hyudai": "hyundai",
    "caterpilar": "caterpillar",
    "caterpillar": "caterpillar",
    "catarpillar": "caterpillar",
    "jcb": "jcb",
    "volvo": "volvo",
    "komatsu": "komatsu",
    # Cities
    "jaipir": "jaipur",
    "jaypur": "jaipur",
    "delih": "delhi",
    "dehli": "delhi",
    "mumabi": "mumbai",
    # Categories
    "exavator": "excavator",
    "excvator": "excavator",
    "excavtor": "excavator",
    "rolar": "roller",
    "rolle": "roller",
    "truk": "truck",
    "crne": "crane",
    "crain": "crane",
    # English typos
    "genrally": "generally",
    "generaly": "generally",
    "generlly": "generally",
    "wese": "waise",
    "waisa": "waise",
    "specifcation": "specification",
    "specifictions": "specifications",
    "consumtion": "consumption",
    # Hinglish normalize (helps downstream token match)
    "chaiye": "chahiye",
    "chahiy": "chahiye",
    "chata": "chahata",
    "acche": "achhe",
    "accha": "achha",
    "theek": "thik",
}

# Never replace these tokens even if fuzzy-close.
_PROTECTED = frozenset({
    "id", "is", "it", "in", "on", "or", "ya", "ke", "pe", "hi", "ok",
    "cat", "jcb", "yes", "no", "me", "my", "we", "he", "she",
})


@dataclass
class NormalizedMessage:
    original: str
    corrected: str
    corrections: list[dict[str, Any]] = field(default_factory=list)
    layer: str = "none"  # none | rules | groq

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "corrections": self.corrections,
            "layer": self.layer,
        }


def _apply_phrases(text: str) -> tuple[str, list[dict]]:
    out = text
    hits: list[dict] = []
    for pattern, repl in _PHRASE_FIXES:
        new = pattern.sub(repl, out)
        if new != out:
            hits.append({"from": out, "to": new, "field": "phrase"})
            out = new
    return out, hits


def _apply_structural(text: str) -> tuple[str, list[dict]]:
    out = text
    hits: list[dict] = []
    for pattern, repl in _STRUCTURAL:
        new = pattern.sub(repl, out)
        if new != out:
            hits.append({"from": out, "to": new, "field": "structural"})
            out = new
    return out, hits


def _apply_tokens(text: str) -> tuple[str, list[dict]]:
    out = text
    hits: list[dict] = []
    for m in re.finditer(r"[a-zA-Z]+", text):
        raw = m.group(0)
        low = raw.lower()
        if low in _PROTECTED:
            continue
        fixed = _TOKEN_FIXES.get(low)
        if not fixed or fixed.lower() == low:
            continue
        repl = fixed if raw.islower() else fixed.title() if raw.istitle() else fixed
        pattern = re.compile(rf"\b{re.escape(raw)}\b")
        new = pattern.sub(repl, out, count=1)
        if new != out:
            hits.append({"from": raw, "to": repl, "field": "token"})
            out = new
    return out, hits


def _apply_catalog_fuzzy(text: str) -> tuple[str, list[dict]]:
    """Fuzzy-match tokens against catalog cities/categories (mechanism, not phrase patches)."""
    try:
        from rapidfuzz import fuzz, process
        from app.ai.category_mapping import KNOWN_CITIES, _CITY_ALIASES, CATEGORY_SYNONYMS
    except Exception:
        return text, []

    vocab: dict[str, str] = {}
    for city in KNOWN_CITIES:
        vocab[city.lower()] = city.lower()
    for alias, canon in _CITY_ALIASES.items():
        vocab[alias.lower()] = canon.lower()
    for canon, synonyms in (CATEGORY_SYNONYMS or {}).items():
        vocab[canon.lower()] = canon.lower()
        for syn in synonyms or []:
            if isinstance(syn, str):
                vocab[syn.lower()] = canon.lower()

    choices = list(vocab.keys())
    if not choices:
        return text, []

    out = text
    hits: list[dict] = []
    for m in re.finditer(r"[a-zA-Z]{4,}", text):
        raw = m.group(0)
        low = raw.lower()
        if low in _PROTECTED or low in vocab:
            continue
        match = process.extractOne(low, choices, scorer=fuzz.ratio)
        if not match or match[1] < 88:
            continue
        canon = vocab.get(match[0], match[0])
        if canon == low:
            continue
        pattern = re.compile(rf"\b{re.escape(raw)}\b", re.I)
        new = pattern.sub(canon, out, count=1)
        if new != out:
            hits.append({"from": raw, "to": canon, "field": "catalog_fuzzy", "score": match[1]})
            out = new
    return out, hits


def normalize_user_message(message: str) -> NormalizedMessage:
    """Synchronous rules normalization — always safe, no API cost."""
    original = (message or "").strip()
    if not original:
        return NormalizedMessage(original, original)

    corrected, phrase_hits = _apply_phrases(original)
    corrected, struct_hits = _apply_structural(corrected)
    corrected, token_hits = _apply_tokens(corrected)
    corrected, catalog_hits = _apply_catalog_fuzzy(corrected)
    corrections = phrase_hits + struct_hits + token_hits + catalog_hits

    return NormalizedMessage(
        original=original,
        corrected=corrected,
        corrections=corrections,
        layer="rules" if corrections else "none",
    )


async def normalize_user_message_async(message: str) -> NormalizedMessage:
    """
    Rules first; optional Groq for residual typos when flag enabled.
    Groq only runs when rules changed nothing AND message looks user-facing.
    """
    base = normalize_user_message(message)
    if base.corrections or not settings.USE_GROQ_MESSAGE_NORMALIZER:
        return base
    if not settings.GROQ_API_KEY:
        return base

    text = base.original.strip()
    if len(text.split()) > 40 or len(text) < 3:
        return base

    groq_fix = _groq_normalize(text)
    if not groq_fix:
        return base

    corrected = groq_fix.get("corrected") or text
    if corrected.strip().lower() == text.lower():
        return base

    return NormalizedMessage(
        original=text,
        corrected=corrected.strip(),
        corrections=[{
            "from": text,
            "to": corrected.strip(),
            "field": "groq",
            "reason": groq_fix.get("reason"),
        }],
        layer="groq",
    )


def _groq_normalize(message: str) -> Optional[dict[str, str]]:
    try:
        from app.core.groq_client import groq_chat_completion

        prompt = f"""Fix spelling/grammar typos in this marketplace chat message.
Keep meaning identical. Fix Hinglish, speech errors, keyboard typos.
Do NOT add information. Do NOT turn into a search query.

Message: "{message}"

Return ONLY JSON:
{{"corrected":"fixed text","reason":"brief"}}"""

        response = groq_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            tag="message_normalizer",
        )
        if not response or not response.choices:
            return None
        content = (response.choices[0].message.content or "").strip()
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        corrected = str(data.get("corrected") or "").strip()
        if corrected:
            return {"corrected": corrected, "reason": str(data.get("reason") or "")}
    except Exception:
        pass
    return None
