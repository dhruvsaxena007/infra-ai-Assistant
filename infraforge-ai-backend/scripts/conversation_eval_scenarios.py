"""
Long sequential conversation scenarios for assistant eval (60+ chats, 10–15 turns each).

English, Hinglish, and Hindi mixes — real contractor / renter flows.
Used by: scripts/generate_conversation_eval_cases.py
"""

from __future__ import annotations

from typing import Any

from scripts.conversation_scenario_builder import CONVERSATIONS  # noqa: F401

__all__ = ["conv", "t", "CONVERSATIONS"]


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
