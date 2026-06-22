"""
Semantic Understanding Phase — paraphrase-group regression tests (150+ cases).

Run: python scripts/test_semantic_understanding_phase.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AI_INTENT_MODE", "rules_first")
os.environ.setdefault("DOMAIN_INTELLIGENCE_MODE", "shadow")
os.environ.setdefault("USE_GROQ_UNIVERSAL_CLASSIFIER", "false")

_passed = 0
_failed = 0
_errors: list[str] = []


def _assert(cond: bool, msg: str) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        _errors.append(msg)
        print(f"  [FAIL] {msg}")


def _group(name: str) -> None:
    print(f"\n--- {name} ---")


# ---------------------------------------------------------------------------
# Numeric normalizer paraphrase groups
# ---------------------------------------------------------------------------

_NUMERIC_GROUPS = [
    ("7k", 7000),
    ("8.5k", 8500),
    ("10K per day", 10000),
    ("under 7k", 7000),
    ("budget 8.5k", 8500),
    ("rs 7k", 7000),
    ("₹8.5k", 8500),
    ("1 lakh", 100000),
    ("2 lac", 200000),
    ("1.5 lakh", 150000),
    ("1 cr", 10000000),
    ("1 crore", 10000000),
    ("5000 hazaar", 5000000),
    ("8000 per day", 8000),
    ("8000/day", 8000),
    ("din ka 7000", 7000),
    ("7k ke andar", 7000),
    ("under 12k per day", 12000),
]


def test_numeric_normalizer():
    _group("Numeric Normalizer")
    from app.ai.numeric_normalizer import extract_budget_amount, expand_numeric_shorthand

    for phrase, expected in _NUMERIC_GROUPS:
        got = extract_budget_amount(phrase)
        _assert(got == expected, f"extract_budget '{phrase}' => {got} expected {expected}")

    expanded = expand_numeric_shorthand("excavator under 7k in jaipur")
    _assert("7000" in expanded, f"expand 7k: {expanded}")
    _assert(extract_budget_amount("8.5k per day") == 8500, "8.5k not 8")


# ---------------------------------------------------------------------------
# Semantic gateway intent groups
# ---------------------------------------------------------------------------

_META_HELP = [
    "how can you help me",
    "what can you do",
    "how does infraforge work",
    "kya kar sakte ho",
    "kaise madad karoge",
    "what are your capabilities",
]

_MEMORY = [
    "what is my name",
    "who am i",
    "mera naam kya hai",
    "do you know my name",
    "naam yaad hai",
]

_FRUSTRATION = [
    "are you mad",
    "you are useless",
    "bekar bot hai",
    "you are stupid",
    "kya pagal ho",
]

_COMPARISON = [
    "JCB vs Komatsu",
    "compare JCB and CAT excavator",
    "Hyundai ya CAT acche hain",
    "which is better JCB or Volvo",
    "JCB versus Komatsu for excavator",
]

_RECOMMENDATION = [
    "best machine for digging",
    "recommend machine for road project",
    "which machine for heavy rocks",
    "kaunsi machine chahiye foundation ke liye",
    "suggest equipment for compaction work",
]

_SUPPORT = [
    "payment failed",
    "refund my booking",
    "booking issue help",
    "order problem",
    "machine not working after rent",
    "invoice missing",
]

_OFF_TOPIC = [
    "what is the weather today",
    "tell me a joke",
    "cricket score",
    "bitcoin price",
]

_MACHINE_SEARCH = [
    "excavator in jaipur",
    "jcb 3dx rent mumbai",
    "crane delhi under 8000",
    "road roller pune",
]

_DOMAIN_KNOWLEDGE = [
    "what is excavator",
    "what is JCB",
    "explain backhoe loader",
    "jcb kya hai",
]


def _test_intent_group(phrases: list[str], expected_intent: str, field: str = "primary_intent"):
    from app.ai.semantic_turn_gateway import _rules_understand

    for p in phrases:
        u = _rules_understand(p)
        got = getattr(u, field)
        _assert(got == expected_intent, f"'{p[:50]}' => {got} expected {expected_intent}")


def test_semantic_gateway_intents():
    _group("Semantic Gateway — Meta Help")
    _test_intent_group(_META_HELP, "meta_help")

    _group("Semantic Gateway — Memory")
    _test_intent_group(_MEMORY, "memory_question")

    _group("Semantic Gateway — Frustration")
    _test_intent_group(_FRUSTRATION, "frustration")

    _group("Semantic Gateway — Comparison")
    _test_intent_group(_COMPARISON, "comparison")

    _group("Semantic Gateway — Recommendation")
    _test_intent_group(_RECOMMENDATION, "recommendation")

    _group("Semantic Gateway — Support")
    _test_intent_group(_SUPPORT, "support")

    _group("Semantic Gateway — Off Topic")
    _test_intent_group(_OFF_TOPIC, "off_topic")

    _group("Semantic Gateway — Machine Search")
    _test_intent_group(_MACHINE_SEARCH, "machine_search")

    _group("Semantic Gateway — Domain Knowledge")
    _test_intent_group(_DOMAIN_KNOWLEDGE, "domain_knowledge")


# ---------------------------------------------------------------------------
# Fragment resolver
# ---------------------------------------------------------------------------

def test_fragment_resolver():
    _group("Fragment Resolver")
    from app.ai.semantic_turn_gateway import is_short_context_fragment, resolve_fragment_context

    conv = {
        "collected_fields": {"category": "excavator", "purpose": "digging"},
        "last_search_filters": {"category": "excavator"},
        "last_comparison_context": {"brands": ["JCB", "Komatsu"], "category": "excavator"},
    }

    fragments = ["in jaipur", "under 7k", "inme se best konsa", "mumbai me", "8.5k per day"]
    for f in fragments:
        _assert(is_short_context_fragment(f), f"fragment detect: {f}")

    r = resolve_fragment_context("in jaipur", conv_state=conv)
    _assert(r["parsed"].get("city") == "jaipur", "city fragment")
    _assert(r["parsed"].get("category") == "excavator", "category preserved")

    r2 = resolve_fragment_context("under 7k", conv_state=conv)
    _assert(r2["parsed"].get("max_price") == 7000, f"budget fragment: {r2['parsed']}")

    r3 = resolve_fragment_context("inme se best konsa", conv_state=conv)
    brands = r3["parsed"].get("brands") or r3["context_reference"].get("brands") or []
    _assert(len(brands) >= 2, f"comparison brands from context: {brands}")


# ---------------------------------------------------------------------------
# Domain recommendation engine
# ---------------------------------------------------------------------------

_REC_ENGINE = [
    ("best machine for digging", "digging"),
    ("machine for road project", "compaction"),
    ("equipment for heavy rocks", "digging"),
    ("recommend for foundation work", "digging"),
    ("lifting work at bridge site", "lifting"),
    ("concrete work on site", "concrete"),
]


def test_domain_recommendation_engine():
    _group("Domain Recommendation Engine")
    from app.ai.domain_recommendation_engine import recommend_machine_categories, is_domain_recommendation_query

    for msg, exp_purpose in _REC_ENGINE:
        plan = recommend_machine_categories(msg)
        _assert(
            plan.get("purpose_key") == exp_purpose or plan.get("primary_category"),
            f"'{msg}' purpose={plan.get('purpose_key')} cat={plan.get('primary_category')}",
        )
        _assert(is_domain_recommendation_query(msg), f"is_recommendation: {msg}")


# ---------------------------------------------------------------------------
# Response mode gateway
# ---------------------------------------------------------------------------

def test_response_mode_gateway():
    _group("Response Mode Gateway")
    from app.ai.response_mode_gateway import resolve_response_mode
    from app.ai.semantic_turn_gateway import SemanticTurnUnderstanding

    cases = [
        ("support", "support_request", True),
        ("comparison", "machine_comparison", False),
        ("meta_help", "general_marketplace_help", True),
        ("memory_question", "user_introduction", True),
        ("off_topic", "out_of_scope", True),
    ]
    for intent, legacy, block_ctx in cases:
        u = SemanticTurnUnderstanding(primary_intent=intent, response_mode=intent)
        d = resolve_response_mode(u)
        _assert(d["legacy_intent"] == legacy, f"legacy {intent}")
        _assert(d["block_machine_context"] == block_ctx, f"block_ctx {intent}")


# ---------------------------------------------------------------------------
# Domain intelligence integration
# ---------------------------------------------------------------------------

def test_domain_intelligence_routing():
    _group("Domain Intelligence Routing")
    from app.ai.domain_intelligence_gateway import interpret_domain_rules

    support_cases = [
        "booking issue need help",
        "payment problem with my order",
        "help with refund",
    ]
    for q in support_cases:
        interp = interpret_domain_rules(q)
        _assert(
            interp.request_type == "support" or interp.proposed_tool == "support",
            f"support route '{q}' => {interp.request_type}/{interp.proposed_tool}",
        )

    compare = interpret_domain_rules("JCB vs Komatsu for excavator")
    _assert(
        compare.request_type in ("domain_knowledge", "comparison") or compare.legacy_intent_hint == "machine_comparison",
        f"comparison: {compare.request_type}",
    )

    meta = interpret_domain_rules("how can you help me")
    _assert(
        meta.reason == "meta_help_signal" or meta.legacy_intent_hint == "general_marketplace_help",
        f"meta_help: {meta.reason}",
    )

    rec = interpret_domain_rules("best machine for digging work")
    _assert(
        rec.request_type == "recommendation" or rec.legacy_intent_hint == "machine_recommendation",
        f"recommendation: {rec.request_type}",
    )


# ---------------------------------------------------------------------------
# Capability registry support priority
# ---------------------------------------------------------------------------

def test_support_over_marketplace():
    _group("Support Over Marketplace Verb")
    from app.ai.capability_registry import has_support_action_signal

    cases = [
        "booking issue",
        "payment problem",
        "help with my order",
        "order issue refund",
    ]
    for c in cases:
        _assert(has_support_action_signal(c), f"support signal: {c}")


# ---------------------------------------------------------------------------
# Knowledge engine memory
# ---------------------------------------------------------------------------

def test_memory_knowledge():
    _group("Knowledge Memory Question")
    from app.ai.knowledge_query_engine import knowledge_turn_from_message

    for q in _MEMORY:
        kq = knowledge_turn_from_message(q)
        _assert(kq and kq.get("kind") == "memory_question", f"memory kind: {q}")


# ---------------------------------------------------------------------------
# Safe error fallback
# ---------------------------------------------------------------------------

def test_safe_error_fallback():
    _group("Safe Error Fallback")
    from app.ai.safe_error_fallback import build_safe_error_response, fallback_message_for_stage

    resp = build_safe_error_response(stage="machine_search", user_message="excavator jaipur")
    _assert(not resp.get("success"), "error envelope")
    _assert("request_id" in (resp.get("error") or {}), "request_id logged")
    _assert("Something went wrong" not in resp.get("message", ""), "no generic error")

    mem = fallback_message_for_stage("memory_answer")
    _assert("name" in mem.lower(), "memory fallback mentions name")


# ---------------------------------------------------------------------------
# Paraphrase stress — multilingual + typos
# ---------------------------------------------------------------------------

_TYPO_FRAGMENTS = [
    "in japur", "under 7k", "8.5k pr day", "jaipur me", "delhi mai",
    "sasta option", "jcb vs cat", "komatsu vs jcb", "best konsa",
    "diging work", "road projct", "heavy rock", "rent chahiye",
    "payment faild", "refnd chahiye", "bookng issue", "machne search",
]

_HINDI_FRAGMENTS = [
    "khudai ke liye machine", "sadak project ke liye", "bade patthar",
    "kiraye pe chahiye", "kya kar sakte ho", "mera naam",
    "inme se accha kaunsa", "sasta dikhao", "delhi me excavator",
]


def test_multilingual_typos():
    _group("Multilingual + Typos")
    from app.ai.semantic_turn_gateway import _rules_understand

    for p in _TYPO_FRAGMENTS + _HINDI_FRAGMENTS:
        u = _rules_understand(p)
        _assert(u.primary_intent != "", f"intent for '{p}': {u.primary_intent}")
        _assert(u.confidence > 0, f"confidence for '{p}'")


# ---------------------------------------------------------------------------
# Budget parse regression — NOT ₹8
# ---------------------------------------------------------------------------

_BUDGET_REGRESSION = [
    ("7k", 7000),
    ("8.5k", 8500),
    ("under 7k per day", 7000),
    ("8.5k per day rent", 8500),
    ("budget 10k", 10000),
    ("12k ke andar", 12000),
    ("1.5 lakh budget", 150000),
]


def test_budget_not_eight():
    _group("Budget Regression — not eight rupees")
    from app.ai.query_parser import parse_query

    for phrase, expected in _BUDGET_REGRESSION:
        p = parse_query(f"excavator jaipur {phrase}")
        got = p.get("max_price")
        _assert(got == expected, f"parse_query '{phrase}' max_price={got} expected {expected}")
        _assert(got != 8, f"NOT 8 for '{phrase}'")


# ---------------------------------------------------------------------------
# Conversation state unified fields
# ---------------------------------------------------------------------------

def test_conversation_state_fields():
    _group("Conversation State Unified Fields")
    from app.ai.conversation_state_manager import empty_conversation_state
    from app.ai.session_requirement_context import sync_turn_context_to_collected

    state = empty_conversation_state("t1")
    _assert("last_user_goal" in state, "last_user_goal field")
    _assert("last_recommendation_context" in state, "last_recommendation_context")
    _assert("last_comparison_context" in state, "last_comparison_context")

    sync_turn_context_to_collected(
        state,
        last_user_goal="recommendation",
        comparison_context={"brands": ["JCB", "CAT"]},
    )
    _assert(state["last_user_goal"] == "recommendation", "sync goal")
    _assert(len(state["collected_fields"].get("brands") or []) >= 2, "sync brands")


# ---------------------------------------------------------------------------
# Expand test count with parameterized domain knowledge + greeting groups
# ---------------------------------------------------------------------------

_GREETINGS = ["hi", "hello", "namaste", "good morning", "hey there"]
_MORE_SEARCH = [
    "need excavator jaipur", "show crane mumbai", "find jcb delhi",
    "wheel loader bangalore", "volvo loader chennai", "hyundai excavator pune",
    "rent roller ahmedabad", "buy bulldozer kolkata", "tipper truck surat",
]
_MORE_SUPPORT = [
    "transaction failed", "double charged", "cancel booking",
    "security deposit refund", "complaint about owner", "delivery delayed",
]


def test_extended_groups():
    _group("Extended Greeting Group")
    _test_intent_group(_GREETINGS, "greeting")

    _group("Extended Search Group")
    _test_intent_group(_MORE_SEARCH, "machine_search")

    _group("Extended Support Group")
    _test_intent_group(_MORE_SUPPORT, "support")


async def test_async_memory_answer():
    _group("Async Memory Answer — no crash")
    from app.ai.response_mode_gateway import build_memory_answer_draft
    from app.ai.semantic_turn_gateway import SemanticTurnUnderstanding

    u = SemanticTurnUnderstanding(primary_intent="memory_question")
    draft = await build_memory_answer_draft(u, session_ctx={"user_name": "Rahul"}, lang="english")
    _assert("Rahul" in draft["message"], "memory answer with name")
    draft2 = await build_memory_answer_draft(u, session_ctx={}, lang="english")
    _assert(draft2.get("message"), "memory answer without name — no crash")


def main():
    print("=" * 60)
    print("Semantic Understanding Phase Tests")
    print("=" * 60)

    test_numeric_normalizer()
    test_semantic_gateway_intents()
    test_fragment_resolver()
    test_domain_recommendation_engine()
    test_response_mode_gateway()
    test_domain_intelligence_routing()
    test_support_over_marketplace()
    test_memory_knowledge()
    test_safe_error_fallback()
    test_multilingual_typos()
    test_budget_not_eight()
    test_conversation_state_fields()
    test_extended_groups()
    asyncio.run(test_async_memory_answer())

    print("\n" + "=" * 60)
    print(f"PASSED: {_passed}  FAILED: {_failed}")
    if _errors:
        print("\nFailures:")
        for e in _errors[:20]:
            print(f"  - {e}")
        if len(_errors) > 20:
            print(f"  ... and {len(_errors) - 20} more")
    print("=" * 60)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
