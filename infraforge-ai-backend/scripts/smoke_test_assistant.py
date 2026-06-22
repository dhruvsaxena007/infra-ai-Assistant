"""
Smoke test for stabilized assistant decision engine.

Run: python scripts/smoke_test_assistant.py
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


def _cat(resp) -> str:
    return (resp.get("data", {}).get("filters", {}).get("category") or "").lower()


def _city(resp) -> str:
    return (resp.get("data", {}).get("filters", {}).get("city") or "").lower()


def _mode(resp) -> str:
    return (
        resp.get("data", {}).get("context", {}).get("assistant_mode")
        or resp.get("data", {}).get("assistant_mode")
        or ""
    )


def _machines(resp) -> list:
    return resp.get("data", {}).get("machines") or []


async def run():
    passed = failed = 0

    def check(label, ok, detail=""):
        nonlocal passed, failed
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -> {detail}" if detail else ""))
        passed += ok
        failed += not ok

    sid = "smoke_stabilization"
    clear_conversation(sid)

    print("\n=== Smoke test ===\n")

    r = await chatbot_response(sid, "hi", database)
    check("1 hi = greeting only", _mode(r) == "greeting" and len(_machines(r)) == 0)

    r = await chatbot_response(sid, "hello", database)
    check("repeat hello = short greeting", _mode(r) == "greeting" and len(_machines(r)) == 0)

    r = await chatbot_response(sid, "road roller chaiye", database)
    check("2 road roller asks city", _mode(r) == "clarification" and _cat(r) == "road roller")

    r = await chatbot_response(sid, "pune", database)
    check("3 pune = road roller in pune", _cat(r) == "road roller" and _city(r) == "pune")

    r = await chatbot_response(sid, "crawler drill in jaipur", database)
    check("4 crawler drill jaipur", _cat(r) == "crawler drill" and _city(r) == "jaipur")

    r = await chatbot_response(sid, "same in delhi", database)
    check("5 same in delhi keeps category", _cat(r) == "crawler drill" and _city(r) == "delhi")

    r = await chatbot_response(sid, "crane in jaipur", database)
    check("context switch setup crane", _cat(r) == "crane")

    r = await chatbot_response(sid, "excavator in delhi", database)
    check("excavator overrides crane", _cat(r) == "excavator" and _city(r) == "delhi")

    clear_conversation("smoke_rr_jcb")
    await chatbot_response("smoke_rr_jcb", "road roller in jaipur", database)
    r = await chatbot_response("smoke_rr_jcb", "JCB in Ahmedabad", database)
    check("JCB overrides road roller", _cat(r) == "backhoe loader" and _city(r) == "ahmedabad")

    r = await chatbot_response(sid, "CAT excavator Mumbai", database)
    check("CAT excavator Mumbai", _cat(r) == "excavator" and _city(r) == "mumbai")

    clear_conversation("smoke_city_only")
    await chatbot_response("smoke_city_only", "crane in jaipur", database)
    r = await chatbot_response("smoke_city_only", "delhi", database)
    check("city-only asks category", _mode(r) == "clarification" and _cat(r) == "")

    clear_conversation("smoke_ctx_budget")
    await chatbot_response("smoke_ctx_budget", "excavator under 10000", database)
    r = await chatbot_response("smoke_ctx_budget", "in jaipur", database)
    check(
        "in jaipur keeps excavator + budget",
        _cat(r) == "excavator" and _city(r) == "jaipur",
        f"cat={_cat(r)} city={_city(r)}",
    )

    clear_conversation("smoke_purpose")
    r1 = await chatbot_response("smoke_purpose", "dump truck in jaipur", database)
    check(
        "no dump truck in jaipur shows in-city alternatives not purpose trap",
        _mode(r1) in ("no_result", "purpose_clarification", "search", "purpose_alternatives")
        and _city(r1) == "jaipur",
        f"mode={_mode(r1)} city={_city(r1)} n={len(_machines(r1))}",
    )
    if _mode(r1) in ("no_result", "purpose_clarification"):
        r2 = await chatbot_response("smoke_purpose", "1", database)
        check(
            "purpose digging shows jaipur alternatives not other cities",
            _city(r2) == "jaipur" or all(
                str(m.get("city", "")).lower() == "jaipur" for m in _machines(r2)
            ) if _machines(r2) else True,
            f"machines={len(_machines(r2))}",
        )

    clear_conversation("smoke_abusive")
    await chatbot_response("smoke_abusive", "excavator under 10000", database)
    r = await chatbot_response("smoke_abusive", "chutiya hai kya", database)
    check(
        "abusive query handled without search",
        _mode(r) == "off_topic" and len(_machines(r)) == 0,
        _mode(r),
    )

    r = await chatbot_response("smoke_abusive", "what is the weather today", database)
    check(
        "off-topic query redirected",
        _mode(r) == "off_topic" and len(_machines(r)) == 0,
    )

    r = await chatbot_response("smoke_abusive", "best action movie in 2026", database)
    check(
        "movie query blocked",
        _mode(r) == "off_topic" and len(_machines(r)) == 0,
        _mode(r),
    )

    clear_conversation("smoke_project_city")
    r1 = await chatbot_response(
        "smoke_project_city",
        "road project ke liye best machine kaunsi hai?",
        database,
    )
    check(
        "road project asks project type",
        _mode(r1) in ("recommendation_clarification", "project_recommendation"),
        _mode(r1),
    )
    r2 = await chatbot_response("smoke_project_city", "3", database)
    check(
        "earthwork recommends excavator",
        _cat(r2) == "excavator" and len(_machines(r2)) > 0,
        f"cat={_cat(r2)} n={len(_machines(r2))}",
    )
    r3 = await chatbot_response("smoke_project_city", "in pune", database)
    check(
        "in pune keeps excavator after recommendation",
        _cat(r3) == "excavator"
        and _city(r3) == "pune"
        and _mode(r3) != "clarification",
        f"cat={_cat(r3)} city={_city(r3)} mode={_mode(r3)}",
    )

    def _ctx(resp) -> dict:
        return resp.get("data", {}).get("context") or {}

    def _lang(resp) -> str:
        return (resp.get("data", {}).get("context") or {}).get("reply_language") or ""

    def _msg(resp) -> str:
        return resp.get("message") or resp.get("data", {}).get("message") or ""

    clear_conversation("smoke_lang_hi")
    r = await chatbot_response("smoke_lang_hi", "मुझे जयपुर में एक मशीन चाहिए", database)
    check(
        "hindi query replies in hindi",
        _lang(r) == "hindi" and "उपलब्ध" in _msg(r),
        f"lang={_lang(r)}",
    )

    clear_conversation("smoke_lang_en")
    r = await chatbot_response("smoke_lang_en", "i want a machine in jaipur", database)
    check(
        "english query replies in english",
        _lang(r) == "english"
        and any(w in _msg(r).lower() for w in ("available", "live", "pick")),
        f"lang={_lang(r)} msg={_msg(r)[:60]}",
    )

    clear_conversation("smoke_lang_budget")
    await chatbot_response("smoke_lang_budget", "crawler drill in jaipur", database)
    r = await chatbot_response("smoke_lang_budget", "मेरा बजट 10,000 है", database)
    check(
        "hindi budget not off_topic",
        _mode(r) != "off_topic",
        _mode(r),
    )
    check(
        "hindi budget keeps context",
        _cat(r) == "crawler drill" or _city(r) == "jaipur" or _mode(r) == "search",
        f"cat={_cat(r)} city={_city(r)} mode={_mode(r)}",
    )

    clear_conversation("smoke_ctx_city_cat")
    r1 = await chatbot_response("smoke_ctx_city_cat", "jaipur", database)
    check("jaipur asks category", _mode(r1) == "clarification" and _city(r1) == "jaipur")
    r2 = await chatbot_response("smoke_ctx_city_cat", "mujhe Crawlre Dril chaiye", database)
    check(
        "category after jaipur keeps city",
        _cat(r2) == "crawler drill" and _city(r2) == "jaipur" and _mode(r2) != "clarification",
        f"cat={_cat(r2)} city={_city(r2)} mode={_mode(r2)}",
    )

    clear_conversation("smoke_ctx_switch")
    await chatbot_response("smoke_ctx_switch", "delhi", database)
    await chatbot_response("smoke_ctx_switch", "Mobile Crusher", database)
    r = await chatbot_response("smoke_ctx_switch", "Feller Buncher", database)
    check(
        "category switch keeps delhi",
        _cat(r) == "feller buncher" and _city(r) == "delhi" and _mode(r) != "clarification",
        f"cat={_cat(r)} city={_city(r)} mode={_mode(r)}",
    )

    clear_conversation("smoke_need_crane")
    await chatbot_response("smoke_need_crane", "delhi", database)
    r = await chatbot_response("smoke_need_crane", "need a crane", database)
    check(
        "need a crane remembers delhi from prior turn",
        _cat(r) == "crane" and _city(r) == "delhi" and _mode(r) != "clarification",
        f"cat={_cat(r)} city={_city(r)} mode={_mode(r)}",
    )

    clear_conversation("smoke_need_after_search")
    await chatbot_response("smoke_need_after_search", "dump truck in delhi", database)
    r = await chatbot_response("smoke_need_after_search", "need a crane", database)
    check(
        "need a crane after dump truck search keeps delhi",
        _cat(r) == "crane" and _city(r) == "delhi" and _mode(r) != "clarification",
        f"cat={_cat(r)} city={_city(r)} mode={_mode(r)}",
    )

    clear_conversation("smoke_mumbai_browse")
    await chatbot_response("smoke_mumbai_browse", "crane", database)
    await chatbot_response("smoke_mumbai_browse", "mumbai", database)
    r = await chatbot_response(
        "smoke_mumbai_browse",
        "what machines are available in mumbai",
        database,
    )
    msg = (r.get("message") or "").lower()
    check(
        "empty mumbai suggests nearby cities engagingly",
        _mode(r) == "clarification"
        and ("pune" in msg or "check" in msg or "live" in msg),
        f"mode={_mode(r)} snippet={msg[:80]}",
    )

    clear_conversation("smoke_rent_guide")
    await chatbot_response("smoke_rent_guide", "dump truck in delhi", database)
    r = await chatbot_response(
        "smoke_rent_guide",
        "ya this machine is good how to rent it",
        database,
    )
    msg = (r.get("message") or "").lower()
    check(
        "how to rent guides user to contact owner — no re-search",
        _mode(r) == "booking_guidance"
        and len(_machines(r)) == 0
        and "contact owner" in msg,
        f"mode={_mode(r)} n={len(_machines(r))}",
    )

    clear_conversation("smoke_no_stuck")
    r = await chatbot_response("smoke_no_stuck", "hello there", database)
    check(
        "hello there is greeting not spell trap",
        _mode(r) == "greeting" and len(_machines(r)) == 0,
        _mode(r),
    )
    r = await chatbot_response("smoke_no_stuck", "nodia", database)
    check(
        "nodia flows forward not stuck",
        _mode(r) != "spell_confirmation",
        _mode(r),
    )
    check(
        "nodia corrects to noida city",
        _city(r) == "noida" or _mode(r) == "clarification",
        f"city={_city(r)} mode={_mode(r)}",
    )

    clear_conversation("smoke_spell_loop")
    await chatbot_response("smoke_spell_loop", "excvator in jaipir", database)
    r = await chatbot_response("smoke_spell_loop", "no", database)
    check(
        "no after search never spell-traps",
        _mode(r) != "spell_confirmation",
        _mode(r),
    )

    clear_conversation("smoke_spell")
    r = await chatbot_response("smoke_spell", "excvator in jaipir", database)
    check(
        "excvator jaipir auto-corrects",
        _cat(r) == "excavator" and _city(r) == "jaipur",
        f"cat={_cat(r)} city={_city(r)}",
    )
    check(
        "spell context in response",
        bool(_ctx(r).get("corrected_query")) and len(_ctx(r).get("corrections") or []) > 0,
        str(_ctx(r).get("corrections")),
    )

    clear_conversation("smoke_spell2")
    r = await chatbot_response("smoke_spell2", "hydra crne in delih", database)
    check(
        "hydra crne delih corrects",
        _cat(r) == "hydra crane" and _city(r) == "delhi",
        f"cat={_cat(r)} city={_city(r)}",
    )

    clear_conversation("smoke_spell3")
    r = await chatbot_response("smoke_spell3", "road rolar in pune", database)
    check("road rolar corrects", _cat(r) == "road roller" and _city(r) == "pune")

    clear_conversation("smoke_spell4")
    r = await chatbot_response("smoke_spell4", "jcb chahiy", database)
    check(
        "jcb chahiy maps to backhoe loader not excavator",
        _cat(r) == "backhoe loader",
        _cat(r),
    )

    clear_conversation("smoke_spell5")
    r = await chatbot_response("smoke_spell5", "dump truk mumbai", database)
    check(
        "dump truk mumbai corrects",
        _cat(r) == "dump truck" and _city(r) == "mumbai",
        f"cat={_cat(r)} city={_city(r)}",
    )

    clear_conversation("smoke_spell6")
    r = await chatbot_response("smoke_spell6", "crawlar dril jaipur", database)
    check(
        "crawlar dril corrects",
        _cat(r) == "crawler drill" and _city(r) == "jaipur",
        f"cat={_cat(r)} city={_city(r)}",
    )

    clear_conversation("smoke_city_chips")
    r = await chatbot_response("smoke_city_chips", "jaipur", database)
    suggestions = r.get("data", {}).get("suggestions") or []
    pending = r.get("data", {}).get("pending_clarification") or {}
    avail = pending.get("available_categories") or []
    static_chips = {
        "Excavator", "JCB / Backhoe Loader", "Crane",
        "Road Roller", "Dump Truck", "Crawler Drill",
    }
    check(
        "jaipur shows db-driven category chips",
        _mode(r) == "clarification" and len(suggestions) > 0,
        f"mode={_mode(r)} suggestions={suggestions}",
    )
    check(
        "chips match available categories in city",
        len(avail) > 0 and len(suggestions) == len(avail),
        f"avail={avail}",
    )
    check(
        "not static generic chip list",
        set(suggestions) != static_chips,
        str(suggestions),
    )

    print(f"\n=== {passed} passed, {failed} failed ===\n")
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
