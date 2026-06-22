"""
No Result Recovery Engine — safe factual alternatives when exact search fails.

Backend decides recovery options from MongoDB/catalog data.
Response gateway explains them naturally; this module does not hardcode final wording.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.category_mapping import category_label
from app.ai.tool_permission_matrix import TOOL_MONGODB_SEARCH, is_tool_allowed
from app.chatbot.assistant_intelligence import (
    map_purpose_to_categories,
    similar_category_keys,
    similar_category_suggestions,
)

RECOVERY_TYPES = frozenset({
    "nearby_or_alternate_city",
    "budget_relaxation",
    "similar_category",
    "brand_alternative",
    "listing_type_alternative",
    "broaden_filters",
    "ask_missing_context",
    "no_safe_recovery",
    "comparison_partial",
    "brand_inventory_empty",
    "support_missing_details",
    "ask_document_upload",
    "image_clarification",
})

_SEARCH_INTENTS = frozenset({
    "machine_search",
    "rent_machine",
    "buy_machine",
    "machine_availability",
    "price_query",
    "cheaper_option_query",
    "higher_budget_query",
    "followup_search_refinement",
    "machine_recommendation",
    "machine_brand_query",
    "machine_comparison",
    "comparison_request",
})


def empty_recovery_output() -> dict[str, Any]:
    return {
        "recovery_type": "no_safe_recovery",
        "recovery_actions": [],
        "safe_alternatives": [],
        "suggested_filters": [],
        "auto_retried": False,
        "auto_retry_allowed": False,
        "auto_retry_results": {},
        "message_facts": {},
        "suggestions": [],
        "next_best_action": "contact_support",
    }


def _permission_allows_search(
    intent: str,
    permission_decision: dict[str, Any] | None,
) -> bool:
    if permission_decision is not None:
        if not permission_decision.get("permission_passed", True):
            return False
        if permission_decision.get("allowed_tool") not in (
            TOOL_MONGODB_SEARCH,
            "mongodb_search",
            "mongodb_brand_inventory",
        ):
            return bool(permission_decision.get("should_search_machines"))
    return is_tool_allowed(intent or "machine_search", TOOL_MONGODB_SEARCH)


def _not_found_reason(filters: dict[str, Any], tool_result: dict[str, Any]) -> str:
    parts: list[str] = []
    cat = filters.get("category")
    city = filters.get("city")
    brand = filters.get("brand")
    max_price = filters.get("max_price")
    listing_type = filters.get("listing_type")
    if cat:
        parts.append(f"category={category_label(cat)}")
    if city:
        parts.append(f"city={str(city).title()}")
    if brand:
        parts.append(f"brand={brand}")
    if max_price is not None:
        parts.append(f"budget_under={max_price}")
    if listing_type:
        parts.append(f"listing_type={listing_type}")
    if tool_result.get("fallback_reason"):
        return str(tool_result["fallback_reason"])
    if parts:
        return "no_exact_match_for:" + ",".join(parts)
    return "no_exact_match"


async def _try_auto_retry(
    database,
    *,
    intent: str,
    filters: dict[str, Any],
    retry_filters: dict[str, Any],
    permission_decision: dict[str, Any] | None,
    limit: int = 8,
) -> tuple[list[dict], str]:
    """Run one safe auto-retry search. Returns (machines, retry_label)."""
    if not _permission_allows_search(intent, permission_decision):
        return [], "permission_blocked"
    from app.utils.machine_repository import search_by_filters

    merged = {**filters, **retry_filters}
    cat = merged.get("category")
    city = merged.get("city")
    results = await search_by_filters(
        database,
        category=cat,
        city=city,
        max_price=merged.get("max_price"),
        brand=merged.get("brand"),
        model=merged.get("model"),
        condition=merged.get("condition"),
        listing_type=merged.get("listing_type"),
        rent_type=merged.get("rent_type"),
        limit=limit,
        exact_category=bool(cat),
        filters=merged,
    )
    label = ",".join(f"{k}={v}" for k, v in retry_filters.items() if v is not None)
    return results, label


async def run_no_result_recovery(
    database,
    *,
    intent: str = "machine_search",
    selected_action: str = "",
    filters: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    conversation_state: dict[str, Any] | None = None,
    permission_decision: dict[str, Any] | None = None,
    purpose_key: str | None = None,
    lang: str = "english",
) -> dict[str, Any]:
    """
    Analyze no-result context, optionally auto-retry, return recovery plan.
    Never invents machines, prices, brands, or cities.
    """
    from app.utils.machine_repository import (
        available_brands_for_category_city,
        available_cities_for_category,
        min_price_for_category_city,
        nearby_cities_with_category_listings,
    )

    filt = dict(filters or {})
    tool = dict(tool_result or {})
    state = dict(conversation_state or {})
    out = empty_recovery_output()
    intent = (intent or "machine_search").lower()

    if intent in (
        "payment_issue", "refund_return", "order_issue", "delivery_issue",
        "invoice_issue", "security_deposit", "support_request",
    ):
        out["recovery_type"] = "support_missing_details"
        out["next_best_action"] = "collect_support_details"
        out["message_facts"] = {"not_found_reason": "support_context_missing"}
        out["suggestions"] = ["Share booking ID", "Talk to support"]
        return out

    if intent == "document_question":
        out["recovery_type"] = "ask_document_upload"
        out["next_best_action"] = "ask_document_upload"
        out["suggestions"] = ["Upload PDF", "Ask another question"]
        return out

    if intent in ("image_followup", "image_search_followup", "image_context_followup"):
        out["recovery_type"] = "image_clarification"
        out["next_best_action"] = "ask_image_clarification"
        out["suggestions"] = ["Upload clearer image", "Search by text"]
        return out

    if intent not in _SEARCH_INTENTS and not filt.get("category"):
        out["recovery_type"] = "ask_missing_context"
        out["next_best_action"] = "ask_missing_fields"
        out["message_facts"] = {"missing": ["category_or_purpose", "city"]}
        out["suggestions"] = ["Excavator", "Road Roller", "Jaipur", "Delhi"]
        return out

    auto_allowed = _permission_allows_search(intent, permission_decision)
    out["auto_retry_allowed"] = auto_allowed

    category = filt.get("category")
    city = (filt.get("city") or "").strip().lower() or None
    brand = filt.get("brand")
    max_price = filt.get("max_price")
    listing_type = filt.get("listing_type")
    nearby_allowed = filt.get("nearby_allowed", True)
    purpose_key = purpose_key or filt.get("purpose_key") or (state.get("collected_fields") or {}).get("purpose")

    not_found = _not_found_reason(filt, tool)
    out["message_facts"] = {
        "not_found_reason": not_found,
        "filters_used": {k: v for k, v in filt.items() if v is not None},
    }

    safe_alternatives: list[dict[str, Any]] = []
    suggested_filters: list[dict[str, Any]] = []
    recovery_actions: list[str] = []

    # --- Budget too low -----------------------------------------------------
    if max_price is not None and category:
        min_price = await min_price_for_category_city(
            database,
            category=category,
            city=city,
            listing_type=listing_type,
        )
        if min_price is not None and min_price > max_price:
            out["recovery_type"] = "budget_relaxation"
            recovery_actions.append("suggest_budget_increase")
            safe_alternatives.append({
                "type": "budget_relaxation",
                "min_available_price": min_price,
                "requested_max": max_price,
                "category": category,
                "city": city,
            })
            suggested_filters.append({
                "category": category,
                "city": city,
                "max_price": None,
                "listing_type": listing_type,
                "action": "remove_budget_cap",
            })
            if auto_allowed and city:
                retry_machines, _ = await _try_auto_retry(
                    database,
                    intent=intent,
                    filters=filt,
                    retry_filters={"max_price": None},
                    permission_decision=permission_decision,
                )
                if retry_machines:
                    out["auto_retried"] = True
                    out["auto_retry_results"] = {
                        "machines": retry_machines[:8],
                        "count": len(retry_machines),
                        "retry_type": "budget_relaxation",
                    }
                    out["next_best_action"] = "show_relaxed_budget_results"
                    out["suggestions"] = _recovery_suggestions(out)
                    return out

    # --- Brand unavailable --------------------------------------------------
    if brand and category:
        available_brands = await available_brands_for_category_city(
            database,
            category=category,
            city=city,
        )
        if available_brands and brand.lower() not in {b.lower() for b in available_brands}:
            out["recovery_type"] = "brand_alternative"
            recovery_actions.append("show_other_brands")
            safe_alternatives.append({
                "type": "brand_alternative",
                "requested_brand": brand,
                "available_brands": available_brands[:8],
            })
            suggested_filters.append({
                "category": category,
                "city": city,
                "brand": None,
                "action": "drop_brand_filter",
            })
            if auto_allowed:
                retry_machines, _ = await _try_auto_retry(
                    database,
                    intent=intent,
                    filters=filt,
                    retry_filters={"brand": None, "model": None},
                    permission_decision=permission_decision,
                )
                if retry_machines:
                    out["auto_retried"] = True
                    out["auto_retry_results"] = {
                        "machines": retry_machines[:8],
                        "count": len(retry_machines),
                        "retry_type": "brand_alternative",
                    }
                    out["next_best_action"] = "show_other_brands_results"
                    out["suggestions"] = _recovery_suggestions(out, available_brands=available_brands)
                    return out

    # --- Similar category (purpose mapping or similar map) ------------------
    similar_cats: list[str] = []
    if purpose_key:
        similar_cats = map_purpose_to_categories(purpose_key)[:4]
    if category:
        similar_cats = list(dict.fromkeys(similar_cats + similar_category_keys(category)))[:4]

    if category and city and similar_cats and auto_allowed:
        from app.utils.machine_repository import search_by_filters

        for sim_cat in similar_cats:
            if sim_cat.lower() == (category or "").lower():
                continue
            batch = await search_by_filters(
                database,
                category=sim_cat,
                city=city,
                max_price=max_price,
                listing_type=listing_type,
                limit=3,
                exact_category=True,
            )
            if batch:
                safe_alternatives.append({
                    "type": "similar_category",
                    "requested_category": category,
                    "similar_category": sim_cat,
                    "count": len(batch),
                })
                suggested_filters.append({
                    "category": sim_cat,
                    "city": city,
                    "action": "try_similar_category",
                })
                if not out.get("auto_retried"):
                    out["auto_retried"] = True
                    out["auto_retry_results"] = {
                        "machines": batch[:8],
                        "count": len(batch),
                        "retry_type": "similar_category",
                        "matched_category": sim_cat,
                    }
                    out["recovery_type"] = "similar_category"
                    out["next_best_action"] = "show_similar_category_results"
                    out["suggestions"] = _recovery_suggestions(
                        out,
                        similar_categories=similar_category_suggestions(category),
                    )
                    return out
                break
    elif category and city and similar_cats and not auto_allowed:
        for sim_cat in similar_cats[:2]:
            if sim_cat.lower() != (category or "").lower():
                suggested_filters.append({
                    "category": sim_cat,
                    "city": city,
                    "action": "try_similar_category",
                })
                safe_alternatives.append({
                    "type": "similar_category",
                    "requested_category": category,
                    "similar_category": sim_cat,
                    "probe_skipped": True,
                })
                out["recovery_type"] = "similar_category"
                break

    # --- Listing type alternative -------------------------------------------
    if listing_type in ("rent", "buy") and category:
        alt_type = "buy" if listing_type == "rent" else "rent"
        alt_machines, _ = await _try_auto_retry(
            database,
            intent=intent,
            filters=filt,
            retry_filters={"listing_type": alt_type},
            permission_decision=permission_decision,
            limit=3,
        )
        if alt_machines:
            safe_alternatives.append({
                "type": "listing_type_alternative",
                "requested_listing_type": listing_type,
                "available_listing_type": alt_type,
            })
            suggested_filters.append({
                "category": category,
                "city": city,
                "listing_type": alt_type,
                "action": "switch_listing_type",
            })
            if auto_allowed and not out.get("auto_retried"):
                out["auto_retried"] = True
                out["auto_retry_results"] = {
                    "machines": alt_machines[:8],
                    "count": len(alt_machines),
                    "retry_type": "listing_type_alternative",
                }
                out["recovery_type"] = "listing_type_alternative"
                out["next_best_action"] = "show_listing_type_alternative"
                out["suggestions"] = _recovery_suggestions(out)
                return out

    # --- Nearby / alternate city (DB-backed only) ---------------------------
    if city and category and nearby_allowed:
        nearby = await nearby_cities_with_category_listings(
            database,
            category=category,
            city=city,
            limit=3,
        )
        if nearby:
            out["recovery_type"] = "nearby_or_alternate_city"
            recovery_actions.append("suggest_nearby_cities")
            safe_alternatives.append({
                "type": "nearby_or_alternate_city",
                "requested_city": city,
                "nearby_cities": nearby,
            })
            for nc in nearby[:2]:
                suggested_filters.append({
                    "category": category,
                    "city": nc,
                    "max_price": max_price,
                    "action": "search_nearby_city",
                })
            if auto_allowed and not out.get("auto_retried"):
                retry_machines, _ = await _try_auto_retry(
                    database,
                    intent=intent,
                    filters=filt,
                    retry_filters={"city": nearby[0]},
                    permission_decision=permission_decision,
                )
                if retry_machines:
                    out["auto_retried"] = True
                    out["auto_retry_results"] = {
                        "machines": retry_machines[:8],
                        "count": len(retry_machines),
                        "retry_type": "nearby_or_alternate_city",
                        "matched_city": nearby[0],
                    }
                    out["next_best_action"] = "show_nearby_city_results"
                    out["suggestions"] = _recovery_suggestions(out, nearby_cities=nearby)
                    return out
        else:
            alt_cities = await available_cities_for_category(database, category=category, limit=5)
            alt_cities = [c for c in alt_cities if c.lower() != (city or "").lower()]
            if alt_cities:
                safe_alternatives.append({
                    "type": "nearby_or_alternate_city",
                    "requested_city": city,
                    "available_cities": alt_cities[:5],
                })
                out["recovery_type"] = "nearby_or_alternate_city"

    # --- Broaden filters (drop optional fields) -----------------------------
    if brand or filt.get("model") or max_price is not None:
        broaden: dict[str, Any] = {}
        if brand:
            broaden["brand"] = None
        if filt.get("model"):
            broaden["model"] = None
        if max_price is not None and out["recovery_type"] == "no_safe_recovery":
            broaden["max_price"] = None
        if broaden and auto_allowed and category and not out.get("auto_retried"):
            retry_machines, _ = await _try_auto_retry(
                database,
                intent=intent,
                filters=filt,
                retry_filters=broaden,
                permission_decision=permission_decision,
            )
            if retry_machines:
                out["auto_retried"] = True
                out["recovery_type"] = "broaden_filters"
                out["auto_retry_results"] = {
                    "machines": retry_machines[:8],
                    "count": len(retry_machines),
                    "retry_type": "broaden_filters",
                }
                out["next_best_action"] = "show_broadened_results"
                out["suggestions"] = _recovery_suggestions(out)
                return out

    # --- Missing context ----------------------------------------------------
    if not category and not purpose_key:
        out["recovery_type"] = "ask_missing_context"
        out["next_best_action"] = "ask_category_or_purpose"
        out["suggestions"] = ["Digging", "Compaction", "Jaipur", "Delhi"]
        return out
    if category and not city:
        out["recovery_type"] = "ask_missing_context"
        out["next_best_action"] = "ask_city"
        out["suggestions"] = ["Jaipur", "Delhi", "Mumbai", "Pune"]
        return out

    # --- Finalize without auto-retry ----------------------------------------
    if not out["recovery_type"] or out["recovery_type"] == "no_safe_recovery":
        if safe_alternatives:
            out["recovery_type"] = safe_alternatives[0].get("type", "no_safe_recovery")
        else:
            out["recovery_type"] = "no_safe_recovery"

    out["recovery_actions"] = recovery_actions
    out["safe_alternatives"] = safe_alternatives
    out["suggested_filters"] = suggested_filters
    out["next_best_action"] = out.get("next_best_action") or "offer_alternatives_or_support"
    out["suggestions"] = _recovery_suggestions(
        out,
        nearby_cities=_extract_nearby(safe_alternatives),
        similar_categories=similar_category_suggestions(category or ""),
        available_brands=_extract_brands(safe_alternatives),
    )
    out["message_facts"]["safe_alternatives"] = safe_alternatives
    return out


def _extract_nearby(alternatives: list[dict]) -> list[str]:
    for alt in alternatives:
        if alt.get("type") == "nearby_or_alternate_city":
            return list(alt.get("nearby_cities") or alt.get("available_cities") or [])
    return []


def _extract_brands(alternatives: list[dict]) -> list[str]:
    for alt in alternatives:
        if alt.get("type") == "brand_alternative":
            return list(alt.get("available_brands") or [])
    return []


def _recovery_suggestions(
    recovery: dict[str, Any],
    *,
    nearby_cities: list[str] | None = None,
    similar_categories: list[str] | None = None,
    available_brands: list[str] | None = None,
) -> list[str]:
    chips: list[str] = []
    rt = recovery.get("recovery_type")

    for c in (nearby_cities or _extract_nearby(recovery.get("safe_alternatives") or []))[:3]:
        chips.append(f"Check {str(c).title()}")
    for b in (available_brands or _extract_brands(recovery.get("safe_alternatives") or []))[:3]:
        chips.append(str(b))
    for cat in (similar_categories or [])[:2]:
        chips.append(f"{cat} options")

    if rt == "budget_relaxation":
        chips.append("Increase budget")
    if rt == "brand_alternative":
        chips.append("Show other brands")
    if rt == "listing_type_alternative":
        chips.append("Try rent options" if "buy" in str(recovery.get("message_facts", {})) else "Try buy options")
    if rt == "similar_category":
        chips.append("Try similar machines")

    chips.extend(["Contact support", "Search machine"])
    seen: set[str] = set()
    out: list[str] = []
    for c in chips:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out[:8]


def build_recovery_draft_message(
    recovery: dict[str, Any],
    *,
    filters: dict[str, Any],
    lang: str = "english",
    existing_alternatives: list | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build factual draft text for response gateway from recovery output.
    Does not invent data — only states what recovery found.
    """
    from app.chatbot.language import localized_no_exact_in_city, pick_lang

    facts = recovery.get("message_facts") or {}
    filt = filters or {}
    category = filt.get("category")
    city = filt.get("city")
    label = category_label(category) if category else "machines"
    city_title = str(city or "").title()

    auto = recovery.get("auto_retry_results") or {}
    if recovery.get("auto_retried") and auto.get("machines"):
        count = auto.get("count") or len(auto.get("machines") or [])
        rt = auto.get("retry_type") or recovery.get("recovery_type")
        if rt == "budget_relaxation":
            head = pick_lang(
                lang,
                english=f"No exact match under your budget. Found {count} {label} option(s) above your budget.",
                hindi=f"Budget ke andar exact match nahi mila. {count} {label} options mil gaye.",
                hinglish=f"Budget ke andar exact match nahi mila. {count} {label} options mil gaye.",
            )
        elif rt == "nearby_or_alternate_city":
            mc = auto.get("matched_city") or ""
            head = pick_lang(
                lang,
                english=f"No {label} in {city_title}. Found {count} in {str(mc).title()}.",
                hindi=f"{city_title} me {label} nahi mila. {str(mc).title()} me {count} options hain.",
                hinglish=f"{city_title} me {label} nahi mila. {str(mc).title()} me {count} options hain.",
            )
        elif rt == "similar_category":
            sc = auto.get("matched_category") or ""
            head = pick_lang(
                lang,
                english=f"No {label} in {city_title}. Showing similar {category_label(sc)} options.",
                hindi=f"{city_title} me {label} nahi. Similar {category_label(sc)} options dikha raha hoon.",
                hinglish=f"{city_title} me {label} nahi. Similar {category_label(sc)} options dikha raha hoon.",
            )
        elif rt == "brand_alternative":
            head = pick_lang(
                lang,
                english=f"Requested brand not available. Showing other {label} options in {city_title or 'your area'}.",
                hindi=f"Requested brand available nahi. {city_title or 'area'} me other {label} options.",
                hinglish=f"Requested brand available nahi. {city_title or 'area'} me other {label} options.",
            )
        else:
            head = pick_lang(
                lang,
                english=f"Exact match not found. Showing {count} related {label} option(s).",
                hindi=f"Exact match nahi mila. {count} related {label} options.",
                hinglish=f"Exact match nahi mila. {count} related {label} options.",
            )
        return head, {"recovery_type": recovery.get("recovery_type"), "auto_retry": True}

    nearby = _extract_nearby(recovery.get("safe_alternatives") or [])
    similar = similar_category_suggestions(category or "")
    if category and city:
        head = localized_no_exact_in_city(
            label=label,
            city=city or "",
            similar=similar,
            nearby_cities=nearby,
            lang=lang,
        )
    else:
        head = pick_lang(
            lang,
            english=f"No exact {label} match found with the current filters.",
            hindi=f"Current filters ke saath exact {label} match nahi mila.",
            hinglish=f"Current filters ke saath exact {label} match nahi mila.",
        )

    extras: list[str] = []
    for alt in recovery.get("safe_alternatives") or []:
        if alt.get("type") == "budget_relaxation" and alt.get("min_available_price"):
            extras.append(
                pick_lang(
                    lang,
                    english=f"Lowest available price is around ₹{int(alt['min_available_price'])}.",
                    hindi=f"Lowest available price lagbhag ₹{int(alt['min_available_price'])} hai.",
                    hinglish=f"Lowest available price lagbhag ₹{int(alt['min_available_price'])} hai.",
                )
            )
        if alt.get("type") == "brand_alternative" and alt.get("available_brands"):
            brands = ", ".join(alt["available_brands"][:5])
            extras.append(
                pick_lang(
                    lang,
                    english=f"Available brands include: {brands}.",
                    hindi=f"Available brands: {brands}.",
                    hinglish=f"Available brands: {brands}.",
                )
            )

    if extras:
        head = head + " " + " ".join(extras)

    if existing_alternatives:
        head += pick_lang(
            lang,
            english=" Some related options may be shown below.",
            hindi=" Kuch related options neeche ho sakte hain.",
            hinglish=" Kuch related options neeche ho sakte hain.",
        )

    return head, {
        "recovery_type": recovery.get("recovery_type"),
        "nearby_cities": nearby,
        "similar_categories": similar,
        "handover_suggested": recovery.get("recovery_type") == "no_safe_recovery",
    }


async def run_brand_inventory_recovery(
    database,
    *,
    category: str | None,
    brand: str | None,
    city: str | None,
    brands_found: list[str],
    lang: str = "english",
) -> dict[str, Any]:
    """Recovery when brand inventory query returns empty."""
    from app.chatbot.language import pick_lang
    from app.utils.machine_repository import available_cities_for_category

    out = empty_recovery_output()
    out["recovery_type"] = "brand_inventory_empty"

    if not brands_found and category:
        alt_cities = await available_cities_for_category(database, category=category, limit=4)
        if city:
            alt_cities = [c for c in alt_cities if c.lower() != city.lower()]
        similar = similar_category_suggestions(category)
        out["safe_alternatives"] = [{
            "type": "brand_inventory_empty",
            "category": category,
            "available_cities": alt_cities[:4],
            "similar_categories": similar[:3],
        }]
        out["message_facts"] = {
            "category": category,
            "city": city,
            "brands_found": [],
        }
        out["suggestions"] = (
            [f"Check {c.title()}" for c in alt_cities[:3]]
            + [f"{s} options" for s in similar[:2]]
            + ["Search machines directly", "Contact support"]
        )[:8]
        out["next_best_action"] = "search_machines_or_similar_category"
    elif not category:
        out["recovery_type"] = "ask_missing_context"
        out["next_best_action"] = "ask_brand_category"
        out["suggestions"] = ["Excavator", "Road Roller", "Crane", "Backhoe Loader"]
    else:
        out["message_facts"] = pick_lang(
            lang,
            english=f"No brand listings found for {category_label(category)}.",
            hindi=f"{category_label(category)} ke liye brand listings nahi mili.",
            hinglish=f"{category_label(category)} ke liye brand listings nahi mili.",
        )
        out["suggestions"] = ["Search machines", "Contact support"]

    return out


async def run_comparison_recovery(
    database,
    *,
    brands: list[str],
    category: str | None,
    city: str | None,
    results: list[dict],
    lang: str = "english",
) -> dict[str, Any]:
    """Recovery when comparison cannot find two listings."""
    from app.utils.machine_repository import available_brands_for_category_city

    out = empty_recovery_output()
    out["recovery_type"] = "comparison_partial"

    missing: list[str] = []
    found_brands = {str(r.get("brand") or "").lower() for r in results}
    for b in brands[:2]:
        if b.lower() not in found_brands:
            missing.append(b)

    available: list[str] = []
    if category:
        available = await available_brands_for_category_city(
            database,
            category=category,
            city=city,
        )

    out["message_facts"] = {
        "missing_brands": missing,
        "found_count": len(results),
        "category": category,
        "city": city,
    }
    out["safe_alternatives"] = [{
        "type": "comparison_partial",
        "missing_brands": missing,
        "available_brands": available[:6],
    }]
    out["suggestions"] = (
        [b for b in available[:3] if b not in brands]
        + ([f"Check {str(city).title()}"] if city else ["Jaipur", "Delhi"])
        + ["Search machine"]
    )[:8]
    out["next_best_action"] = "compare_available_brands_or_city"
    return out


def recovery_context_for_state(
    recovery: dict[str, Any],
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Compact blob for conversation state persistence."""
    auto = recovery.get("auto_retry_results") or {}
    return {
        "recovery_type": recovery.get("recovery_type"),
        "last_no_result_filters": dict(filters or {}),
        "suggested_filters": recovery.get("suggested_filters") or [],
        "safe_alternatives": recovery.get("safe_alternatives") or [],
        "auto_retried": bool(recovery.get("auto_retried")),
        "auto_retry_summary": {
            "count": auto.get("count", 0),
            "retry_type": auto.get("retry_type"),
            "matched_city": auto.get("matched_city"),
            "matched_category": auto.get("matched_category"),
        },
        "next_best_action": recovery.get("next_best_action"),
        "suggestions": recovery.get("suggestions") or [],
    }


def detect_recovery_followup(message: str, recovery_ctx: dict[str, Any]) -> dict[str, Any] | None:
    """Map user follow-up to a suggested filter from saved recovery context."""
    if not recovery_ctx:
        return None
    msg = (message or "").strip().lower()
    suggested = recovery_ctx.get("suggested_filters") or []

    if any(p in msg for p in ("other brand", "show other brand", "different brand")):
        for sf in suggested:
            if sf.get("action") == "drop_brand_filter":
                return sf
        return {"brand": None, "action": "drop_brand_filter"}

    if any(p in msg for p in ("increase budget", "higher budget", "remove budget")):
        for sf in suggested:
            if sf.get("action") == "remove_budget_cap":
                return sf
        return {"max_price": None, "action": "remove_budget_cap"}

    if any(p in msg for p in ("nearby", "other city", "try nearby", "check ")):
        for sf in suggested:
            if sf.get("action") == "search_nearby_city":
                return sf
        for alt in recovery_ctx.get("safe_alternatives") or []:
            cities = alt.get("nearby_cities") or alt.get("available_cities") or []
            for c in cities:
                if c.lower() in msg:
                    return {"city": c, "category": recovery_ctx.get("last_no_result_filters", {}).get("category")}

    if any(p in msg for p in ("similar", "try similar")):
        for sf in suggested:
            if sf.get("action") == "try_similar_category":
                return sf

    if "same city" in msg or "same city only" in msg:
        base = recovery_ctx.get("last_no_result_filters") or {}
        return {**base, "nearby_allowed": False}

    return None
