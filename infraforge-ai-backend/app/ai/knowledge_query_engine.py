"""
Generalized knowledge-query engine — answer what the user is asking.

Structural detection (not phrase lists):
  - assistant_identity: who are you / your name
  - domain_definition: what is X / explain X — brand, category, equipment concept

Does NOT run marketplace search. Uses LLM when available; catalog-aware local draft otherwise.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.brand_catalog import detect_brand
from app.ai.category_mapping import category_label, detect_requested_category
from app.ai.query_parser import parse_query
from app.chatbot.language import pick_lang

ASSISTANT_NAME = "InfraForge AI"

# Assistant-directed identity (English + Hindi/Hinglish + typos)
_ASSISTANT_IDENTITY_RE = re.compile(
    r"(?:"
    r"what(?:'s|s|\s+is)\s+(?:your|ur)\s+name"
    r"|who\s+(?:are|r)\s+you"
    r"|what\s+are\s+you(?:\s+called)?"
    r"|(?:your|ur)\s+name\s*\??\s*$"
    r"|tell\s+me\s+(?:about\s+)?yourself"
    r"|introduce\s+yourself"
    r"|aap\s+ka\s+naam"
    r"|tumhara\s+naam"
    r"|aap\s+kaun\s+ho"
    r"|tum\s+kaun\s+ho"
    r"|kaun\s+ho\s+aap"
    r")",
    re.I | re.UNICODE,
)

# Definitional / explanatory question (not marketplace action)
_KNOWLEDGE_DEFINE_RE = re.compile(
    r"(?:"
    r"\bwhat(?:'s|s|\s+is|\s+are)\b"
    r"|\bexplain\b|\btell\s+me\s+about\b|\bdescribe\b|\bdefine\b"
    r"|\bmeaning\s+of\b"
    r"|kya\s+hai\b|kya\s+hot[ae]\b|samjha(?:o|na)\b"
    r"|(?:\w+)\s+kya\s+hai\b"
    r")",
    re.I | re.UNICODE,
)

# Canonical category → one-line domain knowledge (taxonomy, not query hacks)
_CATEGORY_BRIEFS: dict[str, str] = {
    "excavator": (
        "A tracked or wheeled machine with a boom, stick, and bucket for digging, "
        "trenching, and earthmoving."
    ),
    "backhoe loader": (
        "A versatile machine with a front loader bucket and rear backhoe — common for "
        "urban construction, utilities, and small-to-mid excavation."
    ),
    "crane": "Lifting equipment for vertical loads on construction and industrial sites.",
    "road roller": "Compaction machine for roads, highways, and earthwork layers.",
    "wheel loader": "Front-end loader for moving aggregates, soil, and site materials.",
    "dump truck": "Hauling truck for moving excavated material and aggregates.",
    "motor grader": "Precision grading machine for roads and large flat surfaces.",
    "crawler drill": "Tracked drill rig for blasting holes in rock and mining work.",
    "telehandler": "Telescopic handler for lifting pallets and materials at height.",
    "forklift": "Industrial lift truck for palletized material handling.",
    "concrete mixer": "Equipment for preparing and transporting concrete on site.",
    "bulldozer": "Tracked pusher for clearing, grading, and bulk earth movement.",
    "compactor": "Soil or waste compaction machine for layers and fills.",
}

# Brand → typical equipment association (catalog hints, not sentence templates)
_BRAND_EQUIPMENT_HINT: dict[str, str] = {
    "jcb": "backhoe loaders and compact construction equipment",
    "caterpillar": "excavators, loaders, and heavy earthmoving equipment",
    "cat": "excavators, loaders, and heavy earthmoving equipment",
    "komatsu": "excavators and mining/construction equipment",
    "hitachi": "excavators and hydraulic equipment",
    "tata hitachi": "excavators and construction equipment",
    "hyundai": "excavators and construction equipment",
    "volvo": "excavators, haulers, and road construction equipment",
    "jcb india": "backhoe loaders and compact construction equipment",
}


def _is_marketplace_action(message: str) -> bool:
    from app.ai.capability_registry import has_marketplace_action_signal

    return bool(has_marketplace_action_signal(message or ""))


def _resolve_subject(message: str, parsed: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (display_subject, subject_type) where type is brand|category."""
    text = (message or "").strip()
    brand = parsed.get("brand") or detect_brand(text)
    if brand:
        return brand, "brand"

    category = parsed.get("category") or detect_requested_category(text)
    if category:
        return category_label(category) or category, "category"

    tail = re.sub(
        r"^(?:what(?:'s|\s+is|\s+are)|explain|tell\s+me\s+about|kya\s+hai)\s+",
        "",
        text,
        flags=re.I,
    ).strip(" ?!.,")
    if tail:
        b = detect_brand(tail)
        if b:
            return b, "brand"
        cat = detect_requested_category(tail)
        if cat:
            return category_label(cat) or cat, "category"
        if len(tail.split()) <= 4:
            return tail.title(), "concept"
    return None, None


def detect_knowledge_query(
    message: str,
    parsed: dict | None = None,
    *,
    session_ctx: dict | None = None,
) -> Optional[dict[str, Any]]:
    """
    Return knowledge turn payload or None (caller may search/route normally).
    Structural detection — not example phrase lists.
    """
    text = (message or "").strip()
    if not text:
        return None

    parsed = parsed or parse_query(text)

    from app.ai.machine_spec_service import detect_machine_knowledge_query

    machine_knowledge = detect_machine_knowledge_query(text, parsed, session_ctx=session_ctx)
    if machine_knowledge:
        return machine_knowledge

    if _is_marketplace_action(text):
        return None

    parsed = parsed or parse_query(text)

    if _ASSISTANT_IDENTITY_RE.search(text):
        return {
            "kind": "assistant_identity",
            "reason": "assistant_identity_signal",
        }

    from app.ai.semantic_turn_gateway import _MEMORY_QUESTION_RE

    if _MEMORY_QUESTION_RE.search(text):
        name = None
        if session_ctx:
            name = session_ctx.get("user_name") or (session_ctx.get("collected_fields") or {}).get("name")
        return {
            "kind": "memory_question",
            "reason": "memory_question_signal",
            "user_name": name,
        }

    if not _KNOWLEDGE_DEFINE_RE.search(text):
        return None

    subject, subject_type = _resolve_subject(text, parsed)
    if not subject:
        return None

    return {
        "kind": "domain_definition",
        "subject": subject,
        "subject_type": subject_type,
        "reason": "domain_definition_signal",
    }


def knowledge_turn_from_message(
    message: str,
    parsed: dict | None = None,
    *,
    session_ctx: dict | None = None,
) -> Optional[dict[str, Any]]:
    """Single authority for knowledge turns — used by gateway, universal engine, router."""
    return detect_knowledge_query(message, parsed, session_ctx=session_ctx)


def _local_definition_draft(
    *,
    subject: str,
    subject_type: str,
    lang: str,
) -> str:
    key = (subject or "").lower()
    if subject_type == "category":
        brief = _CATEGORY_BRIEFS.get(key.replace("-", " "))
        if not brief:
            for canon, text in _CATEGORY_BRIEFS.items():
                if canon in key or key in canon:
                    brief = text
                    break
        if brief:
            return pick_lang(
                lang,
                english=f"**{subject}** — {brief} On InfraForge you can search available {subject.lower()} listings by city for rent or buy.",
                hindi=f"**{subject}** — {brief} InfraForge par aap city ke hisaab se {subject} ki listings dekh sakte hain.",
                hinglish=f"**{subject}** — {brief} InfraForge par city choose karke {subject} rent/buy search kar sakte ho.",
            )

    if subject_type == "brand":
        hint = _BRAND_EQUIPMENT_HINT.get(key)
        if not hint:
            for alias, equip in _BRAND_EQUIPMENT_HINT.items():
                if alias in key or key in alias:
                    hint = equip
                    break
        equip_phrase = hint or "construction and heavy equipment"
        return pick_lang(
            lang,
            english=(
                f"**{subject}** is a major brand in India's {equip_phrase} space. "
                f"I can explain specs and compare brands, or search live {subject} listings on InfraForge by city."
            ),
            hindi=(
                f"**{subject}** India me {equip_phrase} ke liye ek bada brand hai. "
                f"Main specs/compare bata sakta hoon, ya InfraForge par city ke hisaab se listings dikh sakta hoon."
            ),
            hinglish=(
                f"**{subject}** India me {equip_phrase} ka well-known brand hai. "
                f"Specs/compare bata sakta hoon, ya InfraForge par city-wise listings search kar sakte ho."
            ),
        )

    return pick_lang(
        lang,
        english=(
            f"**{subject}** relates to construction and heavy equipment. "
            f"Tell me if you want a definition, comparison, or live listings on InfraForge."
        ),
        hindi=f"**{subject}** construction/heavy equipment se related hai. Definition, compare ya listings — bataiye.",
        hinglish=f"**{subject}** construction equipment se related hai. Detail, compare ya search — kya chahiye?",
    )


def _local_identity_draft(lang: str) -> str:
    return pick_lang(
        lang,
        english=(
            f"I'm **{ASSISTANT_NAME}** — InfraForge's construction and heavy-equipment assistant. "
            f"I help you search machines by city, compare brands, understand equipment, and reach owners for rent or buy."
        ),
        hindi=(
            f"Main **{ASSISTANT_NAME}** hoon — InfraForge ka construction aur heavy-equipment assistant. "
            f"Machine search, brand compare, equipment samjhana, aur rent/buy ke liye owner se connect karne me madad karta hoon."
        ),
        hinglish=(
            f"Main **{ASSISTANT_NAME}** hoon — InfraForge ka construction & equipment assistant. "
            f"Machine search, compare, equipment guide, aur rent/buy booking me help karta hoon."
        ),
    )


async def build_knowledge_answer(
    turn: dict[str, Any],
    *,
    user_message: str,
    lang: str = "english",
) -> dict[str, Any]:
    """Build a direct answer draft — LLM enriches when enabled."""
    kind = turn.get("kind") or "domain_definition"
    if kind == "assistant_identity":
        draft = _local_identity_draft(lang)
        goal = "assistant_identity"
    elif kind == "memory_question":
        from app.ai.response_mode_gateway import build_memory_answer_draft
        from app.ai.semantic_turn_gateway import SemanticTurnUnderstanding

        u = SemanticTurnUnderstanding(
            context_reference={"user_name": turn.get("user_name")},
        )
        tool = await build_memory_answer_draft(u, lang=lang)
        return {
            "message": tool["message"],
            "response_goal": tool["response_goal"],
            "assistant_mode": tool["assistant_mode"],
            "suggestions": tool.get("suggestions") or [],
        }
    elif kind == "machine_specification":
        from app.ai.machine_spec_service import build_machine_spec_draft

        draft = build_machine_spec_draft(turn, lang=lang)
        goal = "domain_knowledge_answer"
    elif kind == "machine_advisory":
        from app.ai.machine_spec_service import build_machine_advisory_draft

        draft = build_machine_advisory_draft(turn, lang=lang)
        goal = "domain_knowledge_answer"
    else:
        subject = turn.get("subject") or "this"
        subject_type = turn.get("subject_type") or "concept"
        draft = _local_definition_draft(
            subject=subject,
            subject_type=subject_type,
            lang=lang,
        )
        goal = "domain_knowledge_answer"

    from app.core.config import settings

    if settings.use_llm_response_generation and settings.GROQ_API_KEY:
        try:
            from app.core.groq_client import groq_chat_completion
            from app.ai.capability_registry import capability_summary_for_prompt

            system = (
                "You are InfraForge AI — a construction and heavy-equipment marketplace assistant for India. "
                "Answer the user's question directly and helpfully in 2-4 short paragraphs max. "
                "RULES: Do NOT invent live listing prices, availability, owner contacts, or booking status. "
                "You MAY use well-known public manufacturer specifications (engine HP/kW, operating weight, "
                "bucket/drum capacity, fuel type, typical applications, fuel consumption ranges) for construction equipment. "
                "If exact variant is unclear, give typical range and note it may vary by year/variant. "
                "Match user language (English/Hindi/Hinglish). Be specific — answer what they asked."
            )
            subject = turn.get("display_name") or turn.get("subject") or "assistant"
            user_block = (
                f"User question: {user_message}\n"
                f"Knowledge kind: {kind}\n"
                f"Machine/Subject: {subject}\n"
                f"Brand: {turn.get('brand') or 'unknown'}\n"
                f"Model: {turn.get('model') or 'unknown'}\n"
                f"Category: {turn.get('category') or 'unknown'}\n"
                f"Draft facts (use as base, enrich with public manufacturer knowledge): {draft}\n"
                f"Capabilities: {capability_summary_for_prompt()}"
            )
            resp = groq_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_block},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.35,
                tag="knowledge_query",
            )
            if resp:
                text = (resp.choices[0].message.content or "").strip()
                if text and len(text) > 30:
                    draft = text
        except Exception as exc:
            print(f"[knowledge_query] llm_failed: {exc}")

    if kind == "assistant_identity":
        suggestions = ["Search Machine", "Compare machines", "Contact support"]
    elif kind == "machine_specification":
        suggestions = ["Search this machine", "Compare brands", "Ask recommendation"]
    elif kind == "machine_advisory":
        suggestions = ["Compare brands", "Search this machine", "Ask recommendation"]
    else:
        suggestions = ["Search this machine", "Compare brands", "Ask recommendation"]
    return {
        "message": draft,
        "assistant_mode": "advisory" if kind != "assistant_identity" else "conversational",
        "response_goal": goal,
        "suggestions": suggestions,
        "preserve_machines": True,
    }
