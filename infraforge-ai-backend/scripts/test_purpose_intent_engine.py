"""Purpose-intent engine tests - work-goal queries in Hindi/English/Hinglish."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_GROQ_SEMANTIC", "true")

from app.ai.purpose_intent_engine import detect_purpose_from_message
from app.ai.query_parser import parse_query
from app.ai.semantic_turn_gateway import _rules_understand
from app.ai.message_normalizer import normalize_user_message


SAMPLES = [
    ("i need machine for excavation", "digging", "excavator"),
    ("i need a machine for excavtion", "digging", "excavator"),
    ("mujhe road khodne ke liye machine chaiye", "digging", "excavator"),
    ("mujhe road seedhi karne ke liye machine chaiye", "leveling", "motor grader"),
    ("mujhe patther uthane ke liye truck chaiye", "transport", "dump truck"),
    ("i need a machine to carry rocks from mill", "transport", "dump truck"),
    ("mujhe road dabane ke liye roller chahiye", "compaction", "road roller"),
    ("need equipment for drilling bore", "drilling", "crawler drill"),
    ("mujhe building todne ke liye machine chaiye", "demolition", "excavator"),
    ("mujhe demolish karne ke liye machine chaiye", "demolition", "excavator"),
]


def main() -> int:
    failed = 0
    for message, exp_purpose, exp_cat in SAMPLES:
        norm = normalize_user_message(message).corrected or message
        parsed = parse_query(norm)
        purpose = detect_purpose_from_message(norm)
        sem = _rules_understand(norm, parsed=parsed, context={})

        ok_purpose = purpose == exp_purpose
        ok_cat = parsed.get("category") == exp_cat
        ok_search = sem.should_search and sem.primary_intent == "machine_search"

        if ok_purpose and ok_cat and ok_search:
            print(f"PASS {message[:55]}")
        else:
            failed += 1
            print(f"FAIL {message[:55]}")
            print(f"     purpose={purpose} (exp {exp_purpose}) cat={parsed.get('category')} (exp {exp_cat})")
            print(f"     intent={sem.primary_intent} search={sem.should_search}")

    typo = "i need machne for excavtion"
    p = parse_query(normalize_user_message(typo).corrected or typo)
    if p.get("purpose_key") == "digging":
        print("PASS typo normalization")
    else:
        failed += 1
        print(f"FAIL typo normalization purpose={p.get('purpose_key')}")

    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nAll purpose intent tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
