#!/usr/bin/env python3
"""Selected-machine context — generalized follow-up on UI selection (no fresh search)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.conversation_context import build_result_context, slim_machine
from app.ai.selected_machine_context import (
    build_selected_machine_response,
    detect_selected_machine_turn,
    resolve_active_machine,
)
from app.ai.universal_turn_engine import analyze_universal_turn

HYUNDAI = slim_machine(
    {
        "_id": "hyundai-r210",
        "name": "Hyundai R210",
        "category": "excavator",
        "city": "jaipur",
        "brand": "Hyundai",
        "model": "R210",
        "price_per_day": 38000,
        "availability_status": "available",
        "listing_type": "rent",
    }
)

SESSION = {"selected_machine": HYUNDAI}
RESULT_CTX = build_result_context(
    [
        {"_id": "1", "name": "Komatsu PC210", "category": "excavator", "city": "jaipur"},
        HYUNDAI,
    ],
    {"city": "jaipur", "category": "excavator"},
)
FILTERS = {"city": "jaipur", "category": "excavator"}


def _assert(label: str, cond: bool) -> None:
    print(f"{'OK' if cond else 'FAIL'} {label}")
    if not cond:
        raise SystemExit(1)


def test_resolve_active_machine() -> None:
    m = resolve_active_machine(
        "anything",
        session_ctx=SESSION,
        result_ctx=RESULT_CTX,
    )
    _assert("resolve prefers UI selection", m and m.get("name") == "Hyundai R210")


def test_detect_want_selected() -> None:
    cases = [
        ("mujhe ye machine chaiye", "latin_hinglish"),
        ("i want this machine", "english"),
        ("mujhe ye wali chahiye", "hinglish_wali"),
        (
            "\u092e\u0941\u091d\u0947 \u092f\u0947 \u0938\u0947\u0932\u0947\u0915\u094d\u091f\u0947\u0921 \u092e\u0936\u0940\u0928 \u091a\u093e\u0939\u093f\u090f",
            "hindi_devanagari",
        ),
    ]
    for msg, tag in cases:
        turn = detect_selected_machine_turn(
            msg,
            session_ctx=SESSION,
            result_ctx=RESULT_CTX,
        )
        _assert(
            f"detect want [{tag}]",
            turn
            and turn.get("action") == "want_booking"
            and (turn.get("machine") or {}).get("name") == "Hyundai R210",
        )


def test_detect_contact_owner() -> None:
    turn = detect_selected_machine_turn(
        "Contact owner",
        session_ctx=SESSION,
        result_ctx=RESULT_CTX,
    )
    _assert(
        "contact owner with selection",
        turn and turn.get("action") == "contact_owner",
    )


def test_no_fresh_search_on_selection() -> None:
    """Broad city+category query without demonstrative should NOT be selected-machine."""
    turn = detect_selected_machine_turn(
        "excavator chahiye jaipur me",
        session_ctx=SESSION,
        result_ctx=RESULT_CTX,
    )
    _assert("fresh search not hijacked", turn is None)


def test_universal_shape() -> None:
    turn = analyze_universal_turn(
        "mujhe ye machine chaiye",
        session_ctx=SESSION,
        result_ctx=RESULT_CTX,
        last_filters=FILTERS,
    )
    _assert(
        "universal shape selected_machine",
        turn.get("shape") == "selected_machine"
        and turn.get("action") == "want_booking",
    )


def test_response_has_machine_name() -> None:
    resp = build_selected_machine_response(
        machine=HYUNDAI,
        action="want_booking",
        lang="hinglish",
    )
    _assert(
        "response names machine",
        "Hyundai R210" in resp.get("message", ""),
    )
    _assert("response preserves panel", resp.get("preserve_machines") is True)


def main() -> None:
    test_resolve_active_machine()
    test_detect_want_selected()
    test_detect_contact_owner()
    test_no_fresh_search_on_selection()
    test_universal_shape()
    test_response_has_machine_name()
    print("\nAll selected-machine context tests passed.")


if __name__ == "__main__":
    main()
