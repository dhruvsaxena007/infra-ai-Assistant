"""
Premium assistant copy, suggestion chips, and guided handover prompts.

Extends language.py / support builders — does not change routing.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.category_mapping import category_label
from app.chatbot.assistant_intelligence import _PROJECT_TYPES
from app.chatbot.language import pick_lang

# ---------------------------------------------------------------------------
# Project & search suggestion chips (E8)
# ---------------------------------------------------------------------------

PROJECT_TYPE_CHIPS = [
    "Highway",
    "Urban road",
    "Earthwork",
    "Compaction",
    "Concrete road",
    "Material transport",
    "Lifting / crane work",
]


def search_followup_suggestions(
    *,
    listing_type: Optional[str] = None,
    has_results: bool = True,
) -> list[str]:
    """Next actions after a machine search (E8)."""
    if not has_results:
        return ["Show cheaper options", "Try nearby city", "Contact support"]
    chips = ["Show cheaper options", "Show rent only", "Show buy options", "Contact owner"]
    if listing_type == "rent":
        return ["Show cheaper options", "Show buy options", "Contact owner", "Compare machines"]
    if listing_type == "sell":
        return ["Show rent only", "Show cheaper options", "Contact owner"]
    return chips


def support_action_suggestions(intent: str) -> list[str]:
    """Guided support chips (E5/E8)."""
    base = ["Call", "WhatsApp", "Raise Request"]
    if intent in ("refund_return", "payment_issue", "order_issue"):
        return ["Share order ID", *base]
    if intent == "delivery_logistics":
        return ["Contact support", "Search machine", *base[:2]]
    return base


def no_result_suggestions(
    *,
    nearby_cities: list[str] | None = None,
    similar_categories: list[str] | None = None,
) -> list[str]:
    chips: list[str] = []
    for c in (nearby_cities or [])[:3]:
        chips.append(f"Check {c.title()}")
    for cat in (similar_categories or [])[:2]:
        chips.append(f"{cat} options")
    chips.extend(["Show cheaper options", "Contact support"])
    return chips[:6]


def clarification_suggestions(missing_field: str, *, city: Optional[str] = None) -> list[str]:
    if missing_field == "machine_purpose":
        return [
            "Digging", "Compaction", "Lifting", "Transport", "Loading", "Road work",
        ]
    if missing_field == "city":
        return ["Jaipur", "Delhi", "Mumbai", "Pune"]
    if missing_field == "category" and city:
        return ["Excavator", "JCB / Backhoe Loader", "Road Roller", "Crane"]
    if missing_field == "filters":
        return ["Excavator in Jaipur", "Road roller in Delhi", "Ask About Rental"]
    return ["Excavator", "Road Roller", "Crane", "Dump Truck"]


# ---------------------------------------------------------------------------
# Personality — guided handover (E5)
# ---------------------------------------------------------------------------

def guided_handover_message(intent: str, *, lang: str = "english") -> str:
    """Human handover prompt (E5)."""
    prompts = {
        "refund_return": (
            "I can help with your refund or return. What would you like to do?",
            "Refund/return me main madad kar sakta hoon. Aap kya karna chahenge?",
        ),
        "payment_issue": (
            "I understand — payment issues need quick attention. What would you like to do?",
            "Samajh gaya — payment issue jaldi resolve hona chahiye. Aap kya karna chahenge?",
        ),
        "order_issue": (
            "Let me help with your booking issue. What would you like to do?",
            "Booking issue me main madad kar sakta hoon. Aap kya karna chahenge?",
        ),
        "delivery_logistics": (
            "Delivery and transport depend on machine location and site city. What would you like to do?",
            "Delivery/transport machine location aur site city par depend karta hai. Aap kya karna chahenge?",
        ),
    }
    en, hing = prompts.get(intent, (
        "I can connect you with our support team. What would you like to do?",
        "Main aapko support team se connect kar sakta hoon. Aap kya karna chahenge?",
    ))
    return pick_lang(lang, english=en, hindi=en, hinglish=hing)


def enrich_handover(handover: dict | None, intent: str, *, lang: str = "english") -> dict | None:
    if not handover or not handover.get("enabled"):
        return handover
    out = dict(handover)
    out["message"] = guided_handover_message(intent, lang=lang)
    return out


# ---------------------------------------------------------------------------
# Project recommendation v2 (E3)
# ---------------------------------------------------------------------------

_PROJECT_REASONS = {
    "highway": (
        "Highway projects typically need grading, compaction, excavation, and material transport.",
        "Highway project ke liye Motor Grader, Road Roller, Excavator aur Dump Truck commonly use hote hain.",
    ),
    "urban": (
        "Urban road work focuses on compaction and versatile loaders in tight city sites.",
        "Urban road ke liye Road Roller, Compactor aur Backhoe Loader zyada suitable hain.",
    ),
    "earthwork": (
        "Earthwork needs digging, loading, and hauling capacity on site.",
        "Earthwork ke liye Excavator, Backhoe Loader, Dump Truck aur Wheel Loader common hain.",
    ),
    "compaction": (
        "Compaction work needs rollers and compactors for soil and asphalt layers.",
        "Compaction ke liye Road Roller, Compactor aur Drum Roller best hain.",
    ),
    "concrete": (
        "Concrete road work needs mixing, placing, and pumping equipment.",
        "Concrete road ke liye Concrete Mixer, Mixer Truck aur Concrete Pump use hote hain.",
    ),
    "transport": (
        "Material transport relies on tippers and loaders for bulk movement.",
        "Material transport ke liye Dump Truck, Tipper aur Wheel Loader common hain.",
    ),
    "lifting": (
        "Lifting and erection work needs cranes and telehandlers.",
        "Lifting ke liye Crane, Hydra Crane aur Truck Mounted Crane suitable hain.",
    ),
}


def project_recommendation_explanation(project_key: str, *, lang: str = "english") -> str:
    """Why these machines for this project type (E3)."""
    info = _PROJECT_TYPES.get(project_key, {})
    label = info.get("label") or project_key.replace("_", " ").title()
    cats = info.get("categories") or []
    cat_labels = ", ".join(category_label(c) for c in cats[:4])
    reasons = _PROJECT_REASONS.get(project_key, (
        f"For {label} projects, these machine types are commonly used.",
        f"{label} project ke liye ye machines commonly use hoti hain.",
    ))
    en_reason, hing_reason = reasons
    reason = pick_lang(lang, english=en_reason, hindi=en_reason, hinglish=hing_reason)
    intro = pick_lang(
        lang,
        english=f"For **{label}** projects: {reason}",
        hindi=f"**{label}** प्रोजेक्ट के लिए: {reason}",
        hinglish=f"**{label}** project ke liye: {reason}",
    )
    if cat_labels:
        rec = pick_lang(
            lang,
            english=f"\n\nRecommended: {cat_labels}.",
            hindi=f"\n\nसुझाव: {cat_labels}।",
            hinglish=f"\n\nRecommended: {cat_labels}.",
        )
        intro += rec
    return intro


def build_recommended_categories(project_key: str) -> list[dict[str, Any]]:
    cats = _PROJECT_TYPES.get(project_key, {}).get("categories") or []
    label = _PROJECT_TYPES.get(project_key, {}).get("label") or project_key
    return [
        {
            "category": c,
            "reason": f"Commonly used for {label} projects",
        }
        for c in cats
    ]


def recommendation_clarification_warm(*, lang: str = "english") -> str:
    """Smarter project-type clarification (E2/E3)."""
    return pick_lang(
        lang,
        english=(
            "Happy to recommend the right machines. What kind of project is it?\n"
            "• Highway — grading, compaction, excavation\n"
            "• Urban road — rollers and loaders in city sites\n"
            "• Earthwork — digging and hauling\n"
            "• Compaction — soil/asphalt layers\n"
            "• Concrete — mixing and placing\n\n"
            "Pick one (e.g. Highway) or describe your site work."
        ),
        hindi=(
            "Sahi machines suggest karne ke liye project type batayein:\n"
            "1. Highway  2. Urban road  3. Earthwork  4. Compaction  5. Concrete\n\n"
            "Koi ek option choose karein ya site ka kaam batayein."
        ),
        hinglish=(
            "Sahi machines suggest karne ke liye project type batayein:\n"
            "• Highway — grading, compaction, excavation\n"
            "• Urban road — city site rollers/loaders\n"
            "• Earthwork — digging aur hauling\n"
            "• Compaction — soil/asphalt\n"
            "• Concrete — mixing aur placing\n\n"
            "Koi ek pick karein (jaise Highway) ya site ka kaam batayein."
        ),
    )
