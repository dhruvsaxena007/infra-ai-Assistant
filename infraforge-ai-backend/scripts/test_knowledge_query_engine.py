#!/usr/bin/env python3
"""Knowledge query engine — direct answers for identity and domain definitions."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.knowledge_query_engine import (
    build_knowledge_answer,
    detect_knowledge_query,
    knowledge_turn_from_message,
)
from app.ai.domain_intelligence_gateway import interpret_domain_rules
from app.ai.universal_turn_engine import analyze_universal_turn
from app.ai.social_turn_detector import detect_social_turn
from app.ai.query_parser import parse_query


def _assert(label: str, cond: bool) -> None:
    print(f"{'OK' if cond else 'FAIL'} {label}")
    if not cond:
        raise SystemExit(1)


def test_identity_queries() -> None:
    cases = [
        "whats your name",
        "what is your name",
        "who are you",
        "aap ka naam kya hai",
    ]
    for msg in cases:
        k = detect_knowledge_query(msg, parse_query(msg))
        _assert(f"identity detect: {msg!r}", k and k.get("kind") == "assistant_identity")
        u = analyze_universal_turn(msg)
        _assert(f"universal knowledge: {msg!r}", u.get("shape") == "knowledge_answer")
        s = detect_social_turn(msg, {})
        _assert(f"not social: {msg!r}", s is None)


def test_domain_definition() -> None:
    cases = [
        ("what is jcb", "JCB", "brand"),
        ("what is excavator", "excavator", "category"),
        ("jcb kya hai", "JCB", "brand"),
    ]
    for msg, subject, stype in cases:
        k = detect_knowledge_query(msg, parse_query(msg))
        _assert(
            f"define detect: {msg!r}",
            k
            and k.get("kind") == "domain_definition"
            and (k.get("subject") or "").lower().startswith(subject.lower()[:3]),
        )


def test_domain_gateway_routes_knowledge() -> None:
    for msg in ["whats your name", "what is jcb"]:
        interp = interpret_domain_rules(msg, parsed=parse_query(msg))
        _assert(
            f"gateway domain_answer: {msg!r}",
            interp.response_mode == "domain_answer",
        )


def test_draft_has_substance() -> None:
    import asyncio

    async def _run() -> None:
        for msg, kind in [("whats your name", "assistant_identity"), ("what is jcb", "domain_definition")]:
            k = knowledge_turn_from_message(msg, parse_query(msg))
            turn = {**k, "shape": "knowledge_answer"}
            resp = await build_knowledge_answer(turn, user_message=msg, lang="english")
            body = resp.get("message") or ""
            _assert(f"draft not empty: {msg!r}", len(body) > 40)
            if kind == "assistant_identity":
                _assert("identity names InfraForge", "InfraForge" in body)
            else:
                _assert("jcb draft mentions brand", "JCB" in body)

    asyncio.run(_run())


def test_no_marketplace_hijack() -> None:
    k = detect_knowledge_query("excavator in jaipur dikhao", parse_query("excavator in jaipur dikhao"))
    _assert("search not knowledge", k is None)


def main() -> None:
    test_identity_queries()
    test_domain_definition()
    test_domain_gateway_routes_knowledge()
    test_draft_has_substance()
    test_no_marketplace_hijack()
    print("\nAll knowledge query tests passed.")


if __name__ == "__main__":
    main()
