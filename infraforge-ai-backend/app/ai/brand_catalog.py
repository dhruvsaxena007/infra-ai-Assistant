"""
Brand catalog for marketplace entity extraction.

Hybrid source:
  - Static fallback aliases (always available)
  - Runtime names from MongoDB via ReferenceCache.register_brands()

Brand tokens are never used as category synonyms.
"""

from __future__ import annotations

import re
from typing import Optional

# Static fallback: alias (lowercase) -> canonical display name.
# Longest aliases are matched first at runtime.
_STATIC_BRAND_ALIASES: dict[str, str] = {
    "tata hitachi": "Tata Hitachi",
    "schwing stetter": "Schwing Stetter",
    "atlas copco": "Atlas Copco",
    "ammann apollo": "Ammann Apollo",
    "caterpillar": "Caterpillar",
    "epiroc": "EPIROC",
    "komatsu": "Komatsu",
    "hyundai": "Hyundai",
    "hundai": "Hyundai",
    "hyundia": "Hyundai",
    "hitachi": "Hitachi",
    "kobelco": "Kobelco",
    "liebherr": "Liebherr",
    "liugong": "Liugong",
    "mahindra": "Mahindra",
    "terex": "Terex",
    "volvo": "Volvo",
    "escorts": "Escorts",
    "cat": "CAT",
    "jcb": "JCB",
    "tata": "Tata",
    "sany": "SANY",
    "case": "CASE",
    "ace": "ACE",
}

_runtime_aliases: dict[str, str] = {}


def _word_in_text(word: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text, re.I) is not None


def _alias_lookup() -> list[tuple[str, str]]:
    merged: dict[str, str] = {}
    merged.update(_STATIC_BRAND_ALIASES)
    merged.update(_runtime_aliases)
    return sorted(merged.items(), key=lambda pair: len(pair[0]), reverse=True)


def register_brand_names(names: list[str]) -> None:
    """Register brand display names from DB/cache (idempotent)."""
    for name in names or []:
        raw = str(name or "").strip()
        if not raw or len(raw) < 2:
            continue
        canonical = raw.title() if raw.islower() else raw
        key = raw.lower()
        _runtime_aliases[key] = canonical
        # Multi-word brands also register without extra spaces variants
        collapsed = re.sub(r"\s+", " ", key)
        _runtime_aliases[collapsed] = canonical


def register_brand_alias(alias: str, canonical: str) -> None:
    if alias and canonical:
        _runtime_aliases[alias.strip().lower()] = canonical.strip()


def known_brand_aliases() -> list[str]:
    return list(dict.fromkeys(alias for alias, _ in _alias_lookup()))


def detect_all_brands(text: str) -> list[str]:
    """Return all known brands mentioned in text (canonical names, de-duplicated)."""
    if not text:
        return []
    lowered = text.lower()
    found: list[str] = []
    matched_spans: list[tuple[int, int]] = []

    for alias, canonical in _alias_lookup():
        if canonical in found:
            continue
        pattern = re.compile(rf"\b{re.escape(alias)}\b", re.I)
        match = pattern.search(lowered)
        if not match:
            continue
        span = match.span()
        if any(not (span[1] <= s0 or span[0] >= s1) for s0, s1 in matched_spans):
            continue
        found.append(canonical)
        matched_spans.append(span)
    return found


def detect_brand(text: str) -> Optional[str]:
    """Return the primary (longest-match) brand in text, or None."""
    brands = detect_all_brands(text)
    return brands[0] if brands else None


def reset_runtime_brands() -> None:
    """Clear DB-populated brands (for tests)."""
    _runtime_aliases.clear()
