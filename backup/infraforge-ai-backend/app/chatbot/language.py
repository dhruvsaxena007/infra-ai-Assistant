"""
Per-query reply language — NOT stored in session.

Detect language from the current user message only:
  - english   → Latin script, no Hinglish markers
  - hindi     → Devanagari script dominant
  - hinglish  → Latin + Hindi/Hinglish words (chahiye, me, kiraye, …)
"""

from __future__ import annotations

import re
from typing import Optional

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

_HINGLISH_MARKERS_RE = re.compile(
    r"\b("
    r"chahiye|chaiye|chahiy|kiraye|kiraya|kaunsi|kaunsa|kya|batao|bataiye|"
    r"sasta|sasti|muft|madad|dikhao|dikhaiye|mein|mai|mujhe|liye|wala|wali|"
    r"hain|hai|nahi|haan|ji|bhai|theek|accha|sakta|sakti|bata|dijiye|"
    r"ke\s+liye|kis\s+city|me\s+chahiye|me\s+hai"
    r")\b",
    re.I,
)


def detect_query_language(message: str) -> str:
    """
    Detect reply language for THIS message only.
    Returns: 'english' | 'hindi' | 'hinglish'
    """
    text = (message or "").strip()
    if not text:
        return "english"

    dev_count = len(_DEVANAGARI_RE.findall(text))
    latin_count = len(re.findall(r"[A-Za-z]", text))

    if dev_count > 0 and dev_count >= latin_count:
        return "hindi"

    if _HINGLISH_MARKERS_RE.search(text):
        return "hinglish"

    return "english"


def pick_lang(lang: str, *, english: str, hindi: str, hinglish: Optional[str] = None) -> str:
    if lang == "hindi":
        return hindi
    if lang == "hinglish":
        return hinglish if hinglish is not None else hindi
    return english


def format_city_list(cities: list[str]) -> str:
    """Human-readable city list: 'Pune, Delhi and Jaipur'."""
    titles = [str(c).title() for c in cities if c]
    if not titles:
        return ""
    if len(titles) == 1:
        return titles[0]
    if len(titles) == 2:
        return f"{titles[0]} and {titles[1]}"
    return ", ".join(titles[:-1]) + f" and {titles[-1]}"


def localized_greeting(*, first_time: bool, lang: str) -> str:
    if not first_time:
        return pick_lang(
            lang,
            english=(
                "Welcome back! Tell me the machine type and city — "
                "I'll shortlist options with prices and owners."
            ),
            hindi=(
                "वापसी पर स्वागत है! मशीन का प्रकार और शहर बताइए — "
                "मैं कीमत और मालिक के साथ विकल्प दिखाऊँगा।"
            ),
            hinglish=(
                "Welcome back! Machine type aur city bataiye — "
                "main price aur owner ke saath options dikhaunga."
            ),
        )
    return pick_lang(
        lang,
        english=(
            "Hello! I'm your Infra AI-Assistant for Marketplace assistant — I help you find construction "
            "machines across India with live prices and owner contact.\n\n"
            "Try: 'excavator in Jaipur under 8000', upload a photo, or ask "
            "'what machines are available in Pune'."
        ),
        hindi=(
            "नमस्ते! मैं Infra AI-Assistant for Marketplace AI Assistant हूँ। आप नाम, शहर, बजट, फ़ोटो "
            "या आवाज़ से मशीन खोज सकते हैं।\n\n"
            "उदाहरण: 'जयपुर में क्रॉलर ड्रिल 500 के अंदर'।"
        ),
        hinglish=(
            "Namaste! Main Infra AI-Assistant for Marketplace AI Assistant hoon. Aap machine search kar sakte hain "
            "by name, city, budget, image ya voice.\n\n"
            "Example: 'crawler drill in Jaipur under 500'."
        ),
    )


def localized_irrelevant(kind: str, lang: str) -> str:
    if kind == "abusive":
        return pick_lang(
            lang,
            english=(
                "I'm here to help you find construction machines professionally. "
                "Let's keep our conversation respectful.\n\n"
                "I can help with machine search, rent/buy, image or voice search, "
                "price filters, and project recommendations. What equipment do you need?"
            ),
            hindi=(
                "मैं आपको निर्माण मशीनें खोजने में पेशेवर रूप से मदद करता हूँ। "
                "कृपया बातचीत सम्मानजनक रखें।\n\n"
                "मैं मशीन खोज, किराया/खरीद, फ़ोटो या आवाज़ खोज, "
                "कीमत फ़िल्टर और प्रोजेक्ट सुझाव में मदद कर सकता हूँ। "
                "आपको कौन सी मशीन चाहिए?"
            ),
            hinglish=(
                "Main aapko construction machines dhoondhne mein professionally madad karta hoon. "
                "Baatcheet respectful rakhein.\n\n"
                "Machine search, rent/buy, image/voice search, price filter, "
                "project recommendation — sab mein madad kar sakta hoon. Kaunsi machine chahiye?"
            ),
        )
    if kind == "acknowledgment":
        return pick_lang(
            lang,
            english=(
                "You're welcome! If you need another machine search, city change, "
                "or project recommendation, just tell me."
            ),
            hindi=(
                "आपका स्वागत है! अगर आपको कोई और मशीन खोज, शहर बदलना "
                "या प्रोजेक्ट सुझाव चाहिए, बताइए।"
            ),
            hinglish=(
                "You're welcome! Agar aur machine search, city change "
                "ya project recommendation chahiye, bas bataiye."
            ),
        )
    return pick_lang(
        lang,
        english=(
            "I specialize in Infra AI-Assistant for Marketplace construction equipment — machine search, "
            "rentals, purchases, and project recommendations across India.\n\n"
            "Try: 'JCB in Jaipur under 8000', 'dump truck in Pune', or "
            "'best machine for road project'."
        ),
        hindi=(
            "मैं Infra AI-Assistant for Marketplace निर्माण उपकरण सेवाओं में विशेषज्ञ हूँ — मशीन खोज, "
            "किराया, खरीद और पूरे भारत में प्रोजेक्ट सुझाव।\n\n"
            "कोशिश करें: 'जयपुर में JCB 8000 के अंदर', 'पुणे में डंप ट्रक', "
            "या 'सड़क प्रोजेक्ट के लिए सबसे अच्छी मशीन'।"
        ),
        hinglish=(
            "Main Infra AI-Assistant for Marketplace construction equipment services mein specialize karta hoon — "
            "machine search, rentals, purchases, project recommendations.\n\n"
            "Try: 'JCB in Jaipur under 8000', 'dump truck in Pune', ya "
            "'road project ke liye best machine'."
        ),
    )


def localized_empty_city(
    city: str,
    nearby_cities: list[str],
    lang: str,
) -> str:
    """Engaging reply when a city has zero live listings."""
    city_title = str(city or "").title()
    nearby_txt = format_city_list(nearby_cities)
    if nearby_txt:
        return pick_lang(
            lang,
            english=(
                f"{city_title} doesn't have live listings on Infra AI-Assistant for Marketplace right now — "
                f"but {nearby_txt} {'are' if len(nearby_cities) > 1 else 'is'} stocked!\n\n"
                f"Want me to check **{nearby_cities[0].title()}** for you? "
                "Or tell me the exact machine type (excavator, crane, JCB…) and I'll search smartly."
            ),
            hindi=(
                f"{city_title} में अभी कोई लाइव लिस्टिंग नहीं है — "
                f"लेकिन {nearby_txt} में मशीनें उपलब्ध हैं!\n\n"
                f"क्या मैं **{nearby_cities[0].title()}** चेक करूँ? "
                "या सीधे बताइए कौन सी मशीन चाहिए (excavator, crane, JCB…)।"
            ),
            hinglish=(
                f"{city_title} me abhi live listing nahi hai — "
                f"par {nearby_txt} me machines available hain!\n\n"
                f"Kya main **{nearby_cities[0].title()}** check karoon? "
                "Ya seedha batayein kaunsi machine chahiye (excavator, crane, JCB…)."
            ),
        )
    return pick_lang(
        lang,
        english=(
            f"{city_title} is quiet on Infra AI-Assistant for Marketplace at the moment. "
            "Tell me the machine type you need — excavator, crane, JCB, road roller — "
            "and I'll find the nearest city with live listings for you."
        ),
        hindi=(
            f"{city_title} में अभी लिस्टिंग नहीं है। "
            "बताइए कौन सी मशीन चाहिए — excavator, crane, JCB — "
            "मैं पास के शहर में उपलब्धता ढूँढूँगा।"
        ),
        hinglish=(
            f"{city_title} me abhi listing nahi hai. "
            "Batayein kaunsi machine chahiye — excavator, crane, JCB — "
            "main paas ke city me availability dhoondhunga."
        ),
    )


def localized_city_category(
    city: str,
    labels: list[str],
    lang: str,
    *,
    more_count: int = 0,
    nearby_cities: Optional[list[str]] = None,
) -> str:
    city_title = str(city or "").title()
    joined = ", ".join(labels)
    if more_count > 0:
        extra_en = f" (+{more_count} more)"
        extra_hi = f" (+{more_count} और)"
        extra_hing = f" (+{more_count} aur)"
    else:
        extra_en = extra_hi = extra_hing = ""
    if not labels:
        return localized_empty_city(city, nearby_cities or [], lang)
    return pick_lang(
        lang,
        english=(
            f"Great — here's what's live in **{city_title}** right now. "
            f"Pick one and I'll show prices, availability and how to contact the owner:\n\n"
            f"{joined}{extra_en}\n\n"
            "Which machine fits your project?"
        ),
        hindi=(
            f"बढ़िया — **{city_title}** में ये मशीनें अभी उपलब्ध हैं। "
            f"कोई चुनिए, मैं कीमत और मालिक से संपर्क का तरीका दिखाऊँगा:\n\n"
            f"{joined}{extra_hi}\n\n"
            "आपके प्रोजेक्ट के लिए कौन सी सही रहेगी?"
        ),
        hinglish=(
            f"Great — **{city_title}** me ye machines live hain. "
            f"Koi pick karein, main price aur owner contact ka tareeka dikhaunga:\n\n"
            f"{joined}{extra_hing}\n\n"
            "Aapke project ke liye kaunsi sahi rahegi?"
        ),
    )


def localized_clarification(
    *,
    lang: str,
    missing_field: str,
    label: str,
    city: Optional[str] = None,
    listing_type: Optional[str] = None,
) -> str:
    city_title = str(city or "").title()
    if missing_field == "city":
        if label and label != "machine":
            return pick_lang(
                lang,
                english=(
                    f"{label} — good choice! Which city is your site in? "
                    "Share budget or rent/buy preference too and I'll shortlist the best matches."
                ),
                hindi=(
                    f"{label} — अच्छा विकल्प! प्रोजेक्ट किस शहर में है? "
                    "बजट या किराया/खरीद भी बताएँ, मैं सबसे अच्छे विकल्प दिखाऊँगा।"
                ),
                hinglish=(
                    f"{label} — good choice! Project kis city me hai? "
                    "Budget ya rent/buy bhi bata dein, main best matches dikhaunga."
                ),
            )
        return pick_lang(
            lang,
            english="Which city do you need the machine in?",
            hindi="आपको मशीन किस शहर में चाहिए?",
            hinglish="Kaunsi city me machine chahiye?",
        )
    if missing_field == "category":
        if listing_type == "rent":
            return pick_lang(
                lang,
                english=f"Which machine do you want on rent in {city_title}?",
                hindi=f"{city_title} में किराए पर कौन सी मशीन चाहिए?",
                hinglish=f"{city_title} me rent ke liye kaunsi machine chahiye?",
            )
        if listing_type == "sell":
            return pick_lang(
                lang,
                english=f"Which machine do you want to purchase in {city_title}?",
                hindi=f"{city_title} में खरीदने के लिए कौन सी मशीन चाहिए?",
                hinglish=f"{city_title} me purchase ke liye kaunsi machine chahiye?",
            )
        if city_title:
            return pick_lang(
                lang,
                english=f"Which machine do you need in {city_title}?",
                hindi=f"{city_title} में आपको कौन सी मशीन चाहिए?",
                hinglish=f"{city_title} me kaunsi machine chahiye?",
            )
        return pick_lang(
            lang,
            english=(
                "Which machine type do you need? (e.g. excavator, JCB, crane, road roller)\n"
                "Do you want rent or buy?"
            ),
            hindi=(
                "आपको कौन सी मशीन चाहिए? (जैसे excavator, JCB, crane, road roller)\n"
                "किराया चाहिए या खरीद?"
            ),
            hinglish=(
                "Kaunsi machine type chahiye? (e.g. excavator, JCB, crane, road roller)\n"
                "Rent ke liye chahiye ya buy?"
            ),
        )
    return pick_lang(
        lang,
        english=(
            "Many machines are available. Please refine:\n"
            "1. Machine type\n2. City\n3. Rent or buy\n4. Budget\n5. Brand preference"
        ),
        hindi=(
            "बहुत सारी मशीनें उपलब्ध हैं। कृपया स्पष्ट करें:\n"
            "1. मशीन का प्रकार\n2. शहर\n3. किराया या खरीद\n4. बजट\n5. ब्रांड"
        ),
        hinglish=(
            "Bahut saari machines available hain. Please refine:\n"
            "1. Machine type\n2. City\n3. Rent or buy\n4. Budget\n5. Brand preference"
        ),
    )


def localized_found_intro(
    *,
    lang: str,
    count: int,
    label: str,
    city: Optional[str],
    max_price: Optional[int],
) -> str:
    city_part = f" in {str(city).title()}" if city else ""
    city_hi = f" {str(city).title()} में" if city else ""
    city_hing = f" {str(city).title()} me" if city else ""
    budget_en = f" under ₹{max_price}" if max_price else ""
    budget_hi = f" ₹{max_price} के अंदर" if max_price else ""
    budget_hing = f" ₹{max_price} ke andar" if max_price else ""

    if lang == "hindi":
        verb = "है" if count == 1 else "हैं"
        return (
            f"अच्छी खबर — {city_hi}{budget_hi} {count} {label} मिले {verb}। "
            f"नीचे विवरण देखें, फिर कार्ड पर Contact Owner से बुकिंग शुरू करें:\n\n"
        )
    if lang == "hinglish":
        verb = "hai" if count == 1 else "hain"
        return (
            f"Good news — {city_hing}{budget_hing} {count} {label} mile {verb}. "
            f"Details neeche dekhein, phir card par Contact Owner se booking start karein:\n\n"
        )
    verb = "is" if count == 1 else "are"
    return (
        f"Good news — I found {count} {label}{city_part}{budget_en}. "
        f"Check the details below, then use **Contact Owner** on the card to take the next step:\n\n"
    )


def localized_no_results_generic(lang: str) -> str:
    return pick_lang(
        lang,
        english=(
            "I couldn't find an exact match this time — that happens with tight filters. "
            "Try a nearby city, a slightly higher budget, or tell me the job type "
            "(digging, lifting, road work) and I'll suggest the right machine category."
        ),
        hindi=(
            "इस बार सटीक मेल नहीं मिला — कड़े फ़िल्टर में ऐसा होता है। "
            "पास का शहर, थोड़ा बड़ा बजट, या काम का प्रकार बताएँ "
            "(खुदाई, उठाने, सड़क) — मैं सही मशीन सुझाऊँगा।"
        ),
        hinglish=(
            "Exact match nahi mila — tight filters me aisa hota hai. "
            "Paas ka city, thoda zyada budget, ya kaam ka type bataiye "
            "(digging, lifting, road) — main sahi machine suggest karunga."
        ),
    )


def localized_no_exact_in_city(
    *,
    label: str,
    city: str,
    similar: list[str],
    nearby_cities: list[str],
    lang: str,
) -> str:
    """Warm no-result when category + city have no stock."""
    city_title = str(city or "").title()
    similar_txt = ", ".join(similar) if similar else ""
    nearby_txt = format_city_list(nearby_cities)
    parts_en = [
        f"No {label} in {city_title} on Infra AI-Assistant for Marketplace right now — but don't stop here!"
    ]
    if similar_txt:
        parts_en.append(f"Similar options in other cities: {similar_txt}.")
    if nearby_txt:
        parts_en.append(
            f"**{nearby_cities[0].title()}** and nearby cities have live listings — "
            f"want me to check {nearby_txt}?"
        )
    parts_en.append(
        "Or tell me what work you need (digging, lifting, transport) and I'll find the best fit."
    )
    return pick_lang(
        lang,
        english=" ".join(parts_en),
        hindi=(
            f"{city_title} में अभी {label} नहीं मिला — पर रुकिए नहीं! "
            + (f"मिलते-जुलते विकल्प: {similar_txt}. " if similar_txt else "")
            + (
                f"**{nearby_cities[0].title()}** में लिस्टिंग है — {nearby_txt} चेक करूँ? "
                if nearby_txt else ""
            )
            + "या बताइए काम क्या है (खुदाई, उठाना, transport) — सही मशीन ढूँढूँगा।"
        ),
        hinglish=(
            f"{city_title} me abhi {label} nahi mila — par rukiye mat! "
            + (f"Similar options: {similar_txt}. " if similar_txt else "")
            + (
                f"**{nearby_cities[0].title()}** me listing hai — {nearby_txt} check karoon? "
                if nearby_txt else ""
            )
            + "Ya bataiye kaam kya hai (digging, lifting, transport) — sahi machine dhoondhunga."
        ),
    )


def localized_purpose_no_match(
    city: str,
    nearby_cities: list[str],
    lang: str,
) -> str:
    city_title = str(city or "").title()
    nearby_txt = format_city_list(nearby_cities)
    if nearby_txt:
        return pick_lang(
            lang,
            english=(
                f"I looked across {city_title} for that purpose but nothing close enough matched. "
                f"**{nearby_cities[0].title()}** has more options — want me to check {nearby_txt}? "
                "Or pick a different machine type / purpose and we'll try again."
            ),
            hindi=(
                f"{city_title} में उस काम के लिए कोई करीबी मेल नहीं मिला। "
                f"**{nearby_cities[0].title()}** में ज़्यादा विकल्प हैं — {nearby_txt} चेक करूँ? "
                "या दूसरी मशीन / काम बताइए।"
            ),
            hinglish=(
                f"{city_title} me us purpose ke liye close match nahi mila. "
                f"**{nearby_cities[0].title()}** me zyada options hain — {nearby_txt} check karoon? "
                "Ya different machine / purpose bataiye."
            ),
        )
    return pick_lang(
        lang,
        english=(
            f"I couldn't find a close match in {city_title} for that purpose. "
            "Try another machine category, a nearby city, or describe your project differently."
        ),
        hindi=(
            f"{city_title} में उस काम के लिए करीबी मेल नहीं मिला। "
            "दूसरी मशीन, पास का शहर, या प्रोजेक्ट फिर से बताइए।"
        ),
        hinglish=(
            f"{city_title} me us purpose ke liye close match nahi mila. "
            "Dusri machine, paas ka city, ya project dubara bataiye."
        ),
    )


def localized_alternatives_footer(lang: str) -> str:
    return pick_lang(
        lang,
        english=(
            "These are close alternatives — compare price, condition and city "
            "before you tap Contact Owner on your preferred card."
        ),
        hindi=(
            "ये करीबी विकल्प हैं — Contact Owner से पहले कीमत, हालत और शहर तुलना करें।"
        ),
        hinglish=(
            "Ye close alternatives hain — Contact Owner se pehle price, condition "
            "aur city compare karein."
        ),
    )


def localized_purpose_clarification(
    label: str, city: Optional[str], lang: str,
) -> str:
    city_title = str(city or "").title()
    where_en = f" in {city_title}" if city_title else ""
    where_hi = f" {city_title} में" if city_title else ""
    return pick_lang(
        lang,
        english=(
            f"No exact {label}{where_en} — that's okay, we can still find the right fit! "
            "What job do you need it for?\n"
            "1. Digging / excavation / earthwork\n"
            "2. Loading / material handling\n"
            "3. Lifting / height work\n"
            "4. Compaction / road work\n"
            "5. Transport / hauling\n"
            "6. Drilling / boring\n\n"
            "Reply with a number, or name another machine (e.g. excavator, JCB)."
        ),
        hindi=(
            f"सटीक {label}{where_hi} नहीं मिला। मशीन किस काम के लिए चाहिए?\n"
            "1. खुदाई / excavation\n"
            "2. लोडिंग / material handling\n"
            "3. उठाने का काम / lifting\n"
            "4. compaction / सड़क का काम\n"
            "5. transport / hauling\n"
            "6. drilling / boring\n\n"
            "या कोई दूसरी मशीन बताइए (जैसे excavator, crane)।"
        ),
        hinglish=(
            f"No exact {label}{where_en}. Machine kis kaam ke liye chahiye?\n"
            "1. Digging / excavation / earthwork\n"
            "2. Loading / material handling\n"
            "3. Lifting / height work\n"
            "4. Compaction / road work\n"
            "5. Transport / hauling\n"
            "6. Drilling / boring\n\n"
            "Ya seedha alternative machine type bataiye (e.g. excavator, crane)."
        ),
    )


def localized_recommendation_clarification(lang: str) -> str:
    lines_en = [
        "What type of road / construction project is it? Choose one:",
        "1. Highway", "2. Urban road", "3. Earthwork", "4. Compaction",
        "5. Concrete road", "6. Material transport", "7. Lifting / crane work",
    ]
    lines_hi = [
        "सड़क / निर्माण प्रोजेक्ट किस प्रकार का है? एक चुनें:",
        "1. Highway", "2. Urban road", "3. Earthwork", "4. Compaction",
        "5. Concrete road", "6. Material transport", "7. Lifting / crane work",
    ]
    lines_hing = [
        "Road / construction project kis type ka hai? Choose one:",
        "1. Highway", "2. Urban road", "3. Earthwork", "4. Compaction",
        "5. Concrete road", "6. Material transport", "7. Lifting / crane work",
    ]
    if lang == "hindi":
        return "\n".join(lines_hi)
    if lang == "hinglish":
        return "\n".join(lines_hing)
    return "\n".join(lines_en)


def localized_booking_guidance(
    *,
    label: Optional[str] = None,
    city: Optional[str] = None,
    lang: str = "english",
) -> str:
    """Steps to rent / contact owner — keeps the user moving forward."""
    city_title = str(city or "").title() if city else ""
    if label and city_title:
        context_en = f"For the {label} in {city_title} you were viewing"
        context_hi = f"आप जो {label} {city_title} में देख रहे थे, उसके लिए"
        context_hing = f"Jo {label} aap {city_title} me dekh rahe the, uske liye"
    elif label:
        context_en = f"For the {label} you were viewing"
        context_hi = f"आप जो {label} देख रहे थे, उसके लिए"
        context_hing = f"Jo {label} aap dekh rahe the, uske liye"
    else:
        context_en = "To rent a machine on Infra AI-Assistant for Marketplace"
        context_hi = "Infra AI-Assistant for Marketplace पर मशीन किराए पर लेने के लिए"
        context_hing = "Infra AI-Assistant for Marketplace par machine rent karne ke liye"

    return pick_lang(
        lang,
        english=(
            f"Great — {context_en}, here is how to proceed:\n\n"
            "1. Open the **machine card** from the results above.\n"
            "2. Tap **Contact Owner** on the card to reach the listing owner directly.\n"
            "3. Before you confirm, review **price**, **availability**, **condition**, "
            "**manufacturing year**, and any **security deposit**.\n"
            "4. Use **View Details** or **Compare** if you want to double-check options.\n"
            "5. For documents or verification, use the **Document** button in the chat bar.\n\n"
            "Once you pick a listing, **Contact Owner** is the next step — "
            "that starts the rental conversation with the owner."
        ),
        hindi=(
            f"बढ़िया — {context_hi}, आगे ये करें:\n\n"
            "1. ऊपर दिखे परिणामों में से **मशीन कार्ड** खोलें।\n"
            "2. कार्ड पर **Contact Owner** दबाएँ — मालिक से सीधे बात शुरू होगी।\n"
            "3. पुष्टि से पहले **कीमत**, **उपलब्धता**, **हालत**, **निर्माण वर्ष** "
            "और **सुरक्षा जमा** जाँच लें।\n"
            "4. **View Details** या **Compare** से विकल्प तुलना कर सकते हैं।\n"
            "5. दस्तावेज़ के लिए चैट बार में **Document** बटन का उपयोग करें।\n\n"
            "लिस्टिंग चुनने के बाद **Contact Owner** अगला कदम है — "
            "इससे किराए की बात मालिक से शुरू होती है।"
        ),
        hinglish=(
            f"Great — {context_hing}, aage ye steps follow karein:\n\n"
            "1. Upar ke results me se **machine card** open karein.\n"
            "2. Card par **Contact Owner** tap karein — owner se direct baat shuru hogi.\n"
            "3. Confirm karne se pehle **price**, **availability**, **condition**, "
            "**manufacturing year**, aur **security deposit** check karein.\n"
            "4. **View Details** ya **Compare** se options compare kar sakte hain.\n"
            "5. Documents ke liye chat bar me **Document** button use karein.\n\n"
            "Listing choose karne ke baad **Contact Owner** next step hai — "
            "isse rent ki baat owner se start hoti hai."
        ),
    )


def localized_too_many_results(count: int, lang: str) -> str:
    return pick_lang(
        lang,
        english=(
            f"Many machines ({count}) are available. Please refine:\n"
            "1. Machine type (e.g. excavator, crane)\n"
            "2. City\n3. Rent or buy\n4. Budget\n5. Brand preference"
        ),
        hindi=(
            f"बहुत सारी मशीनें ({count}) उपलब्ध हैं। कृपया स्पष्ट करें:\n"
            "1. मशीन का प्रकार\n2. शहर\n3. किराया या खरीद\n4. बजट\n5. ब्रांड"
        ),
        hinglish=(
            f"Bahut saari machines ({count}) available hain. Please refine:\n"
            "1. Machine type\n2. City\n3. Rent or buy\n4. Budget\n5. Brand"
        ),
    )
