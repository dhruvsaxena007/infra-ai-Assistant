"""
Assistant response builders + universal turn adapter.

Classification lives in universal_turn_engine.py (one engine, all shapes).
This module builds human responses for each shape.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.category_mapping import category_label
from app.ai.comparison_service import compare_machines, generate_comparison_summary
from app.ai.universal_turn_engine import (
    analyze_universal_turn,
    detect_comparison_turn,
    detect_conversational_turn,
    detect_machine_detail_turn,
    extract_user_name,
)
from app.utils.machine_normalizer import format_price_label
from app.utils.machine_repository import search_by_filters


def _machine_price_value(machine: dict) -> float:
    for key in ("price_per_day", "selling_price", "rental_price"):
        val = machine.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return float("inf")

_SPEC_LABELS = {
    "manufacturing_year": "Year",
    "condition": "Condition",
    "fuel_type": "Fuel type",
    "transmission": "Transmission",
    "bucket_capacity": "Bucket capacity",
    "engine_power": "Engine power",
    "operating_weight": "Operating weight",
    "lifting_capacity": "Lifting capacity",
    "max_digging_depth": "Max digging depth",
    "working_hours": "Working hours",
    "drive_type": "Drive type",
    "capacity": "Capacity",
    "variant": "Variant",
    "pincode": "Pincode",
}


def classify_universal_turn(
    message: str,
    *,
    session_ctx: dict | None = None,
    result_ctx: dict | None = None,
    last_filters: dict | None = None,
    greeted: bool = False,
) -> dict[str, Any]:
    """Sync rules-only — prefer classify_universal_turn_async in router."""
    from app.ai.universal_turn_engine import analyze_universal_turn

    return analyze_universal_turn(
        message,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
        last_filters=last_filters,
        greeted=greeted,
    )


async def classify_universal_turn_async(
    message: str,
    *,
    session_ctx: dict | None = None,
    result_ctx: dict | None = None,
    last_filters: dict | None = None,
    greeted: bool = False,
) -> dict[str, Any]:
    """Universal entry — rules + Groq semantic for any phrasing."""
    from app.ai.universal_turn_engine import analyze_universal_turn_async

    return await analyze_universal_turn_async(
        message,
        session_ctx=session_ctx,
        result_ctx=result_ctx,
        last_filters=last_filters,
        greeted=greeted,
    )


def sanitize_display_name(name: str | None) -> str | None:
    """Drop placeholder / serialized null names from API or DB."""
    if name is None:
        return None
    s = str(name).strip()
    if not s or s.lower() in ("null", "none", "undefined", "nan", "n/a"):
        return None
    return s


def build_conversational_response(
    turn: dict,
    *,
    lang: str = "english",
) -> dict[str, Any]:
    subtype = turn.get("subtype")
    name = sanitize_display_name(turn.get("user_name") or turn.get("save_user_name"))

    if subtype == "greeting":
        from app.chatbot.assistant_intelligence import greeting_message

        first_time = not bool(turn.get("greeted"))
        msg = greeting_message(first_time=first_time, lang=lang)
        return {
            "message": msg,
            "assistant_mode": "greeting",
            "suggestions": ["Search machine", "Compare machines", "Contact support"],
        }

    if subtype == "thanks":
        msg = (
            "You're welcome! I can help with machine search, comparison, specs, "
            "booking, or support — just ask."
        )
        if lang == "hinglish":
            msg = "Welcome! Search, compare, specs, booking ya support — bataiye."
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Search machine", "Compare machines", "Contact support"],
        }

    if subtype in ("appreciation", "satisfaction", "flow_ack"):
        from app.ai.social_turn_detector import build_social_response_draft
        return build_social_response_draft(
            {**turn, "kind": subtype, "subtype": subtype},
            lang=lang,
            user_name=name,
        )

    if subtype == "assistant_identity":
        from app.ai.knowledge_query_engine import _local_identity_draft

        msg = _local_identity_draft(lang)
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Search machine", "Compare machines", "Contact support"],
        }

    if subtype == "name_intro":
        intro_name = name or sanitize_display_name(extract_user_name(turn.get("original_message", "")))
        if intro_name:
            msg = (
                f"Nice to meet you, {intro_name}. How can I help you with InfraForge today?"
            )
            if lang == "hinglish":
                msg = (
                    f"Nice to meet you, {intro_name}. Aaj main InfraForge me "
                    f"machine search, compare, rent/buy ya support me kaise madad kar sakta hoon?"
                )
            return {
                "message": msg,
                "assistant_mode": "conversational",
                "suggestions": ["Search Machine", "Ask recommendation", "Contact support"],
                "save_user_name": intro_name,
            }

    if subtype == "polite_social":
        greet = f", {name}" if name else ""
        msg = (
            f"Likewise{greet}. Whenever you're ready, I can help you search machines, "
            f"compare options, or handle booking and support questions."
        )
        if lang == "hinglish":
            msg = (
                f"Likewise{greet}. Jab ready hon, main machine search, compare, "
                f"booking ya support me madad kar sakta hoon."
            )
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Search Machine", "Ask recommendation", "Contact support"],
        }

    if subtype == "wellbeing_reciprocal":
        greet = f", {name}" if name else ""
        original = (turn.get("original_message") or "").lower()
        user_shared_state = bool(
            re.search(r"\b(?:i(?:'m|\s+am)?|im\b|main\b|mai\b)\b", original, re.I)
            and re.search(r"\b(?:fine|good|well|ok|okay|great|theek|thik)\b", original, re.I)
        )
        if user_shared_state:
            msg = (
                f"Glad you're doing well{greet}! I'm good too — ready to help with "
                f"machines, comparisons, specs, or anything on InfraForge."
            )
        else:
            msg = (
                f"I'm doing well{greet}, thank you! I can help you search machines, "
                f"compare brands, check specs, or handle booking/support questions."
            )
        if lang == "hinglish":
            if user_shared_state:
                msg = (
                    f"Achha hai{greet}! Main bhi theek hoon — machine search, compare, "
                    f"specs ya support me bataiye."
                )
            else:
                msg = (
                    f"Main theek hoon{greet}, shukriya! Machine search, compare, specs "
                    f"ya support — bataiye."
                )
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Search machine", "Ask recommendation", "Contact support"],
        }

    if subtype == "user_state":
        greet = f", {name}" if name else ""
        msg = (
            f"Good to hear{greet}! Whenever you're ready, tell me what machine or "
            f"help you need on InfraForge."
        )
        if lang == "hinglish":
            msg = f"Achha hai{greet}! Jab ready hon, machine ya help bata dena."
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Search machine", "Road project machines"],
        }

    if subtype in ("wellbeing", None):
        greet = f", {name}" if name else ""
        msg = (
            f"I'm doing well{greet}, thank you! I can help you search machines, "
            f"compare brands, check specs, or handle booking/support questions."
        )
        if lang == "hinglish":
            msg = (
                f"Main theek hoon{greet}, shukriya! Machine search, compare, specs "
                f"ya support — bataiye."
            )
        return {
            "message": msg,
            "assistant_mode": "conversational",
            "suggestions": ["Search machine", "Compare machines", "Contact support"],
        }

    return {
        "message": "How can I help you with InfraForge marketplace today?",
        "assistant_mode": "conversational",
        "suggestions": ["Search machine", "Contact support"],
    }


def _format_specs(machine: dict) -> list[str]:
    lines: list[str] = []
    specs = machine.get("specifications") or {}
    for key, label in _SPEC_LABELS.items():
        val = specs.get(key)
        if val is not None and str(val).strip():
            lines.append(f"• {label}: {val}")

    if machine.get("brand"):
        lines.insert(0, f"• Brand: {machine['brand']}")
    if machine.get("model"):
        lines.insert(1 if machine.get("brand") else 0, f"• Model: {machine['model']}")
    if machine.get("category_display") or machine.get("category"):
        cat = machine.get("category_display") or category_label(machine.get("category"))
        lines.insert(0, f"• Category: {cat}")
    lines.append(f"• Price: {format_price_label(machine)}")
    if machine.get("city"):
        lines.append(f"• City: {str(machine['city']).title()}")
    if machine.get("rating") is not None:
        lines.append(f"• Rating: {machine['rating']}/5")
    if machine.get("description"):
        desc = str(machine["description"]).strip()
        if len(desc) > 10:
            lines.append(f"• Description: {desc[:280]}{'…' if len(desc) > 280 else ''}")
    return lines


def _fuel_answer(machine: dict, lang: str) -> str:
    specs = machine.get("specifications") or {}
    fuel = specs.get("fuel_type") or "Not listed in this listing"
    name = machine.get("name") or "This machine"
    engine = specs.get("engine_power")
    weight = specs.get("operating_weight")

    if lang == "hinglish":
        base = (
            f"{name} ke liye fuel type: {fuel}. Exact consumption listing me nahi hai — "
            f"owner se confirm karein."
        )
    else:
        base = (
            f"For {name}, fuel type listed: {fuel}. Exact consumption is not in this listing — "
            f"depends on site work and load. Contact the owner for real figures."
        )
    extras = []
    if engine:
        extras.append(f"Engine power: {engine}")
    if weight:
        extras.append(f"Operating weight: {weight}")
    if extras:
        base += " " + " | ".join(extras) + "."
    return base


def build_machine_detail_response(
    turn: dict,
    *,
    lang: str = "english",
) -> dict[str, Any]:
    if turn.get("subtype") == "need_reference":
        msg = (
            "Which machine do you mean? Search first, or name the machine "
            "(e.g. 'specs of JCB VM 117')."
        )
        if lang == "hinglish":
            msg = "Kaunsi machine? Pehle search karein ya naam likhein."
        return {
            "message": msg,
            "assistant_mode": "clarification",
            "suggestions": ["Excavator in Delhi", "Road roller in Jaipur"],
        }

    machine = turn.get("machine") or {}
    name = machine.get("name") or "This machine"

    if turn.get("subtype") == "fuel":
        return {
            "message": _fuel_answer(machine, lang),
            "assistant_mode": "machine_detail",
            "suggestions": ["Contact owner", "Compare similar", "Cheaper options"],
            "preserve_machines": True,
        }

    lines = _format_specs(machine)
    if not lines:
        msg = (
            f"Detailed specs for {name} aren't fully listed. "
            f"Check the machine card or contact the owner."
        )
    else:
        msg = f"Details for {name}:\n\n" + "\n".join(lines)

    return {
        "message": msg,
        "assistant_mode": "machine_detail",
        "suggestions": ["Compare similar", "Contact owner", "Cheaper options"],
        "preserve_machines": True,
    }


async def _resolve_comparison_listing(
    database,
    *,
    brand: str,
    category: Optional[str],
    city: Optional[str],
    model_hint: Optional[str] = None,
) -> Optional[dict]:
    """Best-effort listing for one side of a comparison."""
    searches: list[dict] = []
    if model_hint:
        searches.append({"category": category, "city": city, "brand": brand, "model": model_hint, "exact": False})
    if category:
        searches.append({"category": category, "city": city, "brand": brand, "exact": True})
    searches.append({"category": category, "city": city, "brand": brand, "exact": False})
    searches.append({"brand": brand, "exact": False})

    seen: set[str] = set()
    candidates: list[dict] = []
    for spec in searches:
        key = "|".join(str(spec.get(k) or "") for k in ("category", "city", "brand", "model", "exact"))
        if key in seen:
            continue
        seen.add(key)
        raw = await search_by_filters(
            database,
            category=spec.get("category"),
            city=spec.get("city"),
            brand=spec.get("brand"),
            model=spec.get("model"),
            limit=5,
            exact_category=bool(spec.get("exact")),
        )
        candidates.extend(raw or [])

    if not candidates:
        return None

    if model_hint:
        hint = model_hint.lower().replace(" ", "")
        for machine in candidates:
            blob = " ".join(
                str(machine.get(k) or "")
                for k in ("name", "model", "brand")
            ).lower().replace(" ", "")
            if hint in blob:
                return machine

    return candidates[0]


_MODEL_TOKEN_RE = re.compile(r"\b[a-z]{0,4}\d{2,}[a-z0-9]*\b", re.I)


def _extract_model_hints(message: str, brands: list[str]) -> dict[str, str]:
    """Map brand → model token using message proximity (generalized, not example-specific)."""
    text = (message or "").strip()
    if not text or not brands:
        return {}

    lower = text.lower()
    brand_positions: list[tuple[int, str]] = []
    for brand in brands:
        for match in re.finditer(re.escape(brand.lower()), lower):
            brand_positions.append((match.start(), brand))

    hints: dict[str, str] = {}
    for token in _MODEL_TOKEN_RE.findall(text):
        tok = token.strip()
        if len(tok) < 3:
            continue
        pos = lower.find(tok.lower())
        if pos < 0:
            continue
        nearest: Optional[str] = None
        nearest_dist = 10**9
        for bpos, brand in brand_positions:
            dist = abs(pos - bpos)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = brand
        if nearest and nearest not in hints:
            hints[nearest] = tok
    return hints


async def build_comparison_response(
    database,
    turn: dict,
    *,
    city: Optional[str] = None,
    lang: str = "english",
) -> dict[str, Any]:
    from app.ai.brand_comparison_advisory import (
        build_brand_advisory_comparison,
        is_brand_advisory_comparison,
    )

    brands = turn.get("brands") or []
    category = turn.get("category")
    user_message = turn.get("original_message") or turn.get("normalized_message") or ""
    model_hints = _extract_model_hints(user_message, brands)

    if turn.get("needs_clarification") and len(brands) < 2:
        msg = (
            "I can compare in chat — tell me two brands/models and machine type "
            "(e.g. 'JCB vs CAT road roller')."
        )
        return {
            "message": msg,
            "assistant_mode": "clarification",
            "suggestions": ["JCB vs CAT road roller", "Compare excavators in Mumbai"],
        }

    compare_brands = brands[:2] if len(brands) >= 2 else (
        [brands[0], "CAT"] if brands and brands[0] != "CAT" else ["JCB", "CAT"]
    )

    # General brand comparison — table + summary from domain knowledge (not inventory search)
    if is_brand_advisory_comparison(user_message, parsed={"brands": brands, "category": category}):
        return await build_brand_advisory_comparison(
            brands=compare_brands,
            category=category,
            user_message=user_message,
            lang=lang,
        )

    results: list[dict] = []

    for brand in compare_brands:
        machine = await _resolve_comparison_listing(
            database,
            brand=brand,
            category=category,
            city=city,
            model_hint=model_hints.get(brand),
        )
        if machine:
            results.append(machine)

    if len(results) >= 2:
        return await _comparison_message(
            results[0],
            results[1],
            category,
            lang,
            user_context=user_message,
        )

    # Partial/no listings — fall back to brand advisory instead of search substitution
    if len(compare_brands) >= 2 and category:
        return await build_brand_advisory_comparison(
            brands=compare_brands,
            category=category,
            user_message=user_message,
            lang=lang,
        )

    from app.ai.no_result_recovery import run_comparison_recovery

    recovery = await run_comparison_recovery(
        database,
        brands=compare_brands,
        category=category,
        city=city,
        results=results,
        lang=lang,
    )
    missing = (recovery.get("message_facts") or {}).get("missing_brands") or []
    cat_label = category_label(category) if category else "machines"
    if missing:
        miss_txt = " and ".join(missing)
        msg = (
            f"Could not find listings for {miss_txt} to compare"
            f"{f' in {city.title()}' if city else ''}. "
            "Try available brands or another city."
        )
    else:
        msg = (
            f"Couldn't find two {cat_label} listings to compare"
            f"{f' in {city.title()}' if city else ''}. Try another city or use Compare on cards."
        )
    return {
        "message": msg,
        "assistant_mode": "comparison",
        "machines": results,
        "suggestions": recovery.get("suggestions") or [f"{cat_label} in Jaipur", "Search machine"],
        "recovery_type": recovery.get("recovery_type"),
        "no_result_recovery": {
            "recovery_type": recovery.get("recovery_type"),
            "safe_alternatives": recovery.get("safe_alternatives"),
            "suggestions": recovery.get("suggestions"),
            "next_best_action": recovery.get("next_best_action"),
        },
    }


async def _comparison_message(
    m1: dict,
    m2: dict,
    category: Optional[str],
    lang: str,
    *,
    user_context: str = "",
) -> dict:
    cmp = compare_machines(m1, m2)
    cat_label = category_label(category) if category else "machines"
    n1, n2 = m1.get("name", "Option 1"), m2.get("name", "Option 2")
    rows = cmp.get("comparison_rows") or []

    llm_summary = await generate_comparison_summary(
        m1,
        m2,
        cmp,
        lang=lang,
        user_context=user_context,
    )
    cmp["llm_summary"] = llm_summary

    table_lines = [f"| {r['label']} | {r['a']} | {r['b']} |" for r in rows[:10]]
    header = f"| Spec | {n1} | {n2} |"
    divider = "| --- | --- | --- |"
    table_md = "\n".join([header, divider, *table_lines]) if table_lines else ""

    intro = f"**{cat_label.title()} comparison — {m1.get('brand', '')} vs {m2.get('brand', '')}**"
    msg = intro
    if table_md:
        msg += f"\n\n{table_md}"
    if llm_summary:
        msg += f"\n\n{llm_summary}"

    return {
        "message": msg,
        "assistant_mode": "comparison",
        "machines": [m1, m2],
        "comparison": cmp,
        "comparison_rows": rows,
        "llm_summary": llm_summary,
        "better_for_budget": cmp.get("better_for_budget"),
        "better_rating": cmp.get("better_rating"),
        "overall_recommendation": cmp.get("overall_recommendation"),
        "value_for_money": cmp.get("value_for_money"),
        "suggestions": ["Contact owner", "Show cheaper options", "Show buy options"],
    }


async def build_contextual_refine_response(
    database,
    turn: dict,
    *,
    result_ctx: dict,
    lang: str = "english",
) -> dict[str, Any]:
    """Handle chip follow-ups: cheaper options, compare similar — uses session context."""
    action = turn.get("action")
    ref = turn.get("machine") or result_ctx.get("top_machine") or {}
    filters = turn.get("filters") or {}

    category = filters.get("category") or ref.get("category")
    city = filters.get("city") or ref.get("city")
    max_price = filters.get("max_price")
    ref_price = _machine_price_value(ref) if ref else float("inf")

    if action == "cheaper_options":
        new_max = None
        if max_price:
            new_max = int(float(max_price) * 0.75)
        elif ref_price != float("inf"):
            new_max = int(ref_price * 0.9)

        raw = await search_by_filters(
            database,
            category=category,
            city=city,
            brand=filters.get("brand"),
            max_price=new_max,
            listing_type=filters.get("listing_type"),
            limit=8,
            exact_category=bool(category),
        )
        ref_id = str(ref.get("id") or "")
        cheaper = [
            m for m in raw
            if str(m.get("_id") or m.get("id") or "") != ref_id
            and _machine_price_value(m) < ref_price
        ]
        cheaper.sort(key=_machine_price_value)

        if not cheaper and raw:
            cheaper = sorted(raw, key=_machine_price_value)[:3]

        if cheaper:
            lines = []
            for i, m in enumerate(cheaper[:3], 1):
                lines.append(
                    f"{i}. {m.get('name', 'Machine')} — {format_price_label(m)}, "
                    f"{str(m.get('city', '—')).title()}"
                )
            budget_note = f" under ₹{new_max}" if new_max else ""
            msg = (
                f"Lower-priced options for {category_label(category) or 'similar machines'}"
                f"{f' in {str(city).title()}' if city else ''}{budget_note}:\n\n"
                + "\n".join(lines)
            )
            if lang == "hinglish":
                msg = (
                    f"Saste options {category_label(category) or 'similar'}{budget_note}:\n\n"
                    + "\n".join(lines)
                )
            return {
                "message": msg,
                "assistant_mode": "cheaper_options",
                "machines": cheaper[:5],
                "suggestions": ["Contact owner", "Compare similar", "Search machine"],
            }

        msg = (
            "I couldn't find cheaper listings with your current filters. "
            "Try a higher budget range or another city."
        )
        if lang == "hinglish":
            msg = "Is budget/city ke saath sasta option nahi mila. Budget badha ke ya city change karke try karein."

        from app.ai.no_result_recovery import run_no_result_recovery

        recovery = await run_no_result_recovery(
            database,
            intent="cheaper_option_query",
            selected_action="cheaper_options",
            filters={
                "category": category,
                "city": city,
                "max_price": new_max,
                "listing_type": filters.get("listing_type"),
                "brand": filters.get("brand"),
            },
            tool_result={"fallback_reason": "no_cheaper_options"},
            permission_decision={
                "permission_passed": True,
                "allowed_tool": "mongodb_search",
                "should_search_machines": True,
            },
            lang=lang,
        )
        suggestions = recovery.get("suggestions") or ["Search machine", "Contact support"]
        draft = msg
        min_alt = next(
            (a for a in (recovery.get("safe_alternatives") or []) if a.get("type") == "budget_relaxation"),
            None,
        )
        if min_alt and min_alt.get("min_available_price"):
            draft += f" Lowest available is around ₹{int(min_alt['min_available_price'])}."
        return {
            "message": draft,
            "assistant_mode": "cheaper_options",
            "machines": result_ctx.get("last_machines") or [],
            "preserve_machines": True,
            "suggestions": suggestions,
            "recovery_type": recovery.get("recovery_type"),
            "no_result_recovery": {
                "recovery_type": recovery.get("recovery_type"),
                "safe_alternatives": recovery.get("safe_alternatives"),
                "suggestions": suggestions,
                "next_best_action": recovery.get("next_best_action"),
            },
        }

    if action == "compare_similar":
        if not ref:
            msg = "Search a machine first, then I can compare similar options."
            return {
                "message": msg,
                "assistant_mode": "clarification",
                "suggestions": ["Excavator in Jaipur", "Road roller in Delhi"],
            }

        cat = ref.get("category") or category
        ref_brand = ref.get("brand")
        alt_raw = await search_by_filters(
            database,
            category=cat,
            city=city or ref.get("city"),
            limit=5,
            exact_category=bool(cat),
        )
        alt = None
        for m in alt_raw:
            if (m.get("brand") or "").lower() != (ref_brand or "").lower():
                alt = m
                break
        if not alt and len(alt_raw) > 1:
            alt = alt_raw[1]

        if alt:
            return _comparison_message(ref, alt, cat, lang)

        msg = "No similar machine found to compare right now. Try another city or category."
        return {
            "message": msg,
            "assistant_mode": "comparison",
            "machines": [ref] if ref else [],
            "preserve_machines": True,
            "suggestions": ["Search machine", "Cheaper options"],
        }

    if action == "contact_owner":
        from app.ai.selected_machine_context import build_selected_machine_response

        return build_selected_machine_response(
            machine=ref or {},
            action="contact_owner",
            lang=lang,
        )

    return {
        "message": "Tell me what you'd like — cheaper options, compare similar, or a new search.",
        "assistant_mode": "clarification",
        "suggestions": ["Cheaper options", "Compare similar", "Search machine"],
    }
