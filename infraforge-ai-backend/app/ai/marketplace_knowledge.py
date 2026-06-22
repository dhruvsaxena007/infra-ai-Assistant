"""
Deterministic InfraForge marketplace knowledge — no hallucination (E4).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.chatbot.language import pick_lang

# Topic keys matched against message + intent
_TOPIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("rent_process", re.compile(
        r"how\s+(?:to|do\s+i)\s+rent|rent\s+(?:process|kaise)|kiraye?\s+kaise|"
        r"machine\s+(?:kaise\s+)?(?:rent|hire|book)|ask\s+about\s+rental",
        re.I,
    )),
    ("buy_process", re.compile(
        r"how\s+(?:to|do\s+i)\s+buy|purchase\s+process|buy\s+machine|"
        r"machine\s+(?:kaise\s+)?(?:buy|purchase|khareed)",
        re.I,
    )),
    ("how_infraforge", re.compile(
        r"how\s+does\s+infraforge|infraforge\s+(?:kaise|works?)|what\s+is\s+infraforge|"
        r"marketplace\s+(?:kaise|works?)",
        re.I,
    )),
    ("security_deposit", re.compile(
        r"security\s+deposit|deposit\s+(?:kitna|amount|refund|policy)|"
        r"jama\s+rashi|deposit\s+kya\s+hai",
        re.I,
    )),
    ("transport", re.compile(
        r"transport\s+(?:cost|charge|calculated|kaise)|delivery\s+(?:charge|cost|kaise)|"
        r"how\s+is\s+transport|machine\s+(?:transport|delivery)",
        re.I,
    )),
    ("documents", re.compile(
        r"documents?\s+(?:required|needed|chahiye)|kya\s+documents?|"
        r"paperwork|license\s+required|gst\s+for\s+rent",
        re.I,
    )),
    ("contact_owner", re.compile(
        r"how\s+(?:to|do\s+i)\s+contact\s+(?:the\s+)?owner|owner\s+(?:se\s+)?(?:kaise|contact)|"
        r"reach\s+(?:the\s+)?owner|seller\s+contact",
        re.I,
    )),
]

_INTENT_TOPIC = {
    "platform_how_to": "how_infraforge",
    "booking_help": "rent_process",
    "security_deposit": "security_deposit",
    "delivery_logistics": "transport",
}


def detect_topic(message: str, intent: Optional[str] = None) -> Optional[str]:
    text = (message or "").strip()
    for key, pat in _TOPIC_PATTERNS:
        if pat.search(text):
            return key
    if intent and intent in _INTENT_TOPIC:
        if intent == "platform_how_to":
            return "how_infraforge"
        return _INTENT_TOPIC[intent]
    return None


def _rent_process(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "To rent a machine on InfraForge:\n"
            "1. Search by machine type and city\n"
            "2. Open the listing and check price, availability, and condition\n"
            "3. Tap **Contact Owner** on the card to talk to the listing owner\n"
            "4. Agree on dates, site location, security deposit, and transport\n"
            "5. Support can help if booking or payment needs assistance\n\n"
            "Tell me the machine type and city — I'll shortlist options."
        ),
        hindi=(
            "InfraForge par machine rent karne ke liye:\n"
            "1. Machine type aur city se search karein\n"
            "2. Listing details, price aur availability check karein\n"
            "3. Card par **Contact Owner** se owner se baat karein\n"
            "4. Dates, site, deposit aur transport confirm karein\n\n"
            "Machine type aur city batayein — main options dikhaunga."
        ),
        hinglish=(
            "InfraForge par machine rent karne ke liye:\n"
            "1. Machine type + city search karein\n"
            "2. Price, availability, condition check karein\n"
            "3. Card par **Contact Owner** tap karein\n"
            "4. Dates, site, deposit, transport confirm karein\n\n"
            "Kaunsi machine aur kis city me chahiye?"
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "platform_how_to",
        "suggestions": ["Excavator in Jaipur", "Search Machine", "Contact support"],
        "handover": None,
    }


def _buy_process(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "To buy a machine on InfraForge:\n"
            "1. Search the machine type and filter for **buy / sell** listings\n"
            "2. Compare price, year, condition, and location on the cards\n"
            "3. Use **Contact Owner** to negotiate and arrange inspection\n"
            "4. Support can assist with documentation or payment questions\n\n"
            "Which machine are you looking to purchase?"
        ),
        hinglish=(
            "Machine buy karne ke liye:\n"
            "1. Machine search karein aur **buy/sell** filter use karein\n"
            "2. Price, year, condition compare karein\n"
            "3. **Contact Owner** se inspection aur deal fix karein\n\n"
            "Kaunsi machine purchase karni hai?"
        ),
        hindi=(
            "Machine kharidne ke liye:\n"
            "1. Machine type search karein aur **buy/sell** filter lagayein\n"
            "2. Price, year, condition compare karein\n"
            "3. **Contact Owner** se inspection aur deal tay karein\n\n"
            "Kaunsi machine kharidni hai?"
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "platform_how_to",
        "suggestions": ["Show buy options", "Excavator in Delhi", "Contact support"],
        "handover": None,
    }


def _how_infraforge(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "InfraForge is a construction equipment marketplace across India. You can:\n"
            "• Search and compare machines by type, city, and budget\n"
            "• Rent or buy from verified listing owners\n"
            "• Upload a photo for image-based search\n"
            "• Ask document questions after uploading a PDF\n"
            "• Get help with booking, payment, refund, and delivery\n\n"
            "What would you like to do first?"
        ),
        hinglish=(
            "InfraForge construction equipment marketplace hai. Aap:\n"
            "• Machine search/compare kar sakte hain\n"
            "• Rent ya buy listings dekh sakte hain\n"
            "• Photo upload kar image search kar sakte hain\n"
            "• Booking, payment, refund, delivery me help le sakte hain\n\n"
            "Pehle kya karna hai?"
        ),
        hindi=(
            "InfraForge construction equipment marketplace hai. Aap:\n"
            "• Machine search/compare kar sakte hain\n"
            "• Rent ya buy listings dekh sakte hain\n"
            "• Photo upload kar image search kar sakte hain\n"
            "• Booking, payment, refund, delivery me madad le sakte hain\n\n"
            "Pehle kya karna chahenge?"
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "platform_how_to",
        "suggestions": ["Search Machine", "Upload Image", "Ask About Rental"],
        "handover": None,
    }


def _security_deposit(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "Security deposit depends on machine type, rental duration, and the owner's policy. "
            "It is usually refundable after the machine is returned in agreed condition. "
            "Check the listing details or share your booking ID — support can confirm the exact amount."
        ),
        hinglish=(
            "Security deposit machine type, rental duration aur owner policy par depend karta hai. "
            "Machine wapas karne par usually refundable hota hai. "
            "Listing details dekhein ya booking ID share karein."
        ),
        hindi=(
            "Security deposit machine type, rental duration aur owner policy par depend karta hai. "
            "Machine wapas karne par aam taur par refundable hota hai. "
            "Listing details dekhein ya booking ID share karein."
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "security_deposit",
        "suggestions": ["Contact support", "Ask About Rental", "Search machine"],
        "handover": None,
    }


def _transport(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "Transport cost is calculated based on machine size, pickup location, your site city, "
            "and distance. Some owners include delivery; others charge separately. "
            "Share machine name and site city — I'll help you search, or contact support for a quote."
        ),
        hinglish=(
            "Transport cost machine size, pickup location, site city aur distance par depend karta hai. "
            "Kuch owners delivery include karte hain, kuch alag charge karte hain. "
            "Machine name aur site city batayein."
        ),
        hindi=(
            "Transport cost machine size, pickup location, site city aur distance par depend karta hai. "
            "Kuch owners delivery include karte hain, kuch alag charge karte hain. "
            "Machine name aur site city batayein."
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "delivery_logistics",
        "suggestions": ["Search machine", "Contact support", "Raise Request"],
        "handover": None,
    }


def _documents(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "Typical documents for machine rental:\n"
            "• Site address and project details\n"
            "• ID proof of the person booking\n"
            "• GST details (if applicable for business rental)\n"
            "• Signed rental agreement with the owner\n\n"
            "Exact requirements vary by owner — confirm on **Contact Owner** or with support."
        ),
        hinglish=(
            "Rent ke liye usually chahiye: site address, ID proof, GST (agar business ho), "
            "aur owner ke saath rental agreement. Owner-wise requirements alag ho sakti hain — "
            "**Contact Owner** ya support se confirm karein."
        ),
        hindi=(
            "Rent ke liye aam taur par chahiye: site address, ID proof, GST (agar business ho), "
            "aur owner ke saath rental agreement. Owner-wise requirements alag ho sakti hain — "
            "**Contact Owner** ya support se confirm karein."
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "platform_how_to",
        "suggestions": ["Ask About Rental", "Contact support", "Search machine"],
        "handover": None,
    }


def _contact_owner(lang: str) -> dict[str, Any]:
    msg = pick_lang(
        lang,
        english=(
            "To contact a machine owner:\n"
            "1. Search and open the machine card you like\n"
            "2. Tap **Contact Owner** on the card\n"
            "3. Discuss availability, price, deposit, and transport directly\n\n"
            "Search a machine first — then I can guide you on the next step."
        ),
        hinglish=(
            "Owner se contact karne ke liye machine card par **Contact Owner** tap karein. "
            "Pehle machine search karein — phir main next step guide karunga."
        ),
        hindi=(
            "Owner se contact karne ke liye machine card par **Contact Owner** tap karein. "
            "Pehle machine search karein — phir main agla step guide karunga."
        ),
    )
    return {
        "message": msg,
        "assistant_mode": "platform_how_to",
        "suggestions": ["Search Machine", "Excavator in Jaipur"],
        "handover": None,
    }


_BUILDERS = {
    "rent_process": _rent_process,
    "buy_process": _buy_process,
    "how_infraforge": _how_infraforge,
    "security_deposit": _security_deposit,
    "transport": _transport,
    "documents": _documents,
    "contact_owner": _contact_owner,
}


def lookup_knowledge(
    message: str,
    *,
    intent: Optional[str] = None,
    lang: str = "english",
) -> Optional[dict[str, Any]]:
    """Return structured response dict or None if no knowledge match."""
    topic = detect_topic(message, intent)
    if not topic:
        return None
    builder = _BUILDERS.get(topic)
    if not builder:
        return None
    return builder(lang)
