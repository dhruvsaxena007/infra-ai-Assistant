#!/usr/bin/env python3
"""Smoke-test intent classifier against required test cases."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.intent_classifier import classify_intent

NO_SEARCH = {
    "hi", "what can you do", "help me", "machine kaise book karu",
    "InfraForge kaise kaam karta hai",
    "I ordered a machine and I have a problem", "booking me issue hai",
    "machine abhi tak nahi aayi", "wrong machine delivered",
    "order status kya hai", "I want refund", "refund chahiye",
    "machine return karni hai", "payment wapas chahiye",
    "cancel booking and refund", "payment failed",
    "amount deducted booking not confirmed", "invoice chahiye",
    "security deposit issue", "receipt nahi mili",
    "machine kab deliver hogi", "transport charges kya hain",
    "site par machine kaise ayegi", "owner se baat karni hai",
    "seller ka number chahiye", "contact owner",
    "weather in Jaipur", "tell me a joke", "who is prime minister",
}

SHOULD_SEARCH = {
    "crawler drill in Jaipur", "JCB in Delhi", "excavator in Mumbai",
    "road roller chahiye",
}

CONTEXT = {"last_filters": {"category": "road roller", "city": "pune"}}


async def main():
    fails = 0
    for msg in sorted(NO_SEARCH):
        r = await classify_intent(msg)
        if r["should_search_machines"]:
            print(f"FAIL (should NOT search): {msg!r} -> {r['intent']}")
            fails += 1
        else:
            print(f"OK   no-search: {msg!r} -> {r['intent']} ({r['confidence']})")

    for msg in sorted(SHOULD_SEARCH):
        r = await classify_intent(msg)
        if not r["should_search_machines"]:
            print(f"FAIL (should search): {msg!r} -> {r['intent']}")
            fails += 1
        else:
            print(f"OK   search: {msg!r} -> {r['intent']}")

    r = await classify_intent("Pune", CONTEXT)
    if not r["should_search_machines"]:
        print(f"FAIL follow-up Pune: {r}")
        fails += 1
    else:
        print(f"OK   follow-up Pune -> {r['intent']}")

    print(f"\n{failures if (failures := fails) else 'All'} failures")
    return fails


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
