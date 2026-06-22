"""
Per-turn context / memory evaluation for sequential conversation eval.

Tracks rolling search context across a conversation and checks whether
follow-up queries (cheaper, same city, brand, operator, etc.) retain
category, city, and related filters from earlier turns.
"""

from __future__ import annotations

import re
from typing import Any

# Turns that should NOT require search-context memory
_NO_MEMORY_ROLES = frozenset({"none", "greeting", "thanks", "support", "platform", "compare"})

# Follow-up roles that must inherit prior search context
_REFINE_ROLES = frozenset({
    "refine_budget",
    "refine_cheaper",
    "refine_higher_budget",
    "brand_filter",
    "operator",
    "more_options",
    "resume_search",
})

_CITY_SWITCH_ROLES = frozenset({"city_switch", "demonstrative_city"})


def _norm(val: Any) -> str:
    return (val or "").strip().lower()


def _filters_from_meta(meta: dict) -> dict:
    return {
        "category": _norm(meta.get("category")),
        "city": _norm(meta.get("city")),
        "max_price": meta.get("max_price"),
        "brand": _norm(meta.get("brand")),
    }


def infer_memory_role(message: str) -> str:
    """Guess memory role from user text when not set explicitly."""
    m = message.lower().strip()
    if re.search(r"^(hi|hello|hey|namaste|good morning|good evening)\b", m):
        return "greeting"
    if re.search(r"how are you|kaise ho|kaise hain", m):
        return "none"
    if re.search(r"thanks|thank you|dhanyavaad|shukriya|bye\b", m):
        return "thanks"
    if re.search(r"payment|refund|booking (issue|problem|cancel)|deposit|invoice|support", m):
        return "support"
    if re.search(r"compare .+ vs ", m):
        return "compare"
    if re.search(r"same in |delhi me bhi same|mumbai me bhi|bhi same chahiye", m):
        return "city_switch"
    if re.search(r"cheaper|sasta|kam budget|aur sasta", m):
        return "refine_cheaper"
    if re.search(r"higher budget|budget badha|zyada budget", m):
        return "refine_higher_budget"
    if re.search(r"under \d+|se kam|budget", m) and re.search(r"\d", m):
        return "refine_budget"
    if re.search(r"jcb|cat brand|brand only|volvo|komatsu", m):
        return "brand_filter"
    if re.search(r"operator", m):
        return "operator"
    if re.search(r"aur options|more options|dikhao phir|wapas .+ dikhao", m):
        return "more_options"
    if re.search(r"machine in |me machine|equipment in ", m):
        return "establish_city"
    if re.search(
        r"^(excavator|crane|roller|mixer|dozer|tipper|loader|drill|bulldozer|jcb)\b",
        m,
    ):
        return "establish_category"
    if re.search(r"what machines are available|kaun kaun si machines|list all machines", m):
        return "city_inventory"
    return "none"


class RollingContext:
    """Last known search context within a conversation."""

    def __init__(self) -> None:
        self.category: str = ""
        self.city: str = ""
        self.max_price: int | None = None
        self.brand: str = ""
        self.active: bool = False

    def snapshot(self) -> dict:
        return {
            "category": self.category,
            "city": self.city,
            "max_price": self.max_price,
            "brand": self.brand,
        }

    def update_from_filters(self, filters: dict) -> None:
        cat = _norm(filters.get("category"))
        city = _norm(filters.get("city"))
        if cat:
            self.category = cat
            self.active = True
        if city:
            self.city = city
            self.active = True
        if filters.get("max_price") is not None:
            self.max_price = filters.get("max_price")
        brand = _norm(filters.get("brand"))
        if brand:
            self.brand = brand

    def update_from_expect(self, expect: dict) -> None:
        if expect.get("category"):
            self.category = _norm(expect["category"])
            self.active = True
        if expect.get("city"):
            self.city = _norm(expect["city"])
            self.active = True


def evaluate_turn_memory(
    *,
    message: str,
    meta: dict,
    expect: dict,
    memory_role: str | None,
    rolling: RollingContext,
) -> dict:
    """
    Evaluate whether this turn correctly used prior conversation context.

    Returns dict with memory_required, memory_remembered, expected, actual, notes, failures.
    """
    role = memory_role or infer_memory_role(message)
    actual = _filters_from_meta(meta)
    used_ctx = bool(meta.get("used_previous_context"))
    failures: list[str] = []
    notes: list[str] = []
    prior_snapshot = rolling.snapshot()

    memory_required = role not in _NO_MEMORY_ROLES and (
        role in _REFINE_ROLES
        or role in _CITY_SWITCH_ROLES
        or role in ("establish_category", "resume_search")
        or bool(expect.get("category") or expect.get("city"))
    )

    expected: dict = {}

    if role == "establish_city":
        exp_city = _norm(expect.get("city"))
        if exp_city:
            expected["city"] = exp_city
        if exp_city and actual["city"] and actual["city"] != exp_city:
            failures.append(f"city not set yet: got '{actual['city']}' want '{exp_city}'")

    elif role == "establish_category":
        exp_cat = _norm(expect.get("category") or rolling.category)
        exp_city = _norm(expect.get("city") or rolling.city)
        if exp_cat:
            expected["category"] = exp_cat
        if exp_city:
            expected["city"] = exp_city
        if rolling.active and exp_cat and actual["category"] != exp_cat:
            failures.append(f"category: got '{actual['category']}' expected '{exp_cat}' (from context)")
        if rolling.city and exp_city and actual["city"] != exp_city:
            failures.append(f"city: got '{actual['city']}' expected '{exp_city}' (from context)")

    elif role in _REFINE_ROLES or role == "resume_search":
        exp_cat = _norm(expect.get("category") or rolling.category)
        exp_city = _norm(expect.get("city") or rolling.city)
        if exp_cat:
            expected["category"] = exp_cat
        if exp_city:
            expected["city"] = exp_city
        if rolling.active:
            if exp_cat and actual["category"] != exp_cat:
                failures.append(
                    f"context lost — category: got '{actual['category']}' expected '{exp_cat}'"
                )
            if exp_city and actual["city"] != exp_city:
                failures.append(
                    f"context lost — city: got '{actual['city']}' expected '{exp_city}'"
                )
            if not used_ctx and role in _REFINE_ROLES:
                notes.append("used_previous_context=false but follow-up expected prior search")
        else:
            notes.append("no prior search context established")

    elif role in _CITY_SWITCH_ROLES:
        exp_cat = _norm(expect.get("category") or rolling.category)
        exp_city = _norm(expect.get("city"))
        if exp_cat:
            expected["category"] = exp_cat
        if exp_city:
            expected["city"] = exp_city
        if rolling.active and exp_cat and actual["category"] != exp_cat:
            failures.append(
                f"city switch lost category: got '{actual['category']}' expected '{exp_cat}'"
            )
        if exp_city and actual["city"] != exp_city:
            failures.append(
                f"city switch failed: got '{actual['city']}' expected '{exp_city}'"
            )

    elif role == "support":
        memory_required = False
        notes.append("support turn — search context pause expected")

    elif role in ("greeting", "thanks", "none", "compare", "city_inventory", "platform"):
        memory_required = False

    # Merge expect into expected for report display
    for key in ("category", "city"):
        if expect.get(key) and key not in expected:
            expected[key] = _norm(expect[key])

    remembered: bool | None
    if not memory_required:
        remembered = None
    else:
        remembered = len(failures) == 0

    # Update rolling state after evaluation (use response filters, fallback expect)
    if actual["category"] or actual["city"]:
        rolling.update_from_filters(actual)
    elif remembered and expected:
        rolling.update_from_expect(expected)
    elif role == "establish_category" and expect:
        rolling.update_from_expect(expect)

    if used_ctx and remembered:
        notes.append("backend flagged used_previous_context=true")
    elif memory_required and remembered is False:
        notes.append("follow-up did not retain prior filters")

    return {
        "memory_role": role,
        "memory_required": memory_required,
        "memory_remembered": remembered,
        "expected_context": expected,
        "actual_context": actual,
        "prior_context": prior_snapshot,
        "used_previous_context": used_ctx,
        "memory_notes": "; ".join(notes) if notes else "",
        "memory_failures": failures,
    }
