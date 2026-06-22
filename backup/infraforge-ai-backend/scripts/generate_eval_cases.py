"""
Generate promptfoo test YAML from structured eval cases (180+ prompts).

Run: python scripts/generate_eval_cases.py
Output: promptfoo/tests/assistant_eval.yaml
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "promptfoo" / "tests"
OUT_JSON = OUT_DIR / "cases.json"
OUT_YAML = OUT_DIR / "assistant_eval.yaml"

# ---------------------------------------------------------------------------
# Test case builder helpers
# ---------------------------------------------------------------------------

def single(
    id_: str,
    message: str,
    *,
    category: str | None = None,
    city: str | None = None,
    mode: str | None = None,
    lang: str | None = None,
    lang_in: list[str] | None = None,
    no_machines: bool = False,
    has_machines: bool = False,
    spell: bool = False,
    msg_contains: str | None = None,
    not_mode: str | None = None,
    session: str | None = None,
    expected_behavior: str | None = None,
) -> dict:
    expect: dict = {}
    if category:
        expect["category"] = category
    if city:
        expect["city"] = city
    if mode:
        expect["assistant_mode"] = mode
    if not_mode:
        expect["not_assistant_mode"] = not_mode
    if lang:
        expect["reply_language"] = lang
    if lang_in:
        expect["reply_language_in"] = lang_in
    if no_machines:
        expect["machines_max"] = 0
    if has_machines:
        expect["machines_min"] = 1
    if spell:
        expect["has_corrections"] = True
    if msg_contains:
        expect["message_contains"] = msg_contains
    case = {
        "id": id_,
        "session_id": session or f"pf_{id_}",
        "clear_session": True,
        "message": message,
        "expect": expect,
    }
    if expected_behavior:
        case["expected_behavior"] = expected_behavior
    return case


def multi(id_: str, turns: list[dict], session: str | None = None) -> dict:
    return {
        "id": id_,
        "session_id": session or f"pf_{id_}",
        "clear_session": True,
        "turns": turns,
    }


def turn(msg: str, **expect) -> dict:
    t = {"message": msg}
    if expect:
        t["expect"] = expect
    return t


# ---------------------------------------------------------------------------
# 180+ eval cases grouped by category
# ---------------------------------------------------------------------------

CASES: list[dict] = []

# --- Greetings (12) ---
for msg in [
    "hi", "hello", "hey", "good morning", "namaste", "hello there",
    "hii", "helo", "hi there", "good evening", "hey there", "hola",
]:
    CASES.append(single(f"greet_{msg.replace(' ', '_')}", msg, mode="greeting", no_machines=True))

# --- Basic search: category + city (55) ---
SEARCHES = [
    ("excavator in delhi", "excavator", "delhi"),
    ("excavator in jaipur", "excavator", "jaipur"),
    ("excavator in mumbai", "excavator", "mumbai"),
    ("excavator in pune", "excavator", "pune"),
    ("excavator in bangalore", "excavator", "bangalore"),
    ("excavator in chennai", "excavator", "chennai"),
    ("excavator in hyderabad", "excavator", "hyderabad"),
    ("excavator in kolkata", "excavator", "kolkata"),
    ("excavator in ahmedabad", "excavator", "ahmedabad"),
    ("crane in jaipur", "crane", "jaipur"),
    ("crane in delhi", "crane", "delhi"),
    ("crane in mumbai", "crane", "mumbai"),
    ("hydra crane in delhi", "hydra crane", "delhi"),
    ("hydra crane in jaipur", "hydra crane", "jaipur"),
    ("road roller in jaipur", "road roller", "jaipur"),
    ("road roller in pune", "road roller", "pune"),
    ("road roller in delhi", "road roller", "delhi"),
    ("crawler drill in jaipur", "crawler drill", "jaipur"),
    ("crawler drill in delhi", "crawler drill", "delhi"),
    ("dump truck in mumbai", "dump truck", "mumbai"),
    ("dump truck in delhi", "dump truck", "delhi"),
    ("bulldozer in jaipur", "bulldozer", "jaipur"),
    ("wheel loader in delhi", "wheel loader", "delhi"),
    ("concrete mixer in mumbai", "concrete mixer", "mumbai"),
    ("grader in jaipur", "motor grader", "jaipur"),
    ("jcb in jaipur", "backhoe loader", "jaipur"),
    ("JCB in Jaipur under 8000", "backhoe loader", "jaipur"),
    ("jcb in delhi", "backhoe loader", "delhi"),
    ("jcb 3dx in jaipur", "backhoe loader", "jaipur"),
    ("backhoe loader in jaipur", "backhoe loader", "jaipur"),
    ("CAT excavator Mumbai", "excavator", "mumbai"),
    ("komatsu excavator delhi", "excavator", "delhi"),
    ("volvo excavator pune", "excavator", "pune"),
    ("terex crane mumbai", "crane", "mumbai"),
    ("poclain in delhi", "excavator", "delhi"),
    ("poclain in jaipur", "excavator", "jaipur"),
    ("mobile crusher in delhi", "mobile crusher", "delhi"),
    ("feller buncher in delhi", "feller buncher", "delhi"),
    ("excavator in jaipur under 8000", "excavator", "jaipur"),
    ("crane in jaipur under 15000", "crane", "jaipur"),
    ("rent excavator in delhi", "excavator", "delhi"),
    ("buy jcb in jaipur", "backhoe loader", "jaipur"),
    ("used excavator in mumbai", "excavator", "mumbai"),
    ("new crane in delhi", "crane", "delhi"),
    ("excavator for rent in pune", "excavator", "pune"),
    ("dumper in jaipur", "dump truck", "jaipur"),
    ("tipper in delhi", "dump truck", "delhi"),
    ("roller in jaipur", "road roller", "jaipur"),
    ("dozer in delhi", "bulldozer", "delhi"),
    ("loader in mumbai", "wheel loader", "mumbai"),
    ("mixer in jaipur", "concrete mixer", "jaipur"),
    ("drill in jaipur", "crawler drill", "jaipur"),
    ("excavator jaipur", "excavator", "jaipur"),
    ("jaipur me excavator", "excavator", "jaipur"),
    ("delhi me crane chahiye", "crane", "delhi"),
]
for i, (msg, cat, city) in enumerate(SEARCHES):
    slug = f"search_{i:03d}"
    CASES.append(single(slug, msg, category=cat, city=city, has_machines=False))

# --- Spell correction (28) ---
SPELL = [
    ("excvator in jaipir", "excavator", "jaipur"),
    ("hydra crne in delih", "hydra crane", "delhi"),
    ("road rolar in pune", "road roller", "pune"),
    ("jcb chahiy", "backhoe loader", None),
    ("dump truk mumbai", "dump truck", "mumbai"),
    ("crawlar dril jaipur", "crawler drill", "jaipur"),
    ("exavator delhi", "excavator", "delhi"),
    ("excavater in jaipur", "excavator", "jaipur"),
    ("crain in mumbai", "crane", "mumbai"),
    ("buldozer jaipur", "bulldozer", "jaipur"),
    ("roler in delhi", "road roller", "delhi"),
    ("jcb in jaiur", "backhoe loader", "jaipur"),
    ("poclain in jaiur", "excavator", "jaipur"),
    ("excavator in nodia", "excavator", "noida"),
    ("crane in banglore", "crane", "bangalore"),
    ("hydra crane in dilli", "hydra crane", "delhi"),
    ("mujhe Crawlre Dril chaiye", "crawler drill", None),
    ("excavtor mumbai", "excavator", "mumbai"),
    ("dumper in mumabi", "dump truck", "mumbai"),
    ("grader in ahmdabad", "motor grader", "ahmedabad"),
    ("mixer in chenai", "concrete mixer", "chennai"),
    ("loader in hydrabad", "wheel loader", "hyderabad"),
    ("excavator in kolkatta", "excavator", "kolkata"),
    ("crane in puna", "crane", "pune"),
    ("jcb in ahemdabad", "backhoe loader", "ahmedabad"),
    ("road roller in japur", "road roller", "jaipur"),
    ("drill in jaypur", "crawler drill", "jaipur"),
    ("nodia", None, "noida"),
]
# Messages where city/category resolve via alias map (corrections optional).
_SPELL_NO_CORRECTIONS = {"hydra crane in dilli", "nodia"}

for i, (msg, cat, city) in enumerate(SPELL):
    slug = f"spell_{i:03d}"
    kw = dict(spell=msg not in _SPELL_NO_CORRECTIONS, not_mode="spell_confirmation")
    if cat:
        kw["category"] = cat
    if city:
        kw["city"] = city
    CASES.append(single(slug, msg, **kw))

# --- Hindi / Hinglish (25) ---
HINGLISH = [
    ("mujhe jaipur ke andar excavator chahiye", "excavator", "jaipur"),
    ("mujhe jaipur ke andar jcb chahiye", "backhoe loader", "jaipur"),
    ("mujhe delhi me crane chahiye", "crane", "delhi"),
    ("mujhe pune me road roller chahiye", "road roller", "pune"),
    ("mujhe mumbai me dump truck chahiye", "dump truck", "mumbai"),
    ("मुझे जयपुर में एक मशीन चाहिए", None, "jaipur", "hindi"),
    ("मुझे दिल्ली में एक्सकेवेटर चाहिए", "excavator", "delhi", "hindi"),
    ("मुझे जयपुर में जेसीबी चाहिए", "backhoe loader", "jaipur", "hindi"),
    ("i want a machine in jaipur", None, "jaipur"),
    ("mujhe sasta excavator chahiye jaipur me", "excavator", "jaipur"),
    ("mujhe jaipur me excavator chahiye", "excavator", "jaipur"),
    ("excavator chahiye delhi me", "excavator", "delhi"),
    ("jcb chaiye jaipur", "backhoe loader", "jaipur"),
    ("crane chaiye mumbai", "crane", "mumbai"),
    ("road roller chaiye", "road roller", None),
    ("mujhe bulldozer chahiye delhi me", "bulldozer", "delhi"),
    ("kya jaipur me excavator available hai", "excavator", "jaipur"),
    ("delhi me koi crane hai kya", "crane", "delhi"),
    ("मेरा बजट 10,000 है", None, None),
    ("mujhe 8000 ke andar excavator chahiye jaipur me", "excavator", "jaipur"),
    ("rent pe excavator chahiye delhi", "excavator", "delhi"),
    ("khareedna hai jcb jaipur me", "backhoe loader", "jaipur"),
    ("मुझे मुंबई में क्रेन चाहिए", "crane", "mumbai", "hindi"),
    ("mujhe hyderabad me loader chahiye", "wheel loader", "hyderabad"),
    ("pune me mixer chahiye", "concrete mixer", "pune"),
]
HINGLISH_LANG_IN = ["english", "hinglish"]
for i, row in enumerate(HINGLISH):
    msg = row[0]
    cat = row[1] if len(row) > 1 else None
    city = row[2] if len(row) > 2 else None
    lang = row[3] if len(row) > 3 else None
    slug = f"hinglish_{i:03d}"
    kw: dict = {}
    if cat:
        kw["category"] = cat
    if city:
        kw["city"] = city
    if lang == "hindi":
        kw["lang"] = "hindi"
    elif lang is None and msg != "मेरा बजट 10,000 है":
        kw["lang_in"] = HINGLISH_LANG_IN
    if msg == "road roller chaiye":
        kw["mode"] = "clarification"
    if msg == "मेरा बजट 10,000 है":
        kw["not_mode"] = "off_topic"
    CASES.append(single(slug, msg, **kw))

# --- Clarification / city-only (15) ---
CASES.append(single("clarify_jaipur", "jaipur", mode="clarification", city="jaipur"))
CASES.append(single("clarify_delhi", "delhi", mode="clarification"))
CASES.append(single("clarify_mumbai", "mumbai", mode="clarification", city="mumbai"))
CASES.append(single("clarify_pune", "pune", mode="clarification", city="pune"))
CASES.append(single("clarify_excavator_no_city", "excavator under 10000", mode="clarification", category="excavator"))
CASES.append(single("clarify_crane_no_city", "crane under 15000", mode="clarification", category="crane"))
CASES.append(single("clarify_jcb_no_city", "jcb chahiye", mode="clarification", category="backhoe loader"))
CASES.append(single("clarify_roller_no_city", "road roller chaiye", mode="clarification", category="road roller"))
CASES.append(single("clarify_drill_no_city", "crawler drill", mode="clarification", category="crawler drill"))
CASES.append(single("clarify_hydra_no_city", "hydra crane", mode="clarification", category="hydra crane"))
CASES.append(single("clarify_dump_no_city", "dump truck", mode="clarification", category="dump truck"))
CASES.append(single("clarify_bulldozer_no_city", "bulldozer", mode="clarification", category="bulldozer"))
CASES.append(single("clarify_loader_no_city", "wheel loader", mode="clarification", category="wheel loader"))
CASES.append(single("clarify_mixer_no_city", "concrete mixer", mode="clarification", category="concrete mixer"))
CASES.append(single("clarify_grader_no_city", "grader", mode="clarification", category="motor grader"))

# --- Off-topic / abusive (12) ---
for i, msg in enumerate([
    "what is the weather today",
    "best action movie in 2026",
    "who won the cricket match",
    "tell me a joke",
    "what is python programming",
    "bitcoin price today",
    "recipe for biryani",
    "latest news headlines",
    "chutiya hai kya",
    "stock market tips",
    "how to lose weight",
    "best netflix series",
]):
    CASES.append(single(f"offtopic_{i:03d}", msg, mode="off_topic", no_machines=True))

# --- Budget / edge (12) ---
CASES.append(single("free_excavator", "can i get excavator for free of cost", msg_contains="free machines are not available"))
CASES.append(single("free_jcb", "free jcb in jaipur", msg_contains="free"))
CASES.append(single("budget_zero", "excavator for 0 rupees", not_mode="search"))
CASES.append(single("list_all_delhi", "what about excavator in delhi list all the machines", category="excavator", city="delhi"))
CASES.append(single("cheaper_options", "show cheaper options", not_mode="off_topic"))
CASES.append(single("under_5000", "excavator under 5000 jaipur", category="excavator", city="jaipur"))
CASES.append(single("under_20000", "crane under 20000 mumbai", category="crane", city="mumbai"))
CASES.append(single("rent_only", "excavator on rent delhi", category="excavator", city="delhi"))
CASES.append(single("buy_only", "buy excavator jaipur", category="excavator", city="jaipur"))
CASES.append(single("used_only", "used jcb delhi", category="backhoe loader", city="delhi"))
CASES.append(single("new_only", "new crane mumbai", category="crane", city="mumbai"))
CASES.append(single("pincode_search", "machine in 302026", not_mode="off_topic"))

# --- Multi-turn conversations (25) ---
MULTI = [
    multi("ctx_same_delhi", [
        turn("crawler drill in jaipur"),
        turn("same in delhi", category="crawler drill", city="delhi"),
    ]),
    multi("ctx_excavator_delhi", [
        turn("excavator in jaipur under 8000"),
        turn("same in delhi", category="excavator", city="delhi"),
    ]),
    multi("ctx_what_about_mumbai", [
        turn("excavator in jaipur under 8000"),
        turn("what about mumbai", category="excavator", city="mumbai"),
    ]),
    multi("ctx_jcb_override", [
        turn("excavator in jaipur under 8000"),
        turn("want a JCB 3DX instead of excavator", category="backhoe loader"),
    ]),
    multi("ctx_roller_pune", [
        turn("road roller chaiye"),
        turn("pune", category="road roller", city="pune"),
    ]),
    multi("ctx_crane_excavator_switch", [
        turn("crane in jaipur"),
        turn("excavator in delhi", category="excavator", city="delhi"),
    ]),
    multi("ctx_roller_jcb_switch", [
        turn("road roller in jaipur"),
        turn("JCB in Ahmedabad", category="backhoe loader", city="ahmedabad"),
    ]),
    multi("ctx_budget_jaipur", [
        turn("excavator under 10000"),
        turn("in jaipur", category="excavator", city="jaipur"),
    ]),
    multi("ctx_city_then_category", [
        turn("jaipur"),
        turn("mujhe Crawlre Dril chaiye", category="crawler drill", city="jaipur"),
    ]),
    multi("ctx_delhi_category_switch", [
        turn("delhi"),
        turn("Mobile Crusher", category="mobile crusher", city="delhi"),
        turn("Feller Buncher", category="feller buncher", city="delhi"),
    ]),
    multi("ctx_need_crane_after_delhi", [
        turn("delhi"),
        turn("need a crane", category="crane", city="delhi"),
    ]),
    multi("ctx_need_crane_after_search", [
        turn("dump truck in delhi"),
        turn("need a crane", category="crane", city="delhi"),
    ]),
    multi("ctx_city_only_after_search", [
        turn("crane in jaipur"),
        turn("delhi", assistant_mode="clarification"),
    ]),
    multi("ctx_hindi_budget", [
        turn("crawler drill in jaipur"),
        turn("मेरा बजट 10,000 है", not_assistant_mode="off_topic"),
    ]),
    multi("ctx_spell_no_trap", [
        turn("excvator in jaipir"),
        turn("no", not_assistant_mode="spell_confirmation"),
    ]),
    multi("ctx_project_pune", [
        turn("road project ke liye best machine kaunsi hai?"),
        turn("3", category="excavator"),
        turn("in pune", category="excavator", city="pune"),
    ]),
    multi("ctx_cheaper", [
        turn("excavator in jaipur under 8000"),
        turn("show cheaper options", category="excavator", city="jaipur"),
    ]),
    multi("ctx_same_hindi", [
        turn("mujhe jaipur me excavator chahiye"),
        turn("delhi me bhi", category="excavator", city="delhi"),
    ]),
    multi("ctx_also_in", [
        turn("jcb in jaipur"),
        turn("also in delhi", category="backhoe loader", city="delhi"),
    ]),
    multi("ctx_under_budget", [
        turn("crane in mumbai"),
        turn("under 12000", category="crane", city="mumbai"),
    ]),
    multi("ctx_brand_switch", [
        turn("CAT excavator Mumbai"),
        turn("komatsu excavator delhi", category="excavator", city="delhi"),
    ]),
    multi("ctx_rent_followup", [
        turn("excavator in delhi"),
        turn("on rent only", category="excavator", city="delhi"),
    ]),
    multi("ctx_purpose_dump", [
        turn("dump truck in jaipur", category="dump truck", city="jaipur"),
    ]),
    multi("ctx_list_all", [
        turn("excavator in delhi"),
        turn("list all machines", category="excavator", city="delhi"),
    ]),
    multi("ctx_switch_city_hinglish", [
        turn("mujhe jaipur ke andar jcb chahiye"),
        turn("mumbai me bhi", category="backhoe loader", city="mumbai"),
    ]),
    multi("ctx_hydra_followup", [
        turn("hydra crane in delhi"),
        turn("cheaper options", category="hydra crane", city="delhi"),
    ]),
    multi("ctx_abusive_after_search", [
        turn("excavator under 10000"),
        turn("chutiya hai kya", assistant_mode="off_topic", machines_max=0),
    ]),
    multi("ctx_how_to_rent", [
        turn("dump truck in delhi"),
        turn(
            "ya this machine is good how to rent it",
            assistant_mode="booking_guidance",
            machines_max=0,
            msg_contains="Contact Owner",
        ),
    ]),
]
CASES.extend(MULTI)

# --- Adversarial / nonsense / irrelevant — response must be logical, not random search ---
ADVERSARIAL = [
    {"msg": "abcxyz", "behavior": "Nonsense — should NOT return random machines", "not_mode": "search", "no_machines": True},
    {"msg": "asdfghjkl", "behavior": "Keyboard mash — clarify or redirect", "not_mode": "search", "no_machines": True},
    {"msg": "???", "behavior": "Punctuation only — ask what user needs", "no_machines": True},
    {"msg": "12345", "behavior": "Numbers only — ask machine + city", "no_machines": True},
    {"msg": "machine", "behavior": "Too vague — ask city and type", "mode": "clarification", "no_machines": True},
    {"msg": "what is 2+2", "behavior": "Math off-topic — redirect to machines", "mode": "off_topic", "no_machines": True},
    {"msg": "sell my house in jaipur", "behavior": "Real estate — off-topic block", "mode": "off_topic", "no_machines": True},
    {"msg": "order pizza mumbai", "behavior": "Food delivery — off-topic block", "mode": "off_topic", "no_machines": True},
    {"msg": "book flight to delhi", "behavior": "Travel — off-topic block", "mode": "off_topic", "no_machines": True},
    {"msg": "who is the prime minister", "behavior": "Politics — off-topic block", "mode": "off_topic", "no_machines": True},
    {"msg": "write python code for me", "behavior": "Coding help — off-topic block", "mode": "off_topic", "no_machines": True},
    {"msg": "random gibberish query test", "behavior": "Gibberish — no machine search", "not_mode": "search", "no_machines": True},
    {"msg": "xyz machine in abc city", "behavior": "Invalid entities — clarify or honest no-result", "no_machines": True},
    {"msg": "jaipur mai excavator chaiye", "behavior": "Valid Hinglish — excavator results in Jaipur", "category": "excavator", "city": "jaipur", "lang_in": ["english", "hinglish"]},
    {"msg": "mujhe kuch bhi machine dedo", "behavior": "Vague Hindi — ask city/category", "mode": "clarification", "no_machines": True},
    {"msg": "cheapest thing available", "behavior": "Vague budget — ask category + city", "mode": "clarification", "no_machines": True},
    {"msg": "show me everything", "behavior": "Too broad — ask city or category", "mode": "clarification", "no_machines": True},
    {"msg": "tell me about quantum physics", "behavior": "Science off-topic — redirect", "mode": "off_topic", "no_machines": True},
    {"msg": "dhoni ka score kya hai", "behavior": "Cricket off-topic — redirect", "mode": "off_topic", "no_machines": True},
]

for i, adv in enumerate(ADVERSARIAL):
    msg = adv.pop("msg")
    behavior = adv.pop("behavior")
    kw = {"expected_behavior": behavior, **adv}
    CASES.append(single(f"adversarial_{i:03d}", msg, **kw))

# --- Project recommendation (5) ---
CASES.append(single("project_road", "road project ke liye best machine kaunsi hai?", mode="recommendation_clarification"))
CASES.append(single("project_earthwork", "earthwork ke liye best machine?", not_mode="off_topic"))
CASES.append(single("project_mining", "mining project ke liye machine?", not_mode="off_topic"))
CASES.append(single("project_construction", "building construction ke liye best machine?", not_mode="off_topic"))
CASES.append(single("project_demolition", "demolition ke liye machine chahiye", not_mode="off_topic"))


def case_to_promptfoo_test(case: dict) -> dict:
    """Convert internal case to promptfoo test entry."""
    if "turns" in case:
        # Multi-turn: encode as JSON var for provider
        return {
            "description": case["id"],
            "vars": {
                "session_id": case["session_id"],
                "clear_session": case.get("clear_session", True),
                "turns_json": json.dumps(case["turns"]),
                "expect_json": json.dumps(case["turns"][-1].get("expect", {})),
            },
            "assert": [
                {
                    "type": "javascript",
                    "value": "JSON.parse(output).pass === true",
                }
            ],
        }
    expect = case.get("expect", {})
    return {
        "description": case["id"],
        "vars": {
            "session_id": case["session_id"],
            "clear_session": case.get("clear_session", True),
            "message": case["message"],
            "expect_json": json.dumps(expect),
        },
        "assert": [
            {
                "type": "javascript",
                "value": "JSON.parse(output).pass === true",
            }
        ],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(CASES, indent=2, ensure_ascii=False), encoding="utf-8")

    tests = [case_to_promptfoo_test(c) for c in CASES]
    yaml_lines = [
        "# Auto-generated — do not edit by hand. Run: python scripts/generate_eval_cases.py",
        f"# Total cases: {len(CASES)}",
        "",
    ]
    for t in tests:
        yaml_lines.append(f"- description: {t['description']}")
        yaml_lines.append("  vars:")
        for k, v in t["vars"].items():
            if isinstance(v, bool):
                yaml_lines.append(f"    {k}: {'true' if v else 'false'}")
            elif isinstance(v, str) and ("\n" in v or '"' in v):
                escaped = json.dumps(v)
                yaml_lines.append(f"    {k}: {escaped}")
            else:
                yaml_lines.append(f"    {k}: {json.dumps(v) if isinstance(v, str) else v}")
        yaml_lines.append("  assert:")
        yaml_lines.append("    - type: javascript")
        yaml_lines.append('      value: JSON.parse(output).pass === true')
        yaml_lines.append("")

    OUT_YAML.write_text("\n".join(yaml_lines), encoding="utf-8")
    print(f"Generated {len(CASES)} cases -> {OUT_JSON}")
    print(f"Generated promptfoo tests -> {OUT_YAML}")


if __name__ == "__main__":
    main()
