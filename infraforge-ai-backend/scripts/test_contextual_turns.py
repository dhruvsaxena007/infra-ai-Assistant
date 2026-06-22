#!/usr/bin/env python3
"""Test contextual follow-up detection."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.conversation_context import analyze_contextual_turn, build_result_context

RESULT = build_result_context(
    [
        {
            "_id": "1",
            "name": "EPIROC AIR ROC D-35(LM-100) Pneumatic",
            "category": "crawler drill",
            "city": "jaipur",
        }
    ],
    {"city": "jaipur", "category": "crawler drill"},
)

FILTERS = {"city": "jaipur"}

TESTS = [
    ("will this help me in excavation", "suitability"),
    ("need a machine for excavation", "purpose_search"),
    (
        "EPIROC AIR ROC D-35 will this can help me in road excavatioon",
        "suitability",
    ),
    ("i want a excavator", "none"),
    (
        "i want machines for road digging and compact concrete so suggest me the machines suitable for these works",
        "multi_purpose_advisory",
    ),
]

for msg, expected in TESTS:
    r = analyze_contextual_turn(msg, last_filters=FILTERS, result_ctx=RESULT)
    ok = r["turn_type"] == expected or (expected == "none" and r["turn_type"] == "none")
    print(f"{'OK' if ok else 'FAIL'} {msg!r:55} -> {r['turn_type']} (want {expected})")
    if r.get("search_filters"):
        print(f"     search_filters={r['search_filters']}")
