#!/usr/bin/env python3
"""Generalized image search / follow-up mechanism tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.image_chat_followup import resolve_image_user_intent
from app.ai.image_turn_models import image_chip_to_intent, is_image_clarification_chip
from app.ai.image_turn_resolver import (
    build_search_message_for_image_intent,
    detect_image_text_intent,
    resolve_image_turn,
)
from app.ai.suggestion_action_resolver import resolve_suggestion_chip
from app.chatbot.image_context_memory import (
    clear_image_context,
    is_image_flow_continuation,
    mentions_explicit_machine,
    save_image_context,
)

PASS = FAIL = 0


def ok(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"OK {label}" + (f" | {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"FAIL {label}" + (f" | {detail}" if detail else ""))


def _fake_pipeline(*, category="excavator", confidence=0.82, brand=None):
    intent = {
        "match_type": "exact",
        "machine_type": category,
        "search_query": category,
        "intent_confidence": confidence,
        "confident": confidence >= 0.35,
        "suggested_categories": [category],
        "classifier": "clip+opencv",
        "display_label": f"{brand} {category}".strip() if brand else category.title(),
        "detected_brand": brand,
    }
    return {"success": True, "stage": "visual", "intent": intent, "classification": {}}


def _ctx(*, category="excavator", brand=None, awaiting=True):
    return {
        "detected_category": category,
        "detected_machine_type": category,
        "detected_brand": brand,
        "confidence": 0.8,
        "awaiting_image_choice": awaiting,
        "pending_image_intent": "similar_category",
        "image_intent": "unclear",
    }


def test_chip_intent_mapping() -> None:
    print("\n--- chip intent mapping ---")
    chips = [
        "Exact same machine",
        "Similar machines",
        "Just identify this machine",
        "exact same machine",
        "Bilkul same machine",
        "Similar machines dikhao",
    ]
    for chip in chips:
        ok(f"chip recognized: {chip}", is_image_clarification_chip(chip))
        ok(f"chip intent: {chip}", image_chip_to_intent(chip) is not None)


def test_exact_chip_not_blocked_as_explicit_machine() -> None:
    print("\n--- image reference vs explicit machine ---")
    ctx = _ctx()
    save_image_context("chip_sess", full_context=ctx)
    ok(
        "Exact same machine is image continuation",
        is_image_flow_continuation("Exact same machine", "chip_sess"),
    )
    ok(
        "chip not explicit machine pivot",
        not mentions_explicit_machine("Exact same machine", image_ctx=ctx),
    )
    clear_image_context("chip_sess")


def test_intent_detection_variants() -> None:
    print("\n--- caption intent variants ---")
    cases = [
        ("which machine is this ?", "identify_only"),
        ("which mahcine is this ?", "identify_only"),
        ("is this machine available", "availability_search"),
        ("i this machine available", "availability_search"),
        ("is this brand excavator available", "availability_search"),
        ("similar machines", "similar_category"),
        ("exact same machine", "exact_match"),
        ("jaipur", None),
    ]
    for text, expected in cases:
        got = detect_image_text_intent(text)
        ok(f"intent {text!r}", got == expected, f"got={got}")


def test_city_followup_with_pending_intent() -> None:
    print("\n--- city follow-up memory ---")
    ctx = _ctx(awaiting=True)
    intent = resolve_image_user_intent("jaipur", ctx)
    ok("city continues similar intent", intent == "similar_category", f"got={intent}")
    intent2 = resolve_image_user_intent("Delhi", {**ctx, "pending_image_intent": "availability_search"})
    ok("city continues availability", intent2 == "availability_search")


def test_brand_aware_search_message() -> None:
    print("\n--- brand-aware search messages ---")
    msg = build_search_message_for_image_intent(
        image_intent="availability_search",
        entities={"category": "excavator", "brand": "Tata Hitachi", "city": "Jaipur"},
        user_text="is this available in jaipur",
    )
    ok("brand in availability search", "tata" in msg.lower() and "jaipur" in msg.lower(), msg)
    msg2 = build_search_message_for_image_intent(
        image_intent="similar_category",
        entities={"category": "backhoe loader", "brand": "JCB"},
        user_text="similar machines",
    )
    ok("brand in similar search", "jcb" in msg2.lower() and "similar" in msg2.lower(), msg2)


def test_suggestion_chip_resolver_with_image_context() -> None:
    print("\n--- suggestion chips with image context ---")
    session_ctx = {
        "session_id": "s_chip",
        "last_image_context": _ctx(brand="Tata Hitachi"),
    }
    save_image_context("s_chip", full_context=session_ctx["last_image_context"])
    exact = resolve_suggestion_chip("Exact same machine", session_ctx=session_ctx)
    ok("exact chip sends message", exact.get("action") == "send_message")
    ok("exact chip mentions category", "excavator" in (exact.get("message") or "").lower())
    similar = resolve_suggestion_chip("Similar machines", session_ctx=session_ctx)
    ok("similar chip sends message", similar.get("action") == "send_message")
    ok("similar in message", "similar" in (similar.get("message") or "").lower())
    clear_image_context("s_chip")


def test_low_confidence_identify_path() -> None:
    print("\n--- low confidence identify ---")
    turn = resolve_image_turn(
        pipeline=_fake_pipeline(confidence=0.22),
        user_text="which machine is this ?",
        session_id="low_id",
    )
    ok("identify allowed on low conf", turn.image_intent == "identify_only", turn.image_intent)
    ok("category kept for identify", turn.detected_category == "excavator")


def test_resolver_brand_from_caption() -> None:
    print("\n--- brand from caption ---")
    turn = resolve_image_turn(
        pipeline=_fake_pipeline(brand="XCMG"),
        user_text="is this brand excavator available in jaipur",
        session_id="brand_cap",
    )
    ok("availability with city searches", turn.should_search, f"intent={turn.image_intent}")
    ok("brand captured", turn.detected_brand is not None or "xcmg" in turn.safe_user_message.lower())


def main() -> None:
    test_chip_intent_mapping()
    test_exact_chip_not_blocked_as_explicit_machine()
    test_intent_detection_variants()
    test_city_followup_with_pending_intent()
    test_brand_aware_search_message()
    test_suggestion_chip_resolver_with_image_context()
    test_low_confidence_identify_path()
    test_resolver_brand_from_caption()

    print(f"\n{'=' * 40}\nPassed: {PASS}  Failed: {FAIL}")
    if FAIL:
        sys.exit(1)
    print("ALL IMAGE CHAT FOLLOWUP MECHANISM TESTS PASSED")


if __name__ == "__main__":
    main()
