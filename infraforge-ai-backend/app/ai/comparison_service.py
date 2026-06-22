from __future__ import annotations

from typing import Any, Optional

from app.utils.machine_normalizer import (
    effective_price,
    format_price_label,
    listing_type_label,
    normalize_listing_type_stored,
    rating_score_neutral,
)

_SPEC_FIELDS = (
    ("listing_type", "Listing", lambda m: listing_type_label(m.get("listing_type"))),
    ("price", "Price", format_price_label),
    ("rating", "Rating", lambda m: f"{m.get('rating')}/5" if m.get("rating") is not None else "N/A"),
    ("city", "City", lambda m: str(m.get("city") or "—").title()),
    ("availability_status", "Availability", lambda m: m.get("availability_status") or m.get("availability") or "—"),
    ("brand", "Brand", lambda m: m.get("brand") or "—"),
    ("model", "Model", lambda m: m.get("model") or "—"),
    ("year", "Year", lambda m: (m.get("specifications") or {}).get("manufacturing_year") or "—"),
    ("condition", "Condition", lambda m: (m.get("specifications") or {}).get("condition") or "—"),
    ("engine_power", "Engine power", lambda m: (m.get("specifications") or {}).get("engine_power") or "—"),
    ("operating_weight", "Weight", lambda m: (m.get("specifications") or {}).get("operating_weight") or "—"),
    ("deposit", "Deposit", lambda m: m.get("security_deposit") or "—"),
)


def _machine_label(machine: dict, fallback: str) -> str:
    return machine.get("name") or machine.get("brand") or fallback


def _compare_row_values(val_a: Any, val_b: Any, *, lower_is_better: bool = False) -> str | None:
    if val_a == val_b or val_a in ("—", "N/A", None) or val_b in ("—", "N/A", None):
        return None
    if lower_is_better:
        try:
            na = float(str(val_a).replace("₹", "").replace(",", "").split("/")[0].strip())
            nb = float(str(val_b).replace("₹", "").replace(",", "").split("/")[0].strip())
            if na < nb:
                return "a"
            if nb < na:
                return "b"
        except (TypeError, ValueError):
            pass
    try:
        na = float(val_a)
        nb = float(val_b)
        if na > nb:
            return "a"
        if nb > na:
            return "b"
    except (TypeError, ValueError):
        pass
    return None


def build_comparison_table(machine1: dict, machine2: dict) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label, fn in _SPEC_FIELDS:
        val_a = fn(machine1)
        val_b = fn(machine2)
        winner = None
        if key == "price":
            p1 = effective_price(machine1)
            p2 = effective_price(machine2)
            if p1 is not None and p2 is not None:
                winner = "a" if p1 < p2 else ("b" if p2 < p1 else None)
        elif key == "rating":
            r1 = machine1.get("rating")
            r2 = machine2.get("rating")
            if r1 is not None and r2 is not None:
                winner = "a" if r1 > r2 else ("b" if r2 > r1 else None)
        rows.append({
            "key": key,
            "label": label,
            "a": val_a,
            "b": val_b,
            "winner": winner,
        })
    return rows


def _summary_draft(machine1: dict, machine2: dict, comparison: dict) -> str:
    n1 = _machine_label(machine1, "Option 1")
    n2 = _machine_label(machine2, "Option 2")
    lt1 = normalize_listing_type_stored(machine1.get("listing_type"))
    lt2 = normalize_listing_type_stored(machine2.get("listing_type"))
    cross_type = lt1 != lt2

    lines = [
        f"Comparing {n1} vs {n2}.",
    ]
    if cross_type:
        lines.append(
            "Note: one listing is for rent and the other for purchase — compare on suitability, not raw price alone."
        )
    lines.append(f"Better for budget: {comparison.get('better_for_budget')}.")
    lines.append(f"Better rating: {comparison.get('better_rating')}.")
    lines.append(f"Overall pick: {comparison.get('overall_recommendation')}.")
    avail1 = machine1.get("availability_status") or machine1.get("availability")
    avail2 = machine2.get("availability_status") or machine2.get("availability")
    if avail1 == "available" and avail2 != "available":
        lines.append(f"{n1} is available now — strong for immediate deployment.")
    elif avail2 == "available" and avail1 != "available":
        lines.append(f"{n2} is available now — strong for immediate deployment.")
    return " ".join(lines)


def compare_machines(machine1, machine2):
    comparison: dict[str, Any] = {}

    price1 = effective_price(machine1) or 0
    price2 = effective_price(machine2) or 0
    rating1 = rating_score_neutral(machine1)
    rating2 = rating_score_neutral(machine2)
    lt1 = normalize_listing_type_stored(machine1.get("listing_type"))
    lt2 = normalize_listing_type_stored(machine2.get("listing_type"))
    cross_type = lt1 != lt2

    if cross_type:
        comparison["better_for_budget"] = "Compare rent vs buy separately — different listing types"
    elif price1 < price2:
        comparison["better_for_budget"] = machine1.get("name", "Machine 1")
    else:
        comparison["better_for_budget"] = machine2.get("name", "Machine 2")

    if (machine1.get("rating") or 0) > (machine2.get("rating") or 0):
        comparison["better_rating"] = machine1.get("name", "Machine 1")
    elif (machine2.get("rating") or 0) > (machine1.get("rating") or 0):
        comparison["better_rating"] = machine2.get("name", "Machine 2")
    else:
        comparison["better_rating"] = "Similar — rating not available or equal"

    score1 = rating1 * 0.5 + (1 if machine1.get("availability") else 0) * 0.2
    score2 = rating2 * 0.5 + (1 if machine2.get("availability") else 0) * 0.2
    if not cross_type:
        score1 -= price1 * 0.00005
        score2 -= price2 * 0.00005

    comparison["overall_recommendation"] = (
        machine1.get("name", "Machine 1")
        if score1 >= score2
        else machine2.get("name", "Machine 2")
    )
    comparison["value_for_money"] = comparison["better_for_budget"] if not cross_type else "Depends on rent vs buy goal"
    comparison["cross_type_warning"] = cross_type
    comparison["comparison_rows"] = build_comparison_table(machine1, machine2)
    comparison["summary_draft"] = _summary_draft(machine1, machine2, comparison)
    comparison["machine_1"] = machine1
    comparison["machine_2"] = machine2
    return comparison


async def generate_comparison_summary(
    machine1: dict,
    machine2: dict,
    comparison: dict,
    *,
    lang: str = "english",
    user_context: str = "",
) -> str:
    """Optional LLM narrative — falls back to summary_draft."""
    draft = comparison.get("summary_draft") or _summary_draft(machine1, machine2, comparison)
    try:
        from app.core.config import settings
        if not settings.GROQ_API_KEY:
            return draft
        from app.core.groq_client import groq_chat_completion

        rows = comparison.get("comparison_rows") or []
        table_text = "\n".join(
            f"{r['label']}: {r['a']} | {r['b']}" for r in rows[:12]
        )
        system = (
            "You are InfraForge's construction equipment advisor. "
            "Write a concise comparison (4-6 sentences): specs table insights, "
            "which is better for budget, value for money, and which suits typical site work. "
            "Use ONLY facts from the table. Do not invent availability or prices."
        )
        user = (
            f"Language: {lang}\n"
            f"User context: {user_context or 'general comparison'}\n"
            f"Table:\n{table_text}\n"
            f"Draft: {draft}"
        )
        reply = groq_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=280,
            temperature=0.4,
        )
        text = (reply or "").strip()
        return text or draft
    except Exception:
        return draft
