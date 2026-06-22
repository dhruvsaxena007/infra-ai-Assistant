"""
Build 60+ sequential conversation eval scenarios (10–15 turns each).

Generates English, Hinglish, and Hindi flows with explicit memory_role
on each turn so the runner can test context retention per query.
"""

from __future__ import annotations

from typing import Any


def conv(
    id_: str,
    *,
    title: str,
    lang_mix: str,
    flow_type: str,
    turns: list[dict],
    description: str = "",
) -> dict:
    return {
        "id": id_,
        "eval_type": "conversation",
        "title": title,
        "lang_mix": lang_mix,
        "flow_type": flow_type,
        "description": description,
        "session_id": f"conv_{id_}",
        "clear_session": True,
        "turns": turns,
    }


def t(msg: str, **expect: Any) -> dict:
    row: dict = {"message": msg}
    if expect:
        row["expect"] = expect
    return row


def _mt(msg: str, role: str, **expect: Any) -> dict:
    row: dict = {"message": msg, "memory_role": role}
    if expect:
        row["expect"] = expect
    return row

CITIES = [
    "jaipur", "delhi", "mumbai", "pune", "bangalore",
    "chennai", "hyderabad", "ahmedabad", "kolkata",
]

CITY_SWITCH = {
    "jaipur": "delhi",
    "delhi": "mumbai",
    "mumbai": "pune",
    "pune": "bangalore",
    "bangalore": "chennai",
    "chennai": "hyderabad",
    "hyderabad": "ahmedabad",
    "ahmedabad": "kolkata",
    "kolkata": "jaipur",
}

CATEGORIES = [
    ("excavator", "excavator", "50000"),
    ("crane", "crane", "40000"),
    ("road roller", "road roller", "8000"),
    ("backhoe loader", "backhoe loader", "12000"),
    ("concrete mixer", "concrete mixer", "6000"),
    ("dump truck", "dump truck", "15000"),
    ("bulldozer", "bulldozer", "25000"),
    ("hydra crane", "hydra crane", "35000"),
]

BUDGET_LOW = {
    "excavator": "8000",
    "crane": "7000",
    "road roller": "6000",
    "backhoe loader": "9000",
    "concrete mixer": "5000",
    "dump truck": "10000",
    "bulldozer": "12000",
    "hydra crane": "8000",
}


def _greet_search_refine_en(city: str, cat_slug: str, category: str, budget: str) -> dict:
    city2 = CITY_SWITCH[city]
    low = BUDGET_LOW.get(category, "8000")
    cid = f"en_greet_{city}_{cat_slug}_refine"
    return conv(
        cid,
        title=f"EN greet→{category} {city}→{city2} refine",
        lang_mix="english",
        flow_type="greet_search_refine",
        description=f"English: greeting, {city} {category}, budget refine, switch to {city2}, support.",
        turns=[
            _mt("hi", "greeting", machines_max=0, not_assistant_mode="machine_search"),
            _mt("how are you", "none", machines_max=0),
            _mt(f"i need a machine in {city}", "establish_city"),
            _mt(category, "establish_category", category=category, city=city),
            _mt(f"under {budget} per day", "refine_budget", category=category, city=city),
            _mt("show cheaper options", "refine_cheaper", category=category, city=city),
            _mt("higher budget me kya option hai", "refine_higher_budget", category=category, city=city),
            _mt(f"same in {city2}", "city_switch", category=category, city=city2),
            _mt("with operator included", "operator", category=category, city=city2),
            _mt("jcb brand only", "brand_filter", category=category, city=city2),
            _mt("thanks that helps", "thanks", machines_max=0),
            _mt("how does payment work for booking", "support", machines_max=0, not_assistant_mode="machine_search"),
        ],
    )


def _greet_search_refine_hinglish(city: str, cat_slug: str, category: str) -> dict:
    city2 = CITY_SWITCH[city]
    low = BUDGET_LOW.get(category, "8000")
    cid = f"hi_greet_{city}_{cat_slug}_refine"
    return conv(
        cid,
        title=f"Hinglish greet→{category} {city}→{city2}",
        lang_mix="hinglish",
        flow_type="greet_search_refine",
        description=f"Hinglish contractor: namaste se search tak, {city} se {city2}.",
        turns=[
            _mt("namaste", "greeting", machines_max=0),
            _mt("kaise ho aap", "none", machines_max=0),
            _mt(f"mujhe {city} me machine chahiye", "establish_city"),
            _mt(f"{category} chahiye", "establish_category", category=category, city=city),
            _mt(f"{low} se kam budget me", "refine_budget", category=category, city=city),
            _mt("aur saste options dikhao", "refine_cheaper", category=category, city=city),
            _mt("thoda budget badha do", "refine_higher_budget", category=category, city=city),
            _mt(f"{city2} me bhi same chahiye", "city_switch", category=category, city=city2),
            _mt("operator ke sath", "operator", category=category, city=city2),
            _mt("jcb brand dikhao", "brand_filter", category=category, city=city2),
            _mt("booking kaise hoti hai", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt("theek hai dhanyavaad", "thanks", machines_max=0),
        ],
    )


def _greet_search_refine_hindi(city: str, cat_slug: str, category: str) -> dict:
    city2 = CITY_SWITCH[city]
    low = BUDGET_LOW.get(category, "8000")
    cid = f"hn_greet_{city}_{cat_slug}_refine"
    return conv(
        cid,
        title=f"Hindi greet→{category} {city}→{city2}",
        lang_mix="hindi",
        flow_type="greet_search_refine",
        description=f"Hindi flow: {city} me {category}, budget, {city2} switch.",
        turns=[
            _mt("namaste ji", "greeting", machines_max=0),
            _mt("aap kaise hain", "none", machines_max=0),
            _mt(f"mujhe {city} me machine chahiye", "establish_city"),
            _mt(f"{category} chahiye", "establish_category", category=category, city=city),
            _mt(f"din me {low} rupaye se kam", "refine_budget", category=category, city=city),
            _mt("sasta option dikhao", "refine_cheaper", category=category, city=city),
            _mt("budget thoda badha sakte hain", "refine_higher_budget", category=category, city=city),
            _mt(f"{city2} me bhi wahi chahiye", "city_switch", category=category, city=city2),
            _mt("operator included", "operator", category=category, city=city2),
            _mt("jcb brand", "brand_filter", category=category, city=city2),
            _mt("dhanyavaad", "thanks", machines_max=0),
            _mt("payment kaise hota hai booking me", "support", machines_max=0, not_assistant_mode="machine_search"),
        ],
    )


def _direct_search_refine_en(city: str, cat_slug: str, category: str, budget: str) -> dict:
    city2 = CITY_SWITCH[city]
    cid = f"en_direct_{city}_{cat_slug}_refine"
    return conv(
        cid,
        title=f"EN direct {category} {city} refine",
        lang_mix="english",
        flow_type="direct_search_refine",
        description=f"Direct search {category} in {city}, refine, switch {city2}.",
        turns=[
            _mt(f"{category} in {city}", "establish_category", category=category, city=city),
            _mt(f"under {budget}", "refine_budget", category=category, city=city),
            _mt("cheaper options", "refine_cheaper", category=category, city=city),
            _mt("show more options", "more_options", category=category, city=city),
            _mt(f"same in {city2}", "city_switch", category=category, city=city2),
            _mt("with operator", "operator", category=category, city=city2),
            _mt("monthly rent possible", "more_options", category=category, city=city2),
            _mt("jcb only", "brand_filter", category=category, city=city2),
            _mt("thanks", "thanks", machines_max=0),
        ],
    )


def _city_inventory_drill(city: str, cat_slug: str, category: str, lang: str) -> dict:
    city2 = CITY_SWITCH[city]
    if lang == "hinglish":
        msgs = [
            ("hello", "greeting", {}),
            (f"{city} me kaun si machines hain", "city_inventory", {"machines_max": 0}),
            (category, "establish_category", {"category": category, "city": city}),
            ("sasta dikhao", "refine_cheaper", {"category": category, "city": city}),
            (f"{city2} me bhi", "city_switch", {"category": category, "city": city2}),
            ("aur options", "more_options", {"category": category, "city": city2}),
            ("rent kaise hota hai", "support", {"machines_max": 0, "not_assistant_mode": "machine_search"}),
            ("wapas machine dikhao", "resume_search", {"category": category, "city": city2}),
            ("thanks", "thanks", {"machines_max": 0}),
        ]
        prefix = "hi"
    else:
        msgs = [
            ("hi", "greeting", {}),
            (f"what machines are available in {city}", "city_inventory", {"machines_max": 0}),
            (category, "establish_category", {"category": category, "city": city}),
            ("under 10000", "refine_budget", {"category": category, "city": city}),
            ("cheaper please", "refine_cheaper", {"category": category, "city": city}),
            (f"same in {city2}", "city_switch", {"category": category, "city": city2}),
            ("how do I rent on infraforge", "support", {"machines_max": 0, "not_assistant_mode": "machine_search"}),
            ("show machines again", "resume_search", {"category": category, "city": city2}),
            ("ok thanks", "thanks", {"machines_max": 0}),
        ]
        prefix = "en"
    cid = f"{prefix}_cityinv_{city}_{cat_slug}"
    turns = [_mt(m, r, **exp) for m, r, exp in msgs]
    return conv(
        cid,
        title=f"City inventory→{category} {city}",
        lang_mix=lang if lang != "en" else "english",
        flow_type="city_inventory_drill",
        description=f"Browse {city} inventory then drill to {category}.",
        turns=turns,
    )


def _support_interrupt(city: str, cat_slug: str, category: str, lang: str) -> dict:
    city2 = CITY_SWITCH[city]
    if lang == "hinglish":
        cid = f"hi_support_{city}_{cat_slug}"
        turns = [
            _mt("namaste", "greeting", machines_max=0),
            _mt(f"{category} chahiye {city} me", "establish_category", category=category, city=city),
            _mt("sasta option", "refine_cheaper", category=category, city=city),
            _mt("payment cut gaya booking nahi hui", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt("refund chahiye", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt(f"theek hai ab {category} dikhao", "resume_search", category=category, city=city),
            _mt(f"{city2} me bhi dekho", "city_switch", category=category, city=city2),
            _mt("aur options", "more_options", category=category, city=city2),
            _mt("dhanyavaad", "thanks", machines_max=0),
        ]
        lm = "hinglish"
    else:
        cid = f"en_support_{city}_{cat_slug}"
        turns = [
            _mt("hello", "greeting", machines_max=0),
            _mt(f"{category} in {city}", "establish_category", category=category, city=city),
            _mt("cheaper options", "refine_cheaper", category=category, city=city),
            _mt("payment failed amount deducted", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt("I want refund", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt(f"ok show {category} again", "resume_search", category=category, city=city),
            _mt(f"same in {city2}", "city_switch", category=category, city=city2),
            _mt("thanks", "thanks", machines_max=0),
        ]
        lm = "english"
    return conv(
        cid,
        title=f"Support interrupt→resume {category} {city}",
        lang_mix=lm,
        flow_type="support_interrupt",
        description="Payment issue mid-chat then resume search with context.",
        turns=turns,
    )


def _frustration_recovery(city: str, cat_slug: str, category: str) -> dict:
    city2 = CITY_SWITCH[city]
    cid = f"hi_frust_{city}_{cat_slug}"
    return conv(
        cid,
        title=f"Frustration recovery {category} {city}",
        lang_mix="hinglish",
        flow_type="frustration_recovery",
        description="User frustrated mid-search, then continues in new city.",
        turns=[
            _mt("hey", "greeting", machines_max=0),
            _mt(f"{category} in {city} under 8000", "establish_category", category=category, city=city),
            _mt("tum bilkul bekar ho", "none", machines_max=0),
            _mt("sorry gussa ho gaya", "none", machines_max=0),
            _mt(f"{category} in {city2}", "city_switch", category=category, city=city2),
            _mt("cheaper options", "refine_cheaper", category=category, city=city2),
            _mt("operator ke sath", "operator", category=category, city=city2),
            _mt("payment issue hai", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt(f"ab {category} dikhao", "resume_search", category=category, city=city2),
            _mt("thanks", "thanks", machines_max=0),
        ],
    )


def _project_recommendation(city: str, cat_slug: str, category: str) -> dict:
    city2 = CITY_SWITCH[city]
    cid = f"en_project_{city}_{cat_slug}"
    return conv(
        cid,
        title=f"Project recommend→{category} {city}",
        lang_mix="english",
        flow_type="project_recommendation",
        description="Project description then narrow to category.",
        turns=[
            _mt("hi", "greeting", machines_max=0),
            _mt(f"I have a construction project in {city}", "establish_city"),
            _mt("what machine do you recommend", "none"),
            _mt(f"{category} sounds good", "establish_category", category=category, city=city),
            _mt("under 12000 per day", "refine_budget", category=category, city=city),
            _mt("show cheaper options", "refine_cheaper", category=category, city=city),
            _mt(f"same in {city2}", "city_switch", category=category, city=city2),
            _mt("with operator", "operator", category=category, city=city2),
            _mt("how to book on infraforge", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt("thanks", "thanks", machines_max=0),
        ],
    )


def _compare_then_search(city: str, cat_slug: str, category: str) -> dict:
    city2 = CITY_SWITCH[city]
    cid = f"en_compare_{city}_{cat_slug}"
    return conv(
        cid,
        title=f"Compare brands→{category} {city}",
        lang_mix="english",
        flow_type="compare_then_search",
        description="Brand comparison then specific search.",
        turns=[
            _mt("hi", "greeting", machines_max=0),
            _mt(f"compare jcb vs cat {category}", "compare", machines_max=0),
            _mt(f"show jcb {category} in {city}", "establish_category", category=category, city=city),
            _mt("under 9000", "refine_budget", category=category, city=city),
            _mt("cheaper please", "refine_cheaper", category=category, city=city),
            _mt(f"same in {city2}", "city_switch", category=category, city=city2),
            _mt("with operator", "operator", category=category, city=city2),
            _mt("thanks bye", "thanks", machines_max=0),
        ],
    )


def _vague_clarify(city: str, cat_slug: str, category: str, lang: str) -> dict:
    city2 = CITY_SWITCH[city]
    if lang == "hinglish":
        cid = f"hi_vague_{city}_{cat_slug}"
        turns = [
            _mt("hi", "greeting", machines_max=0),
            _mt("mujhe machine chahiye", "none", machines_max=0),
            _mt(f"{city} me", "establish_city", city=city),
            _mt(f"{category} chahiye", "establish_category", category=category, city=city),
            _mt("sasta", "refine_cheaper", category=category, city=city),
            _mt(f"{city2} me bhi", "city_switch", category=category, city=city2),
            _mt("aur dikhao", "more_options", category=category, city=city2),
            _mt("thanks bhai", "thanks", machines_max=0),
        ]
        lm = "hinglish"
    else:
        cid = f"en_vague_{city}_{cat_slug}"
        turns = [
            _mt("hello", "greeting", machines_max=0),
            _mt("i want to rent a machine", "none", machines_max=0),
            _mt(city, "establish_city", city=city),
            _mt(category, "establish_category", category=category, city=city),
            _mt("cheaper options", "refine_cheaper", category=category, city=city),
            _mt(f"same in {city2}", "city_switch", category=category, city=city2),
            _mt("more options", "more_options", category=category, city=city2),
            _mt("thanks", "thanks", machines_max=0),
        ]
        lm = "english"
    return conv(
        cid,
        title=f"Vague clarify→{category} {city}",
        lang_mix=lm,
        flow_type="clarify_then_search",
        description="Vague start, clarify city+category, then refine.",
        turns=turns,
    )


def _mixed_lang_switch(city: str, cat_slug: str, category: str) -> dict:
    city2 = CITY_SWITCH[city]
    cid = f"mix_lang_{city}_{cat_slug}"
    return conv(
        cid,
        title=f"Mixed EN→HI {category} {city}",
        lang_mix="mixed",
        flow_type="lang_switch",
        description="English start, Hindi/Hinglish follow-ups — context must persist.",
        turns=[
            _mt("hello good morning", "greeting", machines_max=0),
            _mt(f"i need equipment in {city}", "establish_city"),
            _mt(category, "establish_category", category=category, city=city),
            _mt("ab sasta option dikhao", "refine_cheaper", category=category, city=city),
            _mt("operator ke sath chahiye", "operator", category=category, city=city),
            _mt(f"{city2} me bhi same", "city_switch", category=category, city=city2),
            _mt("rental policy kya hai", "support", machines_max=0, not_assistant_mode="machine_search"),
            _mt("wapas machine dikhao", "resume_search", category=category, city=city2),
            _mt("dhanyavaad", "thanks", machines_max=0),
        ],
    )


def _multi_category_site(city: str) -> dict:
    city2 = CITY_SWITCH[city]
    cid = f"en_multicat_{city}"
    return conv(
        cid,
        title=f"Multi-category site work {city}",
        lang_mix="english",
        flow_type="multi_city_multi_cat",
        description="Highway project — excavator, crane, roller across cities.",
        turns=[
            _mt("hello", "greeting", machines_max=0),
            _mt("highway project chal raha hai", "none", machines_max=0),
            _mt(f"excavator in {city}", "establish_category", category="excavator", city=city),
            _mt(f"crane in {city}", "establish_category", category="crane", city=city),
            _mt(f"road roller in {city2}", "city_switch", category="road roller", city=city2),
            _mt("cheaper roller", "refine_cheaper", category="road roller", city=city2),
            _mt(f"excavator in {city2} too", "establish_category", category="excavator", city=city2),
            _mt("compare volvo vs komatsu", "compare", machines_max=0),
            _mt(f"show excavator in {city}", "resume_search", category="excavator", city=city),
            _mt("thanks", "thanks", machines_max=0),
        ],
    )


def build_all_conversations() -> list[dict]:
    """Generate 60+ unique conversation scenarios."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(c: dict) -> None:
        if c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)

    # 1) Canonical greet→refine: 9 cities × excavator EN (matches user example)
    for city in CITIES:
        add(_greet_search_refine_en(city, "excavator", "excavator", "50000"))

    # 2) Hinglish greet→refine: 6 cities × varied categories
    for city in CITIES[:6]:
        for cat_slug, category, budget in CATEGORIES[:4]:
            add(_greet_search_refine_hinglish(city, cat_slug.replace(" ", "_"), category))

    # 3) Hindi greet→refine: 5 cities × 3 categories
    for city in CITIES[:5]:
        for cat_slug, category, _ in CATEGORIES[:3]:
            add(_greet_search_refine_hindi(city, cat_slug.replace(" ", "_"), category))

    # 4) Direct search refine: 8 combos
    for city in CITIES[:4]:
        for cat_slug, category, budget in CATEGORIES[2:4]:
            add(_direct_search_refine_en(city, cat_slug.replace(" ", "_"), category, budget))

    # 5) City inventory drill: 6 combos
    for city in CITIES[:3]:
        for cat_slug, category, _ in CATEGORIES[:2]:
            add(_city_inventory_drill(city, cat_slug.replace(" ", "_"), category, "english"))
    for city in CITIES[3:6]:
        add(_city_inventory_drill(city, "excavator", "excavator", "hinglish"))

    # 6) Support interrupt: 8 combos
    for city in CITIES[:4]:
        for cat_slug, category, _ in CATEGORIES[:2]:
            add(_support_interrupt(city, cat_slug.replace(" ", "_"), category, "english"))
    for city in CITIES[4:8]:
        add(_support_interrupt(city, "crane", "crane", "hinglish"))

    # 7) Frustration recovery: 5
    for city in CITIES[:5]:
        add(_frustration_recovery(city, "excavator", "excavator"))

    # 8) Project recommendation: 5
    for city in CITIES[:5]:
        add(_project_recommendation(city, "excavator", "excavator"))

    # 9) Compare then search: 5
    for city in CITIES[:5]:
        add(_compare_then_search(city, "excavator", "excavator"))

    # 10) Vague clarify: 6
    for city in CITIES[:3]:
        add(_vague_clarify(city, "roller", "road roller", "english"))
        add(_vague_clarify(city, "mixer", "concrete mixer", "hinglish"))

    # 11) Mixed language: 5
    for city in CITIES[:5]:
        add(_mixed_lang_switch(city, "excavator", "excavator"))

    # 12) Multi-category site: 4
    for city in CITIES[:4]:
        add(_multi_category_site(city))

    return out


CONVERSATIONS: list[dict] = build_all_conversations()
