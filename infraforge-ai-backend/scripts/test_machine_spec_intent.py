#!/usr/bin/env python3
"""Machine specification intent - structural detection and knowledge routing."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISABLE_GROQ_SEMANTIC", "true")
os.environ.setdefault("USE_GROQ_UNIVERSAL_CLASSIFIER", "false")

from app.ai.knowledge_query_engine import (
    build_knowledge_answer,
    detect_knowledge_query,
    knowledge_turn_from_message,
)
from app.ai.machine_spec_service import detect_machine_spec_query
from app.ai.message_normalizer import normalize_user_message
from app.ai.query_parser import parse_query
from app.ai.semantic_turn_gateway import _rules_understand
from app.ai.domain_recommendation_engine import is_domain_recommendation_query
from app.ai.universal_turn_engine import analyze_universal_turn


def _assert(label: str, cond: bool) -> None:
    print(f"{'OK' if cond else 'FAIL'} {label}")
    if not cond:
        raise SystemExit(1)


_SPEC_QUERIES = [
    "give me specifications of Komatsu PC210 Excavator",
    "give me the specifications of Komatsu PC210 Excavator",
    "tell me something about Komatsu PC210",
    "give me engine specifications of JCB 3DX",
    "Komatsu PC210 ke baare me batao",
    "komatsu pc210 ki details chahiye",
    "PC210 excavator ki specification bataiye",
    "what are the features of CAT 320D excavator",
    "komatsu pc210 ka engine power kitna hai",
    "give me specification of Caterpillar 320D",
    "Caterpillar 320D is machine ke bare mai batao",
    "Hyundai R210 ye machine kese hai",
    "how is the JCB 3DX machine",
    "give me specifications of Schwing Stetter AM Concrete Mixer",
    "give details of Komatsu PC210 machine",
    "mujhe CAT 320D ke bare mai aur information do",
]

_TYPO_QUERIES = [
    ("geive me specifcations of Komatsu PC210 Excavator", "give"),
    ("especifications of JCB 3DX", "specifications"),
]

_SEARCH_NOT_SPEC = [
    "excavator in delhi dikhao",
    "komatsu pc210 rent in jaipur",
    "show me komatsu listings in delhi",
]


_ADVISORY_QUERIES = [
    "Komatsu PC210 ye baki machines se kese badiya hai",
    "how is JCB 3DX better than other machines",
]


def test_advisory_detection() -> None:
    from app.ai.machine_spec_service import detect_machine_advisory_query

    for msg in _ADVISORY_QUERIES:
        p = parse_query(msg)
        adv = detect_machine_advisory_query(msg, p)
        _assert(f"advisory detect: {msg[:50]!r}", adv and adv.get("kind") == "machine_advisory")
        u = _rules_understand(msg, parsed=p)
        _assert(
            f"advisory routes knowledge: {msg[:45]!r}",
            u.primary_intent == "domain_knowledge" and not u.should_search,
        )


def test_spec_detection() -> None:
    for msg in _SPEC_QUERIES:
        p = parse_query(msg)
        spec = detect_machine_spec_query(msg, p)
        _assert(f"detect spec: {msg[:55]!r}", spec and spec.get("kind") == "machine_specification")
        k = detect_knowledge_query(msg, p)
        _assert(f"knowledge spec: {msg[:55]!r}", k and k.get("kind") == "machine_specification")


def test_semantic_routes_knowledge_not_search() -> None:
    for msg in _SPEC_QUERIES[:6]:
        u = _rules_understand(msg, parsed=parse_query(msg))
        _assert(
            f"semantic domain_knowledge: {msg[:45]!r}",
            u.primary_intent == "domain_knowledge" and not u.should_search,
        )
        _assert(
            f"not recommendation: {msg[:45]!r}",
            u.primary_intent != "recommendation",
        )


def test_not_domain_recommendation() -> None:
    for msg in _SPEC_QUERIES:
        _assert(
            f"not domain rec: {msg[:45]!r}",
            not is_domain_recommendation_query(msg, parsed=parse_query(msg)),
        )


def test_universal_knowledge_shape() -> None:
    for msg in _SPEC_QUERIES[:4]:
        u = analyze_universal_turn(msg)
        _assert(
            f"universal knowledge: {msg[:45]!r}",
            u.get("shape") == "knowledge_answer" and u.get("kind") == "machine_specification",
        )


def test_typos_normalized() -> None:
    for raw, fixed_token in _TYPO_QUERIES:
        norm = normalize_user_message(raw)
        _assert(f"typo fix contains {fixed_token}: {raw!r}", fixed_token in norm.corrected.lower())
        spec = detect_machine_spec_query(norm.corrected, parse_query(norm.corrected))
        _assert(f"typo spec detect: {raw!r}", spec and spec.get("kind") == "machine_specification")


def test_search_not_hijacked() -> None:
    for msg in _SEARCH_NOT_SPEC:
        spec = detect_machine_spec_query(msg, parse_query(msg))
        _assert(f"search not spec: {msg!r}", spec is None)


def test_spec_answer_has_content() -> None:
    async def _run() -> None:
        msg = "give me specifications of Komatsu PC210 Excavator"
        turn = knowledge_turn_from_message(msg, parse_query(msg))
        _assert("turn found", turn is not None)
        resp = await build_knowledge_answer(
            {**turn, "shape": "knowledge_answer"},
            user_message=msg,
            lang="english",
        )
        body = resp.get("message") or ""
        _assert("answer not empty", len(body) > 80)
        _assert("mentions Komatsu", "Komatsu" in body or "komatsu" in body.lower())
        _assert("has engine power", "engine" in body.lower() or "HP" in body)
        _assert("not listing dump", "Delhi listings" not in body)

    asyncio.run(_run())


def main() -> None:
    test_advisory_detection()
    test_spec_detection()
    test_semantic_routes_knowledge_not_search()
    test_not_domain_recommendation()
    test_universal_knowledge_shape()
    test_typos_normalized()
    test_search_not_hijacked()
    test_spec_answer_has_content()
    print("\nAll machine spec intent tests passed.")


if __name__ == "__main__":
    main()
