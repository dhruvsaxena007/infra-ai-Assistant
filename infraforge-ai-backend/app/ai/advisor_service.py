"""
Machine advisor — rules-first ranking; Groq only when USE_GROQ_ADVISOR=true.
"""

from __future__ import annotations

from app.ai.category_mapping import category_label
from app.core.config import settings
from app.core.groq_client import groq_chat_completion
from app.utils.machine_normalizer import (
    effective_price,
    format_price_label,
    rating_score_neutral,
)


def _machine_summary(machine: dict) -> str:
    specs = machine.get("specifications") or {}
    rating = machine.get("rating")
    rating_text = f"{rating}/5" if rating is not None else "not available"
    return (
        f"Name: {machine.get('name')}\n"
        f"Category: {machine.get('category_display') or machine.get('category')}\n"
        f"Brand/Model: {machine.get('brand')} {machine.get('model')}\n"
        f"City: {machine.get('city')}\n"
        f"Price: {format_price_label(machine)}\n"
        f"Listing: {machine.get('listing_type')} ({machine.get('rent_type') or 'n/a'})\n"
        f"Availability: {machine.get('availability_status')}\n"
        f"Condition/Year: {specs.get('condition')} / {specs.get('manufacturing_year')}\n"
        f"Rating: {rating_text}\n"
    )


def _advisor_rank_score(machine: dict) -> float:
    """Higher = better recommendation."""
    score = 0.0
    if machine.get("availability"):
        score += 30.0
    score += rating_score_neutral(machine) * 25.0

    price = effective_price(machine)
    if price is not None and price > 0:
        score += max(0.0, 20.0 - min(price / 500.0, 20.0))

    specs = machine.get("specifications") or {}
    condition = str(specs.get("condition") or "").lower()
    if condition == "new":
        score += 8.0
    elif condition == "used":
        score += 3.0

    if machine.get("security_deposit") is not None:
        try:
            if float(machine["security_deposit"]) <= 500:
                score += 2.0
        except (TypeError, ValueError):
            pass

    return score


def _deterministic_advice(user_query: str, machines: list) -> str:
    ranked = sorted(machines, key=_advisor_rank_score, reverse=True)
    best = ranked[0]
    specs = best.get("specifications") or {}
    rating = best.get("rating")
    rating_note = (
        f"rating {rating}/5"
        if rating is not None
        else "rating not available"
    )

    lines = [
        (
            f"Best match: {best.get('name')} "
            f"({best.get('category_display') or best.get('category')}) "
            f"in {str(best.get('city', '')).title()} — {format_price_label(best)}, "
            f"{best.get('availability_status')}, "
            f"{specs.get('condition') or 'condition n/a'} "
            f"{specs.get('manufacturing_year') or ''}, {rating_note}."
        )
    ]

    if len(ranked) > 1:
        alt = ranked[1]
        lines.append(
            f"Alternative: {alt.get('name')} at {format_price_label(alt)} "
            f"in {str(alt.get('city', '')).title()}."
        )

    if "jcb" in user_query.lower() or "backhoe" in user_query.lower():
        lines.append("Note: JCB / backhoe loader is not an excavator — compare loader class only.")

    lines.append(
        "Compare availability, condition, manufacturing year, and deposit before booking."
    )
    return " ".join(lines)


def _groq_advice(user_query: str, machines: list) -> str:
    machine_text = ""
    for index, machine in enumerate(machines[:5], start=1):
        machine_text += f"\nMachine {index}:\n{_machine_summary(machine)}\n"

    prompt = f"""
You are an AI advisor for the Infra AI-Assistant for Marketplace construction equipment platform.

User requirement:
{user_query}

These machines are CONFIRMED matches. Do not invent machines or prices.
If rating is "not available", do not assume a high rating.

Available machines:
{machine_text}

Rules:
- Use category_display/category exactly as shown.
- Never call a JCB / backhoe loader an excavator.
- Recommend the best machine using price, availability, condition, year, city.
- Keep the answer short and practical.
"""
    response = groq_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        tag="advisor",
    )
    if not response or not response.choices:
        raise RuntimeError("Groq advisor unavailable")
    return response.choices[0].message.content.strip()


def generate_machine_advice(
    user_query: str,
    machines: list,
    exact_match_found: bool = True,
    requested_category=None,
):
    if not machines:
        return {"success": False, "message": "No matching machines found"}

    if not exact_match_found:
        label = (
            category_label(requested_category)
            if requested_category
            else "the exact machine"
        )
        return {
            "success": True,
            "advice": (
                f"I could not find the exact requested {label}. The machines shown "
                "are the closest alternatives — compare price, availability, condition, "
                "year, and city before deciding."
            ),
            "source": "rules",
        }

    advice = _deterministic_advice(user_query, machines)
    source = "rules"

    if settings.USE_GROQ_ADVISOR and len(machines) >= 3:
        try:
            advice = _groq_advice(user_query, machines)
            source = "groq"
        except Exception as exc:
            print(f"[advisor_service] Groq advice failed, using rules: {exc}")

    return {"success": True, "advice": advice, "source": source}
