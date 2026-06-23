# -*- coding: utf-8 -*-
"""Industry lexicon regression - purpose/category mapping, typos, pattern families."""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_GROQ_SEMANTIC", "true")

from app.ai.industry_lexicon import (
    CANONICAL_PURPOSES,
    CONSTRUCTION_NOUNS,
    MATERIAL_TERMS,
    PURPOSE_TERMS,
    VERB_STEMS_HINDI,
    build_purpose_aliases,
    build_purpose_signal_patterns,
    build_verb_stem_patterns,
    build_work_phrase_patterns,
    lexicon_stats,
    merge_category_synonyms,
)
from app.ai.purpose_intent_engine import detect_purpose_from_message
from app.ai.message_normalizer import normalize_user_message
from app.ai.category_mapping import detect_requested_category, CATEGORY_SYNONYMS
from app.chatbot.assistant_intelligence import PURPOSE_ALIASES, detect_all_work_purposes


def _assert(cond: bool, msg: str, failures: list[str]) -> None:
    if not cond:
        failures.append(msg)


def test_lexicon_structure(failures: list[str]) -> None:
    stats = lexicon_stats()
    _assert(stats["purpose_terms"] >= 80, f"purpose_terms too small: {stats['purpose_terms']}", failures)
    _assert(stats["category_terms"] >= 40, f"category_terms too small: {stats['category_terms']}", failures)
    _assert(stats["construction_nouns"] >= 30, "construction_nouns too small", failures)
    _assert(stats["material_terms"] >= 20, "material_terms too small", failures)
    _assert(stats["verb_stems_hindi"] >= 20, "verb_stems_hindi too small", failures)
    _assert(stats["work_phrase_patterns"] >= 15, "work_phrase_patterns too small", failures)
    _assert(stats["common_typos"] >= 20, "common_typos too small", failures)

    for purpose in CANONICAL_PURPOSES:
        _assert(purpose in set(PURPOSE_TERMS.values()), f"missing purpose key in values: {purpose}", failures)

    aliases = build_purpose_aliases()
    _assert(aliases == PURPOSE_TERMS, "build_purpose_aliases must match PURPOSE_TERMS", failures)
    _assert(PURPOSE_ALIASES == PURPOSE_TERMS, "assistant_intelligence must import lexicon aliases", failures)


def test_purpose_queries(failures: list[str]) -> None:
    cases = [
        ("mujhe road khodne ke liye machine chahiye", "digging"),
        ("i need machine for excavation", "digging"),
        ("foundation khudai ke liye equipment", "digging"),
        ("mujhe gaddha khodne ke liye jcb chahiye", "digging"),
        ("mujhe building todne ke liye machine chaiye", "demolition"),
        ("imarat girane ke liye machine", "demolition"),
        ("need equipment for demolition work", "demolition"),
        ("mujhe road dabane ke liye roller chahiye", "compaction"),
        ("highway compaction ke liye machine", "compaction"),
        ("bitumen laying machine chahiye", "compaction"),
        ("mujhe road seedhi karne ke liye machine", "leveling"),
        ("grading work ke liye grader", "leveling"),
        ("mujhe patther uthane ke liye truck chaiye", "transport"),
        ("boulder hauling from quarry", "transport"),
        ("saman le jana hai tipper se", "transport"),
        ("steel erection ke liye crane chahiye", "lifting"),
        ("upar uthane ke liye hydra", "lifting"),
        ("material handling forklift chahiye", "loading"),
        ("borewell drilling machine", "drilling"),
        ("blast hole drilling equipment", "drilling"),
        ("rcc slab casting ke liye mixer", "concrete"),
        ("rmc truck chahiye site pe", "concrete"),
        ("quarry mining ke liye excavator", "mining"),
        ("stone quarry overburden removal", "mining"),
        ("mujhe nh road ka kaam karne ke liye roller", "compaction"),
        ("flyover foundation concreting machine", "concrete"),
        ("pipeline trench digging equipment", "digging"),
        ("bridge demolition ke liye machine", "demolition"),
    ]
    for message, expected in cases:
        norm = normalize_user_message(message).corrected or message
        got = detect_purpose_from_message(norm)
        _assert(got == expected, f"purpose '{message[:50]}' => {got} expected {expected}", failures)


def test_category_terms(failures: list[str]) -> None:
    cases = [
        ("poclain chahiye jaipur mein", "excavator"),
        ("hydra crane rent", "hydra crane"),
        ("sadak roller dikhao", "road roller"),
        ("tata tipper under 50k", "dump truck"),
        ("transit mixer mumbai", "concrete mixer truck"),
        ("blast hole drill", "crawler drill"),
        ("khudai machine chahiye", "excavator"),
    ]
    for message, expected in cases:
        norm = normalize_user_message(message).corrected or message
        got = detect_requested_category(norm)
        _assert(got == expected, f"category '{message}' => {got} expected {expected}", failures)


def test_typo_normalization(failures: list[str]) -> None:
    cases = [
        ("exavator chahiye", "excavator"),
        ("road rolar jaipur", "road roller"),
        ("hydra crne rent", "hydra crane"),
        ("dump truk delhi", "dump truck"),
        ("machne for excavtion", "machine"),
        ("i need machne for excavtion", "excavation"),
    ]
    for raw, fragment in cases:
        norm = normalize_user_message(raw).corrected.lower()
        _assert(fragment in norm, f"typo '{raw}' => '{norm}' missing '{fragment}'", failures)


def test_pattern_families(failures: list[str]) -> None:
    verb_patterns = build_verb_stem_patterns()
    work_patterns = build_work_phrase_patterns()
    signal_patterns = build_purpose_signal_patterns()

    _assert(len(verb_patterns) >= 15, "verb stem pattern families too few", failures)
    _assert(len(work_patterns) >= 15, "work phrase pattern families too few", failures)
    _assert(len(signal_patterns) >= 15, "signal patterns too few", failures)

    matched = False
    for stem in ("khodna", "todna", "dabana", "uthana"):
        for pattern, _ in verb_patterns:
            if re.search(pattern, stem, re.I):
                matched = True
                break
    _assert(matched, "verb patterns should match Hindi stems", failures)

    transport_hit = any(
        re.search(p, "patthar uthane ke liye", re.I) and purpose == "transport"
        for p, purpose in work_patterns
    )
    _assert(transport_hit, "material+verb transport family missing", failures)


def test_merge_category_synonyms(failures: list[str]) -> None:
    base = {"excavator": ["excavator"]}
    merged = merge_category_synonyms(base)
    _assert("poclain" in merged["excavator"], "poclain should merge into excavator synonyms", failures)
    _assert("khudai machine" in CATEGORY_SYNONYMS.get("excavator", []), "lexicon wired into category_mapping", failures)


def test_construction_vocabulary(failures: list[str]) -> None:
    _assert("flyover" in CONSTRUCTION_NOUNS, "flyover noun missing", failures)
    _assert("puliya" in CONSTRUCTION_NOUNS, "puliya noun missing", failures)
    _assert(MATERIAL_TERMS.get("bitumen") == "compaction", "bitumen hint wrong", failures)
    _assert(VERB_STEMS_HINDI.get("khodna") == "digging", "khodna stem wrong", failures)


def test_multi_purpose_detection(failures: list[str]) -> None:
    found = detect_all_work_purposes("digging and lifting work on site")
    _assert("digging" in found and "lifting" in found, f"multi-purpose: {found}", failures)


def main() -> int:
    failures: list[str] = []
    test_lexicon_structure(failures)
    test_purpose_queries(failures)
    test_category_terms(failures)
    test_typo_normalization(failures)
    test_pattern_families(failures)
    test_merge_category_synonyms(failures)
    test_construction_vocabulary(failures)
    test_multi_purpose_detection(failures)

    if failures:
        print(f"FAILED {len(failures)} assertion(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    stats = lexicon_stats()
    print("All industry lexicon tests passed.")
    print(f"stats: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
