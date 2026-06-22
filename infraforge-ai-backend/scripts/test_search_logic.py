"""
Manual test harness for the chatbot search/understanding logic.

Runs a set of representative conversations directly against chatbot_response()
(no HTTP needed) and prints PASS/FAIL for each expectation.

Prerequisites:
- MongoDB configured in .env (MONGODB_URL / DATABASE_NAME)
- Seed data loaded:  python scripts/seed_machines.py
  (the seed adds JCB / Backhoe Loader records in Jaipur, Delhi, etc.)

Run from the project root:
    python scripts/test_search_logic.py

Notes:
- These tests assert the GENERIC rules (category mapping, memory override,
  free-budget, list-all). They do not hard-code machine-specific results.
- The deterministic parser works without any LLM key, so this is reproducible.
"""

import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.database.mongodb import database
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation


_passed = 0
_failed = 0


def check(label: str, condition: bool, detail: str = ""):
    global _passed, _failed
    status = "PASS" if condition else "FAIL"
    if condition:
        _passed += 1
    else:
        _failed += 1
    line = f"  [{status}] {label}"
    if detail:
        line += f"  ->  {detail}"
    print(line)


def _category(resp) -> str:
    return (resp.get("data", {}).get("filters", {}).get("category") or "").lower()


def _city(resp) -> str:
    return (resp.get("data", {}).get("filters", {}).get("city") or "").lower()


def _status(resp) -> dict:
    return resp.get("data", {}).get("search_status", {}) or {}


def _machines(resp) -> list:
    return resp.get("data", {}).get("machines", []) or []


def _categories(resp) -> set:
    return {str(m.get("category", "")).lower() for m in _machines(resp)}


def _has_duplicate_machines(resp) -> bool:
    """True if the same name+city+category appears more than once."""
    seen = set()
    for m in _machines(resp):
        key = (
            str(m.get("name", "")).strip().lower(),
            str(m.get("city", "")).strip().lower(),
            str(m.get("category", "")).strip().lower(),
        )
        if key in seen:
            return True
        seen.add(key)
    return False


async def run():
    print("\n=== InfraForge chatbot search-logic tests ===\n")

    # -- Test 1 & 2: base query + city-switch memory (shared session) --------
    s1 = "logic_test_session_1"
    clear_conversation(s1)
    print("TEST 1: 'excavator in jaipur under 8000'")
    r = await chatbot_response(s1, "excavator in jaipur under 8000", database)
    check("category == excavator", _category(r) == "excavator", _category(r))
    check("city == jaipur", _city(r) == "jaipur", _city(r))
    check(
        "requested_category == excavator",
        (_status(r).get("requested_category") or "").lower() == "excavator",
        str(_status(r).get("requested_category")),
    )
    check(
        "no backhoe loader / jcb shown as direct result",
        "backhoe loader" not in _categories(r),
        f"categories={sorted(_categories(r))}",
    )
    check("no duplicate machines", not _has_duplicate_machines(r))

    print("TEST 2: 'same in delhi' (category retained, city switched)")
    r = await chatbot_response(s1, "same in delhi", database)
    check("category stays excavator", _category(r) == "excavator", _category(r))
    check("city == delhi", _city(r) == "delhi", _city(r))

    # -- Test 3: explicit override 'instead of excavator' --------------------
    s2 = "logic_test_session_2"
    clear_conversation(s2)
    print("TEST 3: context excavator, then 'want a JCB 3DX instead of excavator'")
    await chatbot_response(s2, "excavator in jaipur under 8000", database)
    r = await chatbot_response(s2, "want a JCB 3DX instead of excavator", database)
    check("category == backhoe loader", _category(r) == "backhoe loader", _category(r))
    check("category is NOT excavator", _category(r) != "excavator", _category(r))

    # -- Test 4: JCB strict search -------------------------------------------
    s3 = "logic_test_session_3"
    clear_conversation(s3)
    print("TEST 4: 'JCB in Jaipur under 8000'")
    r = await chatbot_response(s3, "JCB in Jaipur under 8000", database)
    check("category == backhoe loader", _category(r) == "backhoe loader", _category(r))
    check("city == jaipur", _city(r) == "jaipur", _city(r))
    # Any returned machine must be a backhoe loader (never an excavator direct match)
    cats = {str(m.get("category", "")).lower() for m in _machines(r)}
    check(
        "no excavator shown as direct result",
        "excavator" not in cats,
        f"categories={sorted(cats)}",
    )

    # -- Test 5: 'what about mumbai' keeps category --------------------------
    s4 = "logic_test_session_4"
    clear_conversation(s4)
    print("TEST 5: context excavator, then 'what about mumbai'")
    await chatbot_response(s4, "excavator in jaipur under 8000", database)
    r = await chatbot_response(s4, "what about mumbai", database)
    check("category stays excavator", _category(r) == "excavator", _category(r))
    check("city == mumbai", _city(r) == "mumbai", _city(r))

    # -- Test 6: free / unrealistic budget -----------------------------------
    s5 = "logic_test_session_5"
    clear_conversation(s5)
    print("TEST 6: 'can i get excavator for free of cost'")
    r = await chatbot_response(s5, "can i get excavator for free of cost", database)
    msg = (r.get("message") or "").lower()
    check("message says free not available", "free machines are not available" in msg, msg[:60])
    check(
        "fallback_reason == free_or_unrealistic_budget",
        _status(r).get("fallback_reason") == "free_or_unrealistic_budget",
        str(_status(r).get("fallback_reason")),
    )
    check("exact_match_found is False", _status(r).get("exact_match_found") is False)

    # -- Test 7: 'list all' raises the result limit --------------------------
    s6 = "logic_test_session_6"
    clear_conversation(s6)
    print("TEST 7: 'what about excavator in delhi list all the machines'")
    r = await chatbot_response(s6, "what about excavator in delhi list all the machines", database)
    limit = r.get("data", {}).get("context", {}).get("result_limit")
    check(
        "result_limit == 20 OR more than 5 machines",
        limit == 20 or len(_machines(r)) > 5,
        f"result_limit={limit}, machines={len(_machines(r))}",
    )

    # -- Test 8: Hinglish excavator request ----------------------------------
    s7 = "logic_test_session_7"
    clear_conversation(s7)
    print("TEST 8: 'mujhe jaipur ke andar excavator chahiye'")
    r = await chatbot_response(s7, "mujhe jaipur ke andar excavator chahiye", database)
    check("category == excavator", _category(r) == "excavator", _category(r))
    check("city == jaipur", _city(r) == "jaipur", _city(r))

    # -- Test 9: Hinglish JCB request ----------------------------------------
    s8 = "logic_test_session_8"
    clear_conversation(s8)
    print("TEST 9: 'mujhe jaipur ke andar jcb chahiye'")
    r = await chatbot_response(s8, "mujhe jaipur ke andar jcb chahiye", database)
    check("category == backhoe loader", _category(r) == "backhoe loader", _category(r))
    check("city == jaipur", _city(r) == "jaipur", _city(r))
    check(
        "no excavator shown as direct result",
        "excavator" not in _categories(r),
        f"categories={sorted(_categories(r))}",
    )

    # -- Test 10: JCB direct results are backhoe loaders + de-duplicated ------
    s9 = "logic_test_session_9"
    clear_conversation(s9)
    print("TEST 10: 'jcb in jaipur' direct results all backhoe loader, no dupes")
    r = await chatbot_response(s9, "jcb in jaipur", database)
    cats = _categories(r)
    check(
        "direct categories ⊆ {backhoe loader}",
        cats.issubset({"backhoe loader"}) and bool(cats),
        f"categories={sorted(cats)}",
    )
    check("no duplicate machines", not _has_duplicate_machines(r))

    print(f"\n=== SUMMARY: {_passed} passed, {_failed} failed ===\n")
    return _failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
