"""
Score how well an assistant response matches the user query.

Used by run_assistant_eval.py to produce optimization-focused reports:
  - actual reply text visible per query
  - per-dimension match scores (0–100)
  - issues + improvement hints for low-scoring responses
  - optional Groq LLM-as-judge for semantic relevance
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.chatbot.language import detect_query_language

# ---------------------------------------------------------------------------
# Response extraction
# ---------------------------------------------------------------------------

def extract_reply(resp: dict) -> str:
    parts = []
    msg = (resp.get("message") or "").strip()
    if msg:
        parts.append(msg)
    data = resp.get("data") or {}
    advisor = (data.get("advisor_message") or "").strip()
    if advisor and advisor not in msg:
        parts.append(advisor)
    return "\n".join(parts).strip()


def extract_meta(resp: dict) -> dict:
    data = resp.get("data") or {}
    ctx = data.get("context") or {}
    filters = data.get("filters") or {}
    machines = data.get("machines") or []
    return {
        "assistant_mode": ctx.get("assistant_mode") or data.get("assistant_mode") or "",
        "reply_language": ctx.get("reply_language") or "",
        "category": (filters.get("category") or "").lower(),
        "city": (filters.get("city") or "").lower(),
        "max_price": filters.get("max_price"),
        "brand": filters.get("brand"),
        "machines_count": len(machines),
        "machine_names": [m.get("name", "") for m in machines[:5]],
        "suggestions": data.get("suggestions") or [],
        "used_previous_context": bool(ctx.get("used_previous_context")),
        "corrected_query": ctx.get("corrected_query"),
        "corrections": ctx.get("corrections") or [],
        "search_status": data.get("search_status") or {},
    }


# ---------------------------------------------------------------------------
# Heuristic scorers (0–100 each)
# ---------------------------------------------------------------------------

_CATEGORY_WORDS = {
    "excavator": ["excavator", "poclain", "digger"],
    "backhoe loader": ["backhoe", "jcb", "loader"],
    "crane": ["crane"],
    "hydra crane": ["hydra", "crane"],
    "road roller": ["roller", "roller"],
    "crawler drill": ["drill", "crawler"],
    "dump truck": ["dump", "truck", "dumper", "tipper"],
    "bulldozer": ["bulldozer", "dozer"],
    "motor grader": ["grader"],
    "wheel loader": ["loader"],
    "concrete mixer": ["mixer", "concrete"],
    "mobile crusher": ["crusher"],
    "feller buncher": ["feller", "buncher"],
}

_CITY_DISPLAY = {
    "jaipur": ["jaipur", "jaypur", "japur"],
    "delhi": ["delhi", "dilli", "new delhi"],
    "mumbai": ["mumbai", "bombay"],
    "pune": ["pune", "puna"],
    "bangalore": ["bangalore", "bengaluru", "banglore"],
    "hyderabad": ["hyderabad", "hydrabad"],
    "chennai": ["chennai", "chenai"],
    "kolkata": ["kolkata", "calcutta", "kolkatta"],
    "ahmedabad": ["ahmedabad", "ahmdabad", "ahemdabad"],
    "noida": ["noida", "nodia"],
}


def _text_has_any(text: str, words: list[str]) -> bool:
    lower = text.lower()
    return any(w in lower for w in words)


def score_intent_match(meta: dict, expect: dict, *, structural_pass: bool) -> tuple[int, list[str]]:
    """Filters / mode alignment with expected behaviour."""
    if not expect:
        return (95 if meta.get("assistant_mode") else 70, [])

    issues = []
    score = 100

    if "category" in expect:
        want = expect["category"].lower()
        got = meta.get("category") or ""
        if got != want:
            score -= 40
            issues.append(f"Category mismatch: got '{got or 'none'}', expected '{want}'")

    if "city" in expect:
        want = expect["city"].lower()
        got = meta.get("city") or ""
        if got != want:
            score -= 35
            issues.append(f"City mismatch: got '{got or 'none'}', expected '{want}'")

    if "assistant_mode" in expect:
        want = expect["assistant_mode"]
        got = meta.get("assistant_mode") or ""
        if got != want:
            score -= 30
            issues.append(f"Mode mismatch: got '{got}', expected '{want}'")

    if expect.get("not_assistant_mode"):
        bad = expect["not_assistant_mode"]
        if meta.get("assistant_mode") == bad:
            score -= 40
            issues.append(f"Should not be mode '{bad}'")

    if expect.get("machines_max") is not None:
        n = meta.get("machines_count", 0)
        if n > expect["machines_max"]:
            score -= 25
            issues.append(f"Too many machines ({n})")

    if expect.get("machines_min") is not None:
        n = meta.get("machines_count", 0)
        if n < expect["machines_min"]:
            score -= 25
            issues.append(f"Too few machines ({n})")

    if structural_pass and score < 100:
        score = max(score, 85)

    return max(0, min(100, score)), issues


def score_response_relevance(
    query: str,
    reply: str,
    meta: dict,
    expect: dict,
) -> tuple[int, list[str]]:
    """Does the reply text talk about what the user asked?"""
    if not reply:
        return 0, ["Empty response"]

    issues = []
    score = 70
    lower_reply = reply.lower()
    lower_query = query.lower()

    # Query entities should appear in reply (or close variant).
    for token in re.findall(r"[a-zA-Z\u0900-\u097F]{3,}", lower_query):
        if token in ("the", "and", "for", "under", "with", "chahiye", "chaiye", "mujhe"):
            continue
        if token in lower_reply:
            score += 3

    cat = expect.get("category") or meta.get("category")
    if cat:
        words = _CATEGORY_WORDS.get(cat.lower(), [cat.split()[0]])
        if _text_has_any(lower_reply, words):
            score += 15
        else:
            issues.append(f"Reply doesn't mention '{cat}'")

    city = expect.get("city") or meta.get("city")
    if city:
        variants = _CITY_DISPLAY.get(city.lower(), [city])
        if _text_has_any(lower_reply, variants):
            score += 15
        else:
            issues.append(f"Reply doesn't mention city '{city}'")

    mode = meta.get("assistant_mode", "")
    if mode == "clarification":
        if any(w in lower_reply for w in ("city", "which", "where", "kahan", "शहर", "कहाँ", "कौन")):
            score += 10
        else:
            issues.append("Clarification reply should ask city/category clearly")

    if mode == "greeting":
        if any(w in lower_reply for w in ("hello", "hi", "namaste", "help", "machine", "नमस्ते", "मदद")):
            score += 15
        else:
            issues.append("Greeting should welcome and guide user")

    if mode in ("search", "no_result", "purpose_alternatives") and meta.get("machines_count", 0) > 0:
        if any(w in lower_reply for w in ("found", "here", "match", "available", "उपलब्ध", "मिल")):
            score += 10
        if meta.get("machine_names"):
            if any(n.lower() in lower_reply for n in meta["machine_names"] if n):
                score += 10

    if mode == "off_topic":
        if any(w in lower_reply for w in ("machine", "infraforge", "construction", "equipment", "मशीन")):
            score += 10
        else:
            issues.append("Off-topic reply should redirect to machines")

    return max(0, min(100, score)), issues


def score_language_match(query: str, reply: str, meta: dict, expect: dict) -> tuple[int, list[str]]:
    issues = []
    query_lang = detect_query_language(query)
    reply_lang = meta.get("reply_language") or ""

    if "reply_language" in expect:
        want = expect["reply_language"]
        if reply_lang == want:
            return 100, []
        issues.append(f"Reply language '{reply_lang}' != expected '{want}'")
        return 50, issues

    if "reply_language_in" in expect:
        allowed = expect["reply_language_in"]
        if reply_lang in allowed:
            return 100, []
        issues.append(f"Reply language '{reply_lang}' not in {allowed}")
        return 55, issues

    # Heuristic script match
    dev_reply = len(re.findall(r"[\u0900-\u097F]", reply))
    dev_query = len(re.findall(r"[\u0900-\u097F]", query))

    if query_lang == "hindi":
        if dev_reply > 5:
            return 100, []
        issues.append("Hindi query should get Hindi (Devanagari) reply")
        return 40, issues

    if query_lang in ("english", "hinglish"):
        if dev_reply > 20 and dev_query == 0:
            issues.append("English/Hinglish query got mostly Hindi reply")
            return 60, issues
        return 95, []

    return 80, issues


def score_result_quality(meta: dict, expect: dict) -> tuple[int, list[str]]:
    """Are machines / suggestions appropriate for the intent?"""
    mode = meta.get("assistant_mode", "")
    n = meta.get("machines_count", 0)
    issues = []

    if mode == "greeting" and n > 0:
        return 30, ["Greeting should not return machines"]

    if mode == "off_topic" and n > 0:
        return 20, ["Off-topic should not return machines"]

    if mode == "clarification":
        if meta.get("suggestions"):
            return 95, []
        if n > 0:
            return 50, ["Clarification should ask before searching"]
        return 75, ["Clarification without suggestion chips"]

    if mode in ("search", "purpose_alternatives", "no_result", "project_recommendation"):
        if n > 0:
            return min(100, 80 + min(n, 5) * 4), []
        if mode == "no_result":
            return 85, []
        if expect.get("machines_min"):
            return 30, ["Expected machines but got none"]
        return 65, ["Search mode but no machines returned"]

    return 85, issues


def score_helpfulness(reply: str, meta: dict) -> tuple[int, list[str]]:
    issues = []
    if not reply:
        return 0, ["No reply text"]

    score = 60
    words = len(reply.split())

    if words < 5:
        issues.append("Reply too short — add more guidance")
        score -= 20
    elif words >= 12:
        score += 15

    if meta.get("suggestions"):
        score += 15

    if meta.get("machines_count", 0) > 0 and ("₹" in reply or "price" in reply.lower() or "day" in reply.lower()):
        score += 10

    generic_only = reply.lower().strip() in ("ok", "okay", "yes", "no", "done")
    if generic_only:
        return 20, ["Reply is too generic"]

    return max(0, min(100, score)), issues


def describe_expected_behavior(expect: dict, case: Optional[dict] = None) -> str:
    """Human-readable description of what a good response should do."""
    if case and case.get("expected_behavior"):
        return case["expected_behavior"]

    mode = expect.get("assistant_mode")
    cat = expect.get("category")
    city = expect.get("city")

    if mode == "off_topic":
        return "Politely refuse — redirect user to construction machines (no search, no machines)"
    if mode == "greeting":
        return "Welcome user and ask machine type + city (no machine list)"
    if mode == "clarification":
        if cat and not city:
            return f"Ask which CITY for {cat} (do not guess city)"
        if city and not cat:
            return f"Ask which MACHINE TYPE in {city.title()}"
        return "Ask missing detail (city or machine type) before searching"
    if mode == "recommendation_clarification":
        return "Ask project type (road, earthwork, etc.) before recommending"
    if mode == "booking_guidance":
        return "Guide user to Contact Owner on machine card — no new search"
    if cat and city:
        return f"Show relevant {cat} machines in {city.title()} with prices/details"
    if cat:
        return f"Search or ask city for {cat}"
    if expect.get("message_contains"):
        return f"Reply must explain: {expect['message_contains']}"
    if expect.get("not_assistant_mode") == "search":
        return "Should NOT run a blind machine search — clarify or redirect"
    return "Logical, relevant reply matching user intent"


_VAGUE_QUERY_PATTERNS = (
    r"^machine[\s!.?]*$",
    r"show\s+me\s+everything",
    r"kuch\s+bhi.*machine",
    r"koi\s+bhi.*machine",
    r"xyz\s+machine",
    r"abc\s+city",
    r"^cheapest\s+thing",
    r"mujhe\s+kuch\s+bhi\s+machine",
)


def _is_vague_query(query: str) -> bool:
    lower = (query or "").strip().lower()
    return any(re.search(p, lower) for p in _VAGUE_QUERY_PATTERNS)


def compute_verdict(
    query: str,
    reply: str,
    meta: dict,
    expect: dict,
    scores: dict,
    issues: list,
    *,
    expected_behavior: str = "",
) -> dict:
    """
    Human verdict: is this response relevant and logical for this query?
    """
    mode = meta.get("assistant_mode", "")
    n = meta.get("machines_count", 0)
    overall = scores.get("overall", 0)
    rel = scores.get("response_relevance", 0)

    # Vague / gibberish queries must not return machine listings.
    if _is_vague_query(query) and n > 0:
        return {
            "verdict": "WRONG",
            "logical": False,
            "summary": "Vague query triggered blind machine search",
            "analyze": "Assistant should ask city and machine type — not return random machines.",
        }
    if _is_vague_query(query) and mode == "search" and n > 0:
        return {
            "verdict": "WRONG",
            "logical": False,
            "summary": "Vague query should clarify, not search",
            "analyze": expected_behavior or "Too vague — ask city and category first.",
        }

    # Off-topic with city keyword (pizza, house sale) must not show machine chips.
    if expect.get("assistant_mode") == "off_topic" and mode == "clarification" and n == 0:
        if re.search(r"\b(pizza|house|property|flight)\b", query, re.I):
            return {
                "verdict": "WRONG",
                "logical": False,
                "summary": "Non-machine query treated as city clarification",
                "analyze": "Should politely redirect to construction machines.",
            }

    # Hard failures — logically wrong
    if expect.get("assistant_mode") == "off_topic" and mode not in ("off_topic", "abusive", "acknowledgment"):
        return {
            "verdict": "WRONG",
            "logical": False,
            "summary": f"Off-topic query got '{mode}' instead of redirect",
            "analyze": "User asked non-machine question but assistant searched or gave irrelevant answer.",
        }
    if expect.get("not_assistant_mode") == "search" and mode == "search" and n > 0:
        return {
            "verdict": "WRONG",
            "logical": False,
            "summary": "Nonsense/vague query triggered random machine search",
            "analyze": "Assistant should clarify or redirect — not return machines for gibberish.",
        }
    if expect.get("assistant_mode") == "greeting" and n > 0:
        return {
            "verdict": "WRONG",
            "logical": False,
            "summary": "Greeting returned machine results",
            "analyze": "Hi/hello should only welcome — no search.",
        }
    if expect.get("machines_max") == 0 and n > 0:
        return {
            "verdict": "WRONG",
            "logical": False,
            "summary": f"Returned {n} machines when none expected",
            "analyze": expected_behavior or "This query type should not show machines.",
        }

    # Category/city search expectations
    if expect.get("category") and expect.get("city"):
        got_cat = meta.get("category", "")
        got_city = meta.get("city", "")
        if got_cat != expect["category"].lower() or got_city != expect["city"].lower():
            return {
                "verdict": "WRONG",
                "logical": False,
                "summary": f"Wrong filters: {got_cat or '?'} in {got_city or '?'}",
                "analyze": f"Expected {expect['category']} in {expect['city']}.",
            }

    # Correct search — filters match (mode may be blank on some code paths)
    if expect.get("category") and expect.get("city"):
        if (
            meta.get("category") == expect["category"].lower()
            and meta.get("city") == expect["city"].lower()
            and overall >= 80
            and mode in ("search", "no_result", "purpose_alternatives", "", "project_recommendation")
        ):
            return {
                "verdict": "RELEVANT",
                "logical": True,
                "summary": "Correct search response for category + city",
                "analyze": _analysis_text(query, reply, meta, expected_behavior),
            }

    if expect.get("assistant_mode") == mode and mode in (
        "greeting", "clarification", "off_topic", "recommendation_clarification",
    ) and overall >= 82:
        return {
            "verdict": "RELEVANT",
            "logical": True,
            "summary": f"Correct {mode} response",
            "analyze": _analysis_text(query, reply, meta, expected_behavior),
        }

    # Purpose-clarification trap when user already gave category + city.
    if (
        mode == "purpose_clarification"
        and expect.get("category")
        and expect.get("city")
        and "what will you use" in reply.lower()
    ):
        return {
            "verdict": "PARTIAL",
            "logical": True,
            "summary": "Correct city/category but forced purpose menu",
            "analyze": "User already specified machine + city — show no-result or in-city alternatives instead of a 6-option purpose loop.",
        }

    # Scoring-based verdict
    if overall >= 85 and rel >= 75:
        return {
            "verdict": "RELEVANT",
            "logical": True,
            "summary": "Response matches query — relevant and logical",
            "analyze": _analysis_text(query, reply, meta, expected_behavior),
        }
    if overall >= 65 or rel >= 65:
        return {
            "verdict": "PARTIAL",
            "logical": True,
            "summary": "Mostly OK but missing detail in reply text",
            "analyze": "; ".join(issues[:3]) if issues else "Wording could better reflect parsed intent.",
        }
    return {
        "verdict": "NEEDS_FIX",
        "logical": False,
        "summary": "Response does not adequately match query",
        "analyze": "; ".join(issues[:4]) if issues else "Low relevance score — review reply templates.",
    }


def _analysis_text(query: str, reply: str, meta: dict, expected: str) -> str:
    parts = []
    if meta.get("machines_count"):
        names = ", ".join(meta.get("machine_names") or [])[:80]
        parts.append(f"Returned {meta['machines_count']} machine(s)" + (f": {names}" if names else ""))
    elif meta.get("assistant_mode") == "clarification":
        parts.append("Asked for clarification (correct)")
    elif meta.get("assistant_mode") == "off_topic":
        parts.append("Blocked off-topic correctly")
    if expected:
        parts.append(f"Expected: {expected}")
    return " · ".join(parts) if parts else "Reply aligns with query intent."


def compute_quality_scores(
    query: str,
    resp: dict,
    expect: dict,
    *,
    structural_pass: bool,
    case: Optional[dict] = None,
) -> dict:
    reply = extract_reply(resp)
    meta = extract_meta(resp)

    intent_s, intent_issues = score_intent_match(meta, expect, structural_pass=structural_pass)
    rel_s, rel_issues = score_response_relevance(query, reply, meta, expect)
    lang_s, lang_issues = score_language_match(query, reply, meta, expect)
    result_s, result_issues = score_result_quality(meta, expect)
    help_s, help_issues = score_helpfulness(reply, meta)

    weights = {
        "intent_match": 0.30,
        "response_relevance": 0.30,
        "language_match": 0.15,
        "result_quality": 0.15,
        "helpfulness": 0.10,
    }
    scores = {
        "intent_match": intent_s,
        "response_relevance": rel_s,
        "language_match": lang_s,
        "result_quality": result_s,
        "helpfulness": help_s,
    }
    overall = round(sum(scores[k] * weights[k] for k in weights))

    all_issues = intent_issues + rel_issues + lang_issues + result_issues + help_issues
    optimize = overall < 75 or len(all_issues) >= 2

    hints = _optimization_hints(scores, all_issues, meta)
    expected_behavior = describe_expected_behavior(expect, case)
    scores_with_overall = {**scores, "overall": overall}
    verdict_info = compute_verdict(
        query, reply, meta, expect, scores_with_overall, all_issues,
        expected_behavior=expected_behavior,
    )
    if verdict_info["verdict"] in ("WRONG", "NEEDS_FIX"):
        optimize = True

    return {
        "reply": reply,
        "meta": meta,
        "scores": scores,
        "overall": overall,
        "issues": all_issues,
        "optimize": optimize,
        "optimization_hints": hints,
        "expected_behavior": expected_behavior,
        "verdict": verdict_info["verdict"],
        "logical": verdict_info["logical"],
        "verdict_summary": verdict_info["summary"],
        "analysis": verdict_info["analyze"],
    }


def _optimization_hints(scores: dict, issues: list, meta: dict) -> list[str]:
    hints = []
    if scores["response_relevance"] < 70:
        hints.append("Reply should explicitly mention the machine type and city the user asked for.")
    if scores["language_match"] < 70:
        hints.append("Match reply language to the user's query (Hindi/Hinglish/English).")
    if scores["intent_match"] < 70:
        hints.append("Fix intent resolver — filters or assistant_mode don't match user intent.")
    if scores["result_quality"] < 70:
        hints.append("Improve search results or clarification flow before returning empty/generic answers.")
    if scores["helpfulness"] < 70:
        hints.append("Add suggestion chips, price info, or a clearer next-step question.")
    if meta.get("assistant_mode") == "clarification" and not meta.get("suggestions"):
        hints.append("Show DB-driven category/city chips during clarification.")
    if not hints and issues:
        hints.append("Review reply wording — logic is OK but text doesn't reflect it well.")
    return hints[:4]


# ---------------------------------------------------------------------------
# Optional Groq LLM judge
# ---------------------------------------------------------------------------

def groq_judge_available() -> bool:
    from app.core.config import settings
    return bool(settings.GROQ_API_KEY)


async def groq_judge_scores(query: str, reply: str, meta: dict) -> Optional[dict]:
    """Semantic relevance judge via Groq (optional). Returns None if unavailable."""
    if not groq_judge_available() or not reply:
        return None
    try:
        from app.core.groq_client import client

        prompt = f"""You evaluate an AI construction-equipment marketplace assistant.

USER QUERY:
{query}

ASSISTANT REPLY:
{reply}

CONTEXT (parsed by backend):
- mode: {meta.get('assistant_mode')}
- category: {meta.get('category')}
- city: {meta.get('city')}
- machines returned: {meta.get('machines_count')}

Score 0-100 on each dimension and explain briefly in JSON only:
{{
  "relevance": <does reply answer what user asked?>,
  "completeness": <enough useful detail?>,
  "clarity": <easy to understand?>,
  "actionability": <clear next step for user?>,
  "overall": <weighted average>,
  "summary": "<one sentence: what is good or bad>",
  "improve": "<one concrete fix for the developer>"
}}"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()
        # Extract JSON from markdown fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
