"""
Numeric normalization for Indian marketplace budgets and rates.

Handles: 7k, 8.5k, 10K, lakh/lac, cr/crore, ₹, Hindi forms (hazaar, ke andar,
per day, din ka, etc.). Applied before entity parsing / price detection.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Bare shorthand: 7k, 8.5k, 10K (optionally with /day or per day)
_BARE_K_RE = re.compile(
    r"(?<!\d)([\d,]+(?:\.\d+)?)\s*[kK](?![a-zA-Z])(?:\s*(?:/|per\s*)?(?:day|din|daily))?",
    re.I,
)

# lakh / lac / crore / cr
_INDIAN_UNIT_RE = re.compile(
    r"(?<!\d)([\d,]+(?:\.\d+)?)\s*(lakh|lac|lakhs|lacs|crore|crores|cr)\b",
    re.I,
)

# Hindi: hazaar / hazar
_HAZAAR_RE = re.compile(
    r"(?<!\d)([\d,]+(?:\.\d+)?)\s*(?:hazaar|hazar|hajar)\b",
    re.I,
)

# "ke andar", "tak", "se kam" after a number
_KE_ANDAR_RE = re.compile(
    r"(?<!\d)([\d,]+(?:\.\d+)?)\s*(?:k|K)?\s*(?:ke\s+andar|tak|se\s+kam|se\s+niche|under|below)\b",
    re.I,
)

# Currency-prefixed with optional k: ₹7k, rs 8.5k
_CURRENCY_K_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*[kK]\b",
    re.I,
)

# per day / din ka after number
_PER_DAY_RE = re.compile(
    r"(?<!\d)([\d,]+(?:\.\d+)?)\s*(?:k|K)?\s*(?:/|per\s*)?(?:day|din|daily|din\s+ka|din\s+ki)\b",
    re.I,
)

_UNIT_MULTIPLIERS = {
    "lakh": 100_000,
    "lac": 100_000,
    "lakhs": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}


def _parse_number(raw: str) -> float:
    return float((raw or "0").replace(",", ""))


def _to_int_amount(value: float) -> int:
    return int(round(value))


def expand_numeric_shorthand(text: str) -> str:
    """
    Replace numeric shorthand in text with full integer strings for downstream parsers.
    E.g. 'under 7k per day' → 'under 7000 per day'
    """
    if not text:
        return text

    result = text

    def _repl_k(m: re.Match) -> str:
        num = _parse_number(m.group(1)) * 1000
        return str(_to_int_amount(num))

    def _repl_unit(m: re.Match) -> str:
        num = _parse_number(m.group(1))
        unit = (m.group(2) or "").lower()
        mult = _UNIT_MULTIPLIERS.get(unit, 1)
        return str(_to_int_amount(num * mult))

    def _repl_hazaar(m: re.Match) -> str:
        num = _parse_number(m.group(1)) * 1000
        return str(_to_int_amount(num))

    def _repl_ke_andar(m: re.Match) -> str:
        raw = m.group(1)
        full = m.group(0)
        num = _parse_number(raw)
        if num < 1000 and re.search(rf"{re.escape(raw)}\s+[kK](?:\s|/|$)", full):
            num *= 1000
        suffix = full[len(raw):].strip()
        return f"{_to_int_amount(num)} {suffix}".strip()

    result = _CURRENCY_K_RE.sub(lambda m: f"rs {_to_int_amount(_parse_number(m.group(1)) * 1000)}", result)
    result = _INDIAN_UNIT_RE.sub(
        lambda m: str(_to_int_amount(_parse_number(m.group(1)) * _UNIT_MULTIPLIERS.get(m.group(2).lower(), 1))),
        result,
    )
    result = _HAZAAR_RE.sub(_repl_hazaar, result)
    result = _BARE_K_RE.sub(_repl_k, result)
    result = _KE_ANDAR_RE.sub(_repl_ke_andar, result)
    return result


def extract_budget_amount(text: str) -> Optional[int]:
    """
    Extract a single budget/rate amount from normalized or raw text.
    Returns integer INR amount or None.
    """
    if not text:
        return None

    normalized = expand_numeric_shorthand(text)
    lowered = normalized.lower()

    for pattern in (
        r"under\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"below\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"less\s+than\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"max(?:imum)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"budget\s*(?:of|is)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"([\d,]+)\s*budget\b",
        r"within\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"up\s*to\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"upto\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"(?:rs\.?|inr|₹)\s*([\d,]+)",
        r"([\d,]+)\s*(?:rs|rupees|/\s*day|per\s*day)",
        r"([\d,]+)\s*(?:rent|kiraye|kiraya)\b",
        r"([\d,]+)\s*(?:ke\s+andar|ke\s+in|tak)\b",
        r"budget\s*(?:is|of)?\s*([\d,]+)",
    ):
        m = re.search(pattern, lowered)
        if m:
            val = _to_int_amount(_parse_number(m.group(1)))
            if val >= 100:
                return val

    m = _BARE_K_RE.search(text)
    if m:
        return _to_int_amount(_parse_number(m.group(1)) * 1000)

    m = _INDIAN_UNIT_RE.search(text)
    if m:
        unit = m.group(2).lower()
        return _to_int_amount(_parse_number(m.group(1)) * _UNIT_MULTIPLIERS.get(unit, 1))

    m = _HAZAAR_RE.search(text)
    if m:
        return _to_int_amount(_parse_number(m.group(1)) * 1000)

    m = re.search(r"(?:din\s+ka|din\s+ki)\s*([\d,]+)", lowered)
    if m:
        return _to_int_amount(_parse_number(m.group(1)))

    # Trailing expanded amount: "excavator jaipur 7000"
    m = re.search(r"(?<!\d)([\d,]+)\s*$", normalized.strip())
    if m:
        val = _to_int_amount(_parse_number(m.group(1)))
        if val >= 1000:
            return val

    return None


def normalize_message_numerics(message: str) -> dict[str, Any]:
    """Return normalized text + extracted budget if present."""
    raw = (message or "").strip()
    expanded = expand_numeric_shorthand(raw)
    budget = extract_budget_amount(expanded) or extract_budget_amount(raw)
    return {
        "raw_message": raw,
        "normalized_message": expanded,
        "budget_amount": budget,
        "had_shorthand": expanded != raw,
    }
