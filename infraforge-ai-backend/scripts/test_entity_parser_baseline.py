"""
Phase 2 — Generalized entity / parser baseline tests.

Run: python scripts/test_entity_parser_baseline.py
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.query_parser import parse_query  # noqa: E402


def _check(label: str, ok: bool, detail: str = "") -> tuple[str, bool, str]:
    tag = "PASS" if ok else "FAIL"
    line = f"  [{tag}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return label, ok, detail


def _brands_include(parsed: dict, *expected: str) -> bool:
    brands = [b.upper() for b in (parsed.get("brands") or [])]
    canonical = [b.upper() for b in expected]
    return all(any(e in b or b in e for b in brands) for e in canonical)


def main() -> int:
    failed = 0
    total = 0

    def assert_case(label, ok, detail=""):
        nonlocal failed, total
        total += 1
        if not ok:
            failed += 1
        _check(label, ok, detail)

    print("\n=== Entity / Parser Baseline (Phase 2) ===\n")

    # Brand + category
    cases_brand_cat = [
        ("JCB roadroller", "JCB", "road roller"),
        ("Hyundai excavator", "Hyundai", "excavator"),
        ("Komatsu bulldozer", "Komatsu", "bulldozer"),
        ("CAT crane", "CAT", "crane"),
        ("Tata Hitachi excavator", "Tata Hitachi", "excavator"),
        ("Volvo wheel loader", "Volvo", "wheel loader"),
        ("Sany concrete pump", "SANY", "concrete pump"),
    ]
    for query, brand, category in cases_brand_cat:
        p = parse_query(query)
        ok = (
            (p.get("brand") or "").upper() == brand.upper()
            and p.get("category") == category
        )
        assert_case(
            f"brand+category: {query!r}",
            ok,
            f"brand={p.get('brand')!r} cat={p.get('category')!r}",
        )

    # Brand-only
    for query, brand in [("Hyundai", "Hyundai"), ("JCB", "JCB")]:
        p = parse_query(query)
        ok = (p.get("brand") or "").upper() == brand.upper() and not p.get("category")
        assert_case(
            f"brand-only: {query!r}",
            ok,
            f"brand={p.get('brand')!r} cat={p.get('category')!r}",
        )

    # Model-specific
    p = parse_query("JCB 3DX")
    ok = (
        (p.get("brand") or "").upper() == "JCB"
        and p.get("category") == "backhoe loader"
        and (p.get("model") or "").upper().replace(" ", "") == "3DX"
    )
    assert_case("model: JCB 3DX", ok, str(p))

    p = parse_query("JCB 3DX road roller")
    ok = (
        p.get("category") == "road roller"
        and (p.get("brand") or "").upper() == "JCB"
        and "model_category_conflict" in (p.get("validation_notes") or [])
    )
    assert_case("conflict: JCB 3DX road roller", ok, str(p))

    # Road roller aliases
    for query, city in [
        ("roadroller in jaipur", "jaipur"),
        ("road-roller in delhi", "delhi"),
    ]:
        p = parse_query(query)
        ok = p.get("category") == "road roller" and p.get("city") == city
        assert_case(f"alias+city: {query!r}", ok, str(p))

    p = parse_query("road roller chahiye")
    assert_case(
        "alias: road roller chahiye",
        p.get("category") == "road roller",
        f"cat={p.get('category')!r}",
    )

    p = parse_query("konse brands ke roadroller hai tumhare pas")
    assert_case(
        "alias: Hindi roadroller brand query",
        p.get("category") == "road roller",
        f"cat={p.get('category')!r}",
    )

    # Comparison / multi-brand
    p = parse_query("JCB ke roadroller acche hote hai ya CAT ke")
    ok = (
        p.get("category") == "road roller"
        and _brands_include(p, "JCB", "CAT")
        and p.get("category") != "backhoe loader"
    )
    assert_case("comparison: JCB vs CAT roadroller", ok, str(p))

    p = parse_query("Hyundai excavator better hai ya Komatsu excavator")
    ok = (
        p.get("category") == "excavator"
        and _brands_include(p, "Hyundai", "Komatsu")
    )
    assert_case("comparison: Hyundai vs Komatsu excavator", ok, str(p))

    p = parse_query("Tata Hitachi aur Volvo wheel loader compare karo")
    ok = (
        p.get("category") == "wheel loader"
        and _brands_include(p, "Tata Hitachi", "Volvo")
    )
    assert_case("comparison: Tata Hitachi vs Volvo wheel loader", ok, str(p))

    print(f"\nEntity tests: {total - failed}/{total} passed, {failed} failed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
