"""
Generate conversation eval cases (10–15 turn sequential chats).

Run:
    python scripts/generate_conversation_eval_cases.py

Output:
    promptfoo/tests/conversation_cases.json
    promptfoo/tests/conversation_eval.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.conversation_eval_scenarios import CONVERSATIONS  # noqa: E402

OUT_DIR = ROOT / "promptfoo" / "tests"
OUT_JSON = OUT_DIR / "conversation_cases.json"
OUT_YAML = OUT_DIR / "conversation_eval.yaml"


def case_to_promptfoo_test(case: dict) -> dict:
    return {
        "description": case["id"],
        "vars": {
            "session_id": case["session_id"],
            "clear_session": case.get("clear_session", True),
            "turns_json": json.dumps(case["turns"], ensure_ascii=False),
            "expect_json": json.dumps(case["turns"][-1].get("expect", {})),
        },
        "assert": [
            {"type": "javascript", "value": "JSON.parse(output).pass === true"},
        ],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(CONVERSATIONS, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    tests = [case_to_promptfoo_test(c) for c in CONVERSATIONS]
    total_turns = sum(len(c["turns"]) for c in CONVERSATIONS)
    yaml_lines = [
        "# Auto-generated conversation eval — do not edit by hand.",
        f"# Conversations: {len(CONVERSATIONS)} · Total turns: {total_turns}",
        "",
    ]
    for t in tests:
        yaml_lines.append(f"- description: {t['description']}")
        yaml_lines.append("  vars:")
        for k, v in t["vars"].items():
            if isinstance(v, bool):
                yaml_lines.append(f"    {k}: {'true' if v else 'false'}")
            else:
                yaml_lines.append(f"    {k}: {json.dumps(v, ensure_ascii=False)}")
        yaml_lines.append("  assert:")
        yaml_lines.append("    - type: javascript")
        yaml_lines.append('      value: JSON.parse(output).pass === true')
        yaml_lines.append("")

    OUT_YAML.write_text("\n".join(yaml_lines), encoding="utf-8")
    print(f"Generated {len(CONVERSATIONS)} conversations ({total_turns} turns)")
    print(f"  -> {OUT_JSON}")
    print(f"  -> {OUT_YAML}")


if __name__ == "__main__":
    main()
