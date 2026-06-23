"""
Machine specification knowledge - structural detection + reference catalog lookup.

Answers spec/detail/info queries about named machines without marketplace search.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.brand_catalog import detect_brand
from app.ai.category_mapping import category_label, detect_model, detect_requested_category
from app.ai.query_parser import parse_query
from app.chatbot.language import pick_lang
from data.model_reference_specs import lookup_model_specs

# Info / spec / detail signals (English + Hindi/Hinglish) - structural families
_MACHINE_INFO_SIGNAL_RE = re.compile(
    r"(?:"
    r"\b(?:spec(?:ification)?s?|detail?s?|info(?:rmation)?|feature?s?|"
    r"dimension?s?|measurement?s?|size|weight|height|width|length|"
    r"capacity|power|engine|hp|torque|bucket|lifting|operating|"
    r"fuel|petrol|diesel|mileage|consumption|efficiency|performance|output)\b"
    r"|\b(?:vivaran|vivran|jankari|jaankari)\b"
    r"|\b(?:ke\s+baare\s+me|bare\s+me|baare\s+mein|iske\s+bare\s+me|iske\s+bare\s+mai|"
    r"bare\s+mai|ke\s+bare\s+me|ke\s+bare\s+mai)\b"
    r"|\b(?:kitna|kitni|kya\s+hai)\b"
    r"|\b(?:batao|bataiye|bataie|janna|janiye|samjhao|bata)\b"
    r"|\b(?:kese|kaise|kesa|kaisa|kaisi)\s+(?:hai|hain|ho|h)\b"
    r"|\b(?:machine|machinery|equipment)\s+(?:kese|kaise|kesa|kaisa|kaisi)\b"
    r"|\b(?:how\s+is|how\s+good|how\s+well)\b"
    r"|\btell\s+me\s+(?:something\s+)?(?:about|regarding)\b"
    r"|\bgive\s+me\s+(?:the\s+)?(?:spec|detail|info|information|feature)\b"
    r"|\bgive\s+details?\b"
    r"|\bdetails?\s+of\b"
    r"|\b(?:aur|more)\s+(?:info(?:rmation)?|details?|jankari)\b"
    r"|\b(?:info(?:rmation)?|details?|jankari)\s+do\b"
    r"|\bshow\s+me\s+(?:the\s+)?(?:spec|detail|info)\b"
    r"|\bsomething\s+about\b"
    r"|\b(?:use|usage|application|mileage|fuel\s+consumption)\b"
    r")",
    re.I | re.UNICODE,
)

# Pure definitional - handled by domain_definition unless spec words present
_PURE_DEFINITION_RE = re.compile(
    r"(?:"
    r"\bwhat(?:'s|s|\s+is|\s+are)\b"
    r"|\bexplain\b|\bdescribe\b|\bdefine\b"
    r"|\bmeaning\s+of\b"
    r"|kya\s+hai\b|kya\s+hot[ae]\b"
    r")",
    re.I | re.UNICODE,
)

_SPEC_WORD_RE = re.compile(
    r"\b(?:spec|detail|info|feature|engine|dimension|weight|power|vivaran|jankari|jaankari)\b",
    re.I,
)

_MARKETPLACE_SEARCH_SHAPE_RE = re.compile(
    r"\b(?:"
    r"rent|buy|hire|kiraye|kiraya|chahiye|chaiye|available|dikhao|dikhado|"
    r"find|search|show\s+me\s+(?:all\s+)?(?:machine|listing)|listings|milega|book"
    r")\b",
    re.I,
)

_MODEL_TOKEN_RE = re.compile(
    r"\b(?:pc[- ]?\d{3}|3dx|4dx|2dx|320d|120k2|zaxis\s*\d+|r\d{3}[a-z-]*|ec\d{3}|"
    r"lm[- ]?\d+|scs\d+[a-z]*|bp\s*\d+|am\b)\b",
    re.I,
)

_COMPARISON_EXCLUSION_RE = re.compile(
    r"\b(?:vs\.?|versus|compare|comparison|which\s+is\s+better|kaun\s+sa\s+best|"
    r"kaunsi\s+best|konsi\s+best)\b",
    re.I,
)

_MACHINE_ADVISORY_RE = re.compile(
    r"(?:"
    r"\b(?:kese|kaise)\s+(?:badiya|behtar|acch[ae]|badhiya)\b"
    r"|\b(?:better|behtar|superior)\s+than\s+(?:other|others|rest|baki|dusre)\b"
    r"|\bbaki\s+(?:machines?|dusre|models?)\s+se\b"
    r"|\badvantages?\s+of\b"
    r"|\bwhy\s+(?:choose|pick|prefer)\b"
    r"|\b(?:kya|kyu|kyun)\s+(?:special|unique|better|acch[ae])\b"
    r"|\bworth\s+(?:it|buying|renting)\b"
    r")",
    re.I,
)

_BRAND_VS_BRAND_RE = re.compile(
    r"\b(?:vs\.?|versus|compare|comparison)\b"
    r"|\b(?:better|behtar|acch[ae]|badiya).{0,40}\b(?:or|ya)\b"
    r"|\b(?:or|ya)\b.{0,40}\b(?:better|behtar|acch[ae]|badiya)\b",
    re.I,
)


def _extract_model_from_text(text: str) -> Optional[str]:
    model = detect_model(text)
    if model:
        return model
    m = _MODEL_TOKEN_RE.search(text or "")
    if m:
        return m.group(0).upper().replace("  ", " ")
    return None


def _display_name(
    *,
    brand: str | None,
    model: str | None,
    category: str | None,
) -> str:
    parts = [p for p in (brand, model) if p]
    if parts:
        name = " ".join(parts)
        if category and category_label(category):
            cat_label = category_label(category) or category
            if cat_label.lower() not in name.lower():
                name = f"{name} {cat_label}"
        return name
    if category:
        return category_label(category) or category.title()
    return "this machine"


def _resolve_machine_entity(
    text: str,
    parsed: dict,
) -> tuple[str | None, str | None, str | None]:
    brand = parsed.get("brand") or detect_brand(text)
    model = parsed.get("model") or _extract_model_from_text(text)
    category = parsed.get("category") or detect_requested_category(text)
    return brand, model, category


def detect_machine_advisory_query(
    message: str,
    parsed: dict | None = None,
    *,
    session_ctx: dict | None = None,
) -> Optional[dict[str, Any]]:
    """Qualitative / comparative questions about a named machine (not marketplace search)."""
    text = (message or "").strip()
    if not text or not _MACHINE_ADVISORY_RE.search(text):
        return None

    from app.ai.capability_registry import has_marketplace_action_signal

    parsed = dict(parsed or parse_query(text))
    if parsed.get("city") and has_marketplace_action_signal(text):
        return None

    brand, model, category = _resolve_machine_entity(text, parsed)
    if not (brand or model):
        return None

    if _BRAND_VS_BRAND_RE.search(text):
        from app.ai.category_mapping import detect_all_brands

        if len(detect_all_brands(text)) >= 2:
            return None

    return {
        "kind": "machine_advisory",
        "brand": brand,
        "model": model,
        "category": category,
        "display_name": _display_name(brand=brand, model=model, category=category),
        "reason": "machine_advisory_signal",
    }


def detect_machine_knowledge_query(
    message: str,
    parsed: dict | None = None,
    *,
    session_ctx: dict | None = None,
) -> Optional[dict[str, Any]]:
    """Unified machine knowledge: specs, details, or advisory — never marketplace search."""
    spec = detect_machine_spec_query(message, parsed, session_ctx=session_ctx)
    if spec:
        return spec
    return detect_machine_advisory_query(message, parsed, session_ctx=session_ctx)


def detect_machine_spec_query(
    message: str,
    parsed: dict | None = None,
    *,
    session_ctx: dict | None = None,
) -> Optional[dict[str, Any]]:
    """
    Return machine spec knowledge payload when user asks for specs/details about a machine.
    Structural - not phrase-specific.
    """
    text = (message or "").strip()
    if not text:
        return None

    from app.ai.capability_registry import has_marketplace_action_signal

    parsed = dict(parsed or parse_query(text))
    brand, model, category = _resolve_machine_entity(text, parsed)

    # Brand-vs-brand comparison is not a single-machine spec lookup
    if _BRAND_VS_BRAND_RE.search(text):
        from app.ai.category_mapping import detect_all_brands

        if len(detect_all_brands(text)) >= 2:
            return None

    if _MACHINE_ADVISORY_RE.search(text):
        return None

    if not _MACHINE_INFO_SIGNAL_RE.search(text):
        return None

    # Pure "what is X" without spec/detail words -> domain_definition path
    if _PURE_DEFINITION_RE.search(text) and not _SPEC_WORD_RE.search(text):
        if not model:
            return None

    # Marketplace listing search in a city - not a spec query
    if parsed.get("city") and (
        _MARKETPLACE_SEARCH_SHAPE_RE.search(text) or has_marketplace_action_signal(text)
    ):
        return None

    has_machine_entity = bool(brand or model)
    if not has_machine_entity and category and _SPEC_WORD_RE.search(text):
        has_machine_entity = True

    if not has_machine_entity:
        return None

    if brand and not model:
        model = _extract_model_from_text(text)

    return {
        "kind": "machine_specification",
        "brand": brand,
        "model": model,
        "category": category,
        "display_name": _display_name(brand=brand, model=model, category=category),
        "reason": "machine_specification_signal",
    }


_SPEC_LABELS = {
    "engine_power": "Engine power",
    "operating_weight": "Operating weight",
    "bucket_capacity": "Bucket capacity",
    "max_digging_depth": "Max digging depth",
    "fuel_type": "Fuel type",
    "fuel_consumption": "Fuel consumption",
    "lifting_capacity": "Lifting capacity",
    "drum_capacity": "Drum capacity",
    "output_capacity": "Output capacity",
    "applications": "Applications",
    "category": "Category",
    "note": "Note",
}


def build_machine_advisory_draft(
    turn: dict[str, Any],
    *,
    lang: str = "english",
) -> str:
    """Local draft for qualitative machine questions — LLM enriches in build_knowledge_answer."""
    display = turn.get("display_name") or "this machine"
    specs = lookup_model_specs(
        brand=turn.get("brand"),
        model=turn.get("model"),
        category=turn.get("category"),
    )
    lines = [f"**{display}** — overview:"]
    if specs:
        for key in ("applications", "engine_power", "operating_weight", "fuel_consumption", "note"):
            val = specs.get(key)
            if val:
                lines.append(f"- **{_SPEC_LABELS.get(key, key.title())}:** {val}")
    else:
        cat = category_label(turn.get("category")) or turn.get("category") or "equipment"
        lines.append(
            f"- Typical {cat} used for construction, infrastructure, and site work in India."
        )
    lines.append(
        pick_lang(
            lang,
            english=(
                "Strengths usually include reliability, service network, and suitability for Indian site conditions. "
                "Exact advantages depend on model year, maintenance, and job type."
            ),
            hindi=(
                "Indian conditions me reliability, service network aur job suitability important hoti hai. "
                "Model year aur maintenance par performance depend karti hai."
            ),
            hinglish=(
                "Indian sites par reliability, service network aur job fit important hai. "
                "Model year aur maintenance se performance change hoti hai."
            ),
        )
    )
    return "\n".join(lines)


def build_machine_spec_draft(
    turn: dict[str, Any],
    *,
    lang: str = "english",
) -> str:
    """Format reference specs for a machine spec knowledge turn."""
    brand = turn.get("brand")
    model = turn.get("model")
    category = turn.get("category")
    display = turn.get("display_name") or _display_name(
        brand=brand, model=model, category=category,
    )

    specs = lookup_model_specs(brand=brand, model=model, category=category)
    lines: list[str] = []
    has_spec_values = specs and any(
        specs.get(k) for k in _SPEC_LABELS if k != "note"
    )

    if specs and (brand or model) and has_spec_values:
        lines.append(f"**{display}** - reference specifications:")
        for key, label in _SPEC_LABELS.items():
            val = specs.get(key)
            if val and key not in ("note",):
                lines.append(f"- **{label}:** {val}")
        note = specs.get("note")
        if note:
            lines.append(f"- **Note:** {note}")
        footer = pick_lang(
            lang,
            english=(
                "These are typical manufacturer specs - actual listing may vary by year and condition. "
                "Search InfraForge by city for live rent/buy options."
            ),
            hindi=(
                "Ye typical manufacturer specs hain - listing ke hisaab se alag ho sakti hain. "
                "Live rent/buy ke liye InfraForge par city choose karke search karein."
            ),
            hinglish=(
                "Ye typical specs hain - actual machine listing par thoda differ ho sakta hai. "
                "Live options ke liye InfraForge par city-wise search kar sakte ho."
            ),
        )
        lines.append("")
        lines.append(footer)
        return "\n".join(lines)

    if specs and category and not (brand and model):
        cat_label = category_label(category) or category
        lines.append(f"**{cat_label}** - general information:")
        for key in ("applications", "fuel_type", "note"):
            val = specs.get(key)
            if val:
                lines.append(f"- **{_SPEC_LABELS.get(key, key.title())}:** {val}")
        lines.append("")
        lines.append(
            pick_lang(
                lang,
                english=f"For exact specs, name a brand and model (e.g. Komatsu PC210 {cat_label}).",
                hindi="Exact specs ke liye brand aur model batayein (jaise Komatsu PC210).",
                hinglish="Exact specs ke liye brand+model batao (jaise Komatsu PC210).",
            )
        )
        return "\n".join(lines)

    return pick_lang(
        lang,
        english=(
            f"I don't have full reference specs for **{display}** in my catalog yet. "
            f"Typical {category_label(category) or category or 'equipment'} specs depend on model year and variant. "
            f"Search InfraForge by city to see live listings with available details, or ask me to compare brands."
        ),
        hindi=(
            f"**{display}** ke liye mere paas abhi poori reference specs nahi hain. "
            f"Live listings InfraForge par city ke hisaab se dekh sakte hain."
        ),
        hinglish=(
            f"**{display}** ki full reference specs abhi catalog me nahi hain. "
            f"InfraForge par city search karke live listing details dekh sakte ho."
        ),
    )
