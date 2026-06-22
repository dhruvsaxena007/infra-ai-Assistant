"""
Live multi-turn /chat simulation — reproduces screenshot flows through real pipeline.
Run: python scripts/test_live_multiturn_chat.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AI_INTENT_MODE", "rules_first")
os.environ.setdefault("DOMAIN_INTELLIGENCE_MODE", "hybrid")
os.environ.setdefault("ASSISTANT_DEBUG", "true")


class _FakeDB:
    """Minimal DB stub — returns empty search results."""

    equipmentcategories = None

    def __init__(self):
        self.equipmentcategories = _FakeCollection()
        self.machines = _FakeCollection()
        self.listings = _FakeCollection()

    def __getattr__(self, name):
        return _FakeCollection()


class _FakeCollection:
    def find(self, *a, **k):
        return _FakeCursor()

    async def find_one(self, *a, **k):
        return None

    async def insert_one(self, *a, **k):
        return None

    async def update_one(self, *a, **k):
        return None

    async def count_documents(self, *a, **k):
        return 0


class _FakeCursor:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def to_list(self, *a, **k):
        return []


def _msg(resp: dict) -> str:
    return (resp.get("message") or resp.get("data", {}).get("message") or "")[:200]


def _filters(resp: dict) -> dict:
    ctx = (resp.get("data") or {}).get("context") or {}
    return ctx.get("filters") or {}


async def _turn(session_id: str, text: str, db) -> dict:
    from app.chatbot.chatbot_service import chatbot_response

    return await chatbot_response(session_id, text, db)


async def run_flow(name: str, turns: list[str], checks: list) -> None:
    from app.chatbot.chatbot_service import _get_last_filters
    from app.ai.conversation_state_manager import load_conversation_state

    session_id = f"test-{name}-{uuid.uuid4().hex[:8]}"
    db = _FakeDB()
    print(f"\n=== FLOW: {name} (session={session_id}) ===")
    last_resp = None
    for i, text in enumerate(turns, 1):
        last_resp = await _turn(session_id, text, db)
        f = _filters(last_resp)
        print(f"  [{i}] USER: {text}")
        print(f"      BOT: {_msg(last_resp)}")
        print(f"      filters: {f}")
    state = load_conversation_state(session_id)
    collected = (state or {}).get("collected_fields") or {}
    lf = _get_last_filters(session_id)
    print(f"  STATE collected: {collected}")
    print(f"  STATE last_filters: {lf}")
    for check_fn, label in checks:
        ok, detail = check_fn(last_resp, collected, lf, turns)
        status = "OK" if ok else "FAIL"
        print(f"  CHECK {status}: {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            raise AssertionError(f"{name}: {label} — {detail}")


def main():
    asyncio.run(_run_all())


async def _run_all():
    # Flow 1: transport context then digging revision
    await run_flow(
        "digging_after_transport",
        ["truck for transporting sand", "gidding", "machine need for digging in jaipur on rent under 20k"],
        [
            (
                lambda r, c, lf, t: (
                    (lf.get("category") or c.get("category") or "").lower() not in ("dump truck", "tipper")
                    or "excavator" in str(lf.get("category", "")).lower()
                    or "excavator" in str(c.get("category", "")).lower()
                    or "digging" in str(c.get("purpose", "")).lower(),
                    f"cat={lf.get('category') or c.get('category')} purpose={c.get('purpose')}",
                )
            ),
        ],
    )

    # Flow 2: kota -> jaipur -> truck should NOT reset
    await run_flow(
        "kota_jaipur_truck",
        [
            "i need a machine for transporting sand in kota",
            "no problem i also need in jaipur also",
            "i need a truck for transporting sand",
        ],
        [
            (
                lambda r, c, lf, t: (
                    "jaipur" in str(c.get("city", "")).lower() or "jaipur" in str(lf.get("city", "")).lower(),
                    f"city lost: collected={c.get('city')} filters={lf.get('city')}",
                )
            ),
            (
                lambda r, c, lf, t: (
                    "happy to help" not in _msg(r).lower()
                    or "tell me" not in _msg(r).lower()
                    or bool(c.get("city")),
                    f"generic reset: {_msg(r)[:80]}",
                )
            ),
        ],
    )

    # Flow 3: bike should boundary not dump truck search
    await run_flow(
        "bike_boundary",
        ["i want to rent a bike"],
        [
            (
                lambda r, c, lf, t: (
                    "dump truck" not in _msg(r).lower()
                    and (
                        "supported" in _msg(r).lower()
                        or "doesn't" in _msg(r).lower()
                        or "not" in _msg(r).lower()
                        or "infraforge" in _msg(r).lower()
                    ),
                    _msg(r)[:120],
                )
            ),
        ],
    )

    # Flow 4: backpack unrelated
    await run_flow(
        "backpack_boundary",
        ["do you have skybags backpack ?"],
        [
            (
                lambda r, c, lf, t: (
                    "good to connect" not in _msg(r).lower()[:30]
                    or "machine" in _msg(r).lower(),
                    _msg(r)[:120],
                )
            ),
        ],
    )

    print("\n=== ALL LIVE MULTITURN FLOWS PASSED ===")


if __name__ == "__main__":
    main()
