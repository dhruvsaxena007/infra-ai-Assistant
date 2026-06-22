"""
Chatbot service with conversational state management.

The core challenge is not search — search already works. The challenges are:
  1. Multi-turn context: merging previous filters with partial follow-ups
     ("show cheaper options", "what about mumbai") WITHOUT old context being
     too sticky — a new explicit category must override the old one.
  2. Category accuracy: a "JCB / 3DX / backhoe" request must return Backhoe
     Loaders, never an excavator. This is enforced by strict category search
     (search_by_filters with anchored category match) instead of relying on
     semantic similarity, which bleeds across categories.
  3. Honest fallback: if the exact requested category/city/budget has no match,
     we return ALTERNATIVES that are clearly labelled as alternatives, plus a
     machine-readable search_status block, instead of silently showing the
     wrong machine as a direct result.

Architecture:
    _last_filters_by_session — per-session resolved filters from the last turn.
    chatbot_response()       — orchestrates parsing, memory merge, strict search,
                               fallback tiers, special intents, and the reply.
"""

from app.ai.intelligent_search import (
    intelligent_machine_search,
)
from app.utils.machine_repository import (
    available_categories_in_city,
    nearby_cities_with_listings,
    search_by_filters,
    search_by_region,
)
from app.core.config import settings
from app.ai.category_mapping import category_label
from app.chatbot.memory import save_conversation
from app.database.persistent_store import load_session_doc, persist_session_fields
from app.utils.machine_normalizer import format_price_label
from app.utils.sanitize import without_embeddings, deduplicate_machines
from app.ai.advisor_service import generate_machine_advice
from app.analytics.search_logger import save_search_log
from app.utils.response import success_response
from app.chatbot.language import (
    detect_query_language,
    localized_alternatives_footer,
    localized_found_intro,
    localized_no_results_generic,
)
from app.chatbot.assistant_intelligence import (
    booking_guidance_message,
    build_handover,
    build_response_context,
    build_purpose_pending,
    chips_from_categories,
    city_category_clarification_message,
    clarification_question,
    enrich_no_result_message,
    greeting_message,
    irrelevant_response_message,
    project_categories,
    purpose_clarification_chips,
    purpose_clarification_message,
    recommendation_clarification_message,
    similar_category_keys,
    similar_category_suggestions,
    too_many_results_message,
    _CATEGORY_CHIPS,
    _GREETING_CHIPS,
)

_MAX_CITY_CATEGORIES_SHOW = 10
from app.chatbot.intent_resolver import resolve_user_intent
from app.ai.category_mapping import region_cities

# ---------------------------------------------------------------------------
# Per-session conversation-state store
# ---------------------------------------------------------------------------

_last_filters_by_session: dict[str, dict] = {}
_pending_clarification_by_session: dict[str, dict] = {}
_recommendation_context_by_session: dict[str, dict] = {}
_session_context_by_session: dict[str, dict] = {}

_DEFAULT_FILTERS = {
    "category": None,
    "city": None,
    "region": None,
    "max_price": None,
    "brand": None,
    "model": None,
    "condition": None,
    "pincode": None,
    "listing_type": None,
    "rent_type": None,
}

# Number of results returned for normal vs "list all" requests.
_DEFAULT_LIMIT = 5
_LIST_ALL_LIMIT = 20


def invalidate_session_cache(session_id: str) -> None:
    """Drop in-memory session state (e.g. after clear / new chat)."""
    session_id = (session_id or "").strip()
    for store in (
        _last_filters_by_session,
        _pending_clarification_by_session,
        _recommendation_context_by_session,
        _session_context_by_session,
    ):
        store.pop(session_id, None)


def _get_last_filters(session_id: str) -> dict:
    """Return the last resolved filters for this session."""
    if session_id not in _last_filters_by_session:
        doc = load_session_doc(session_id)
        if doc and doc.get("filters"):
            _last_filters_by_session[session_id] = {**_DEFAULT_FILTERS, **doc["filters"]}
        else:
            _last_filters_by_session[session_id] = dict(_DEFAULT_FILTERS)
    return _last_filters_by_session[session_id]


def _save_last_filters(session_id: str, filters: dict) -> None:
    _last_filters_by_session[session_id] = filters
    persist_session_fields(session_id, filters=filters)


def _get_pending_clarification(session_id: str) -> dict | None:
    if session_id in _pending_clarification_by_session:
        return _pending_clarification_by_session[session_id]
    doc = load_session_doc(session_id)
    pending = (doc or {}).get("pending_clarification")
    if pending:
        _pending_clarification_by_session[session_id] = pending
    return pending


def _save_pending_clarification(session_id: str, pending: dict | None) -> None:
    if pending:
        _pending_clarification_by_session[session_id] = pending
    elif session_id in _pending_clarification_by_session:
        del _pending_clarification_by_session[session_id]
    persist_session_fields(session_id, pending_clarification=pending or {})


def _get_recommendation_context(session_id: str) -> dict | None:
    if session_id in _recommendation_context_by_session:
        return _recommendation_context_by_session[session_id]
    doc = load_session_doc(session_id)
    ctx = (doc or {}).get("recommendation_context")
    if ctx:
        _recommendation_context_by_session[session_id] = ctx
    return ctx


def _save_recommendation_context(session_id: str, ctx: dict | None) -> None:
    if ctx:
        _recommendation_context_by_session[session_id] = ctx
    elif session_id in _recommendation_context_by_session:
        del _recommendation_context_by_session[session_id]
    persist_session_fields(session_id, recommendation_context=ctx or {})


def _get_session_context(session_id: str) -> dict:
    if session_id in _session_context_by_session:
        return _session_context_by_session[session_id]
    doc = load_session_doc(session_id)
    ctx = (doc or {}).get("session_context") or {}
    _session_context_by_session[session_id] = ctx
    return ctx


def _save_session_context(session_id: str, ctx: dict) -> None:
    _session_context_by_session[session_id] = ctx
    persist_session_fields(session_id, session_context=ctx)


def _persist_last_results(
    session_id: str,
    machines: list,
    filters: dict | None = None,
) -> None:
    """Remember last shown machines so follow-up questions use session context."""
    if not machines:
        return
    from app.ai.conversation_context import build_result_context

    ctx = _get_session_context(session_id)
    ctx["last_results"] = build_result_context(machines, filters or {})
    _save_session_context(session_id, ctx)


def _assistant_payload(
    *,
    message: str,
    machines: list | None = None,
    filters: dict | None = None,
    assistant_mode: str,
    suggestions: list | None = None,
    handover: dict | None = None,
    pending_clarification: dict | None = None,
    spell_context: dict | None = None,
    reply_language: str | None = None,
    **extra,
) -> dict:
    context_extra = dict(extra.pop("context_extra", None) or {})
    if spell_context:
        context_extra = {**spell_context, **context_extra}
    if reply_language:
        context_extra["reply_language"] = reply_language
    data = {
        "advisor_message": extra.pop("advisor_message", None),
        "machines": machines or [],
        "exact_results": extra.pop("exact_results", []),
        "alternatives": extra.pop("alternatives", []),
        "filters": filters or {},
        "search_status": extra.pop("search_status", {}),
        "context": build_response_context(
            assistant_mode=assistant_mode,
            pending_clarification=pending_clarification,
            extra=context_extra or None,
        ),
        "suggestions": suggestions or [],
        "handover": handover,
        "pending_clarification": pending_clarification,
    }
    data.update({k: v for k, v in extra.items() if k != "context_extra"})
    return data


def hydrate_filters_cache(session_id: str, filters: dict) -> None:
    if session_id and filters:
        _last_filters_by_session[session_id] = {**_DEFAULT_FILTERS, **filters}


# ---------------------------------------------------------------------------
# Reply builders (deterministic, LLM-free)
# ---------------------------------------------------------------------------

def _format_machine_lines(machines: list) -> str:
    lines = []
    for index, machine in enumerate(machines, start=1):
        name = machine.get("name", "Unknown Machine")
        cat = machine.get("category_display") or machine.get("category") or "Unknown"
        city = str(machine.get("city", "Unknown")).title()
        price = format_price_label(machine)
        status = machine.get("availability_status") or "unknown"
        brand = machine.get("brand")
        model = machine.get("model")
        specs = machine.get("specifications") or {}
        year = specs.get("manufacturing_year")
        condition = specs.get("condition")

        meta_parts = [f"({cat})", f"— {city}", price, status]
        if brand or model:
            meta_parts.insert(1, f"{brand or ''} {model or ''}".strip())
        detail = ", ".join(str(p) for p in meta_parts if p)
        if year or condition:
            detail += f", {condition or ''} {year or ''}".strip()

        rating = machine.get("rating")
        if rating is not None:
            detail += f", rating {rating}/5"
        else:
            detail += ", rating not available"

        lines.append(f"{index}. {name} {detail}")
    return "\n".join(lines)


def _conditions_text(city, max_price) -> str:
    parts = []
    if city:
        parts.append(f"in {str(city).title()}")
    if max_price:
        parts.append(f"under ₹{max_price}")
    return (" " + " ".join(parts)) if parts else ""


def _build_found_reply(
    category, city, max_price, machines, *, lang: str = "english",
) -> str:
    label = category_label(category) if category else "machines"
    intro = localized_found_intro(
        lang=lang,
        count=len(machines),
        label=label,
        city=city,
        max_price=max_price,
    )
    return intro + _format_machine_lines(machines)


def _build_not_found_reply(category, city, max_price, alternatives, reason) -> str:
    label = category_label(category)
    head = f"No {label} found{_conditions_text(city, max_price)}."

    if alternatives:
        head += " " + (reason or "Showing the closest alternatives instead:") + "\n\n"
        head += _format_machine_lines(alternatives)
        head += "\n\nThese are alternatives, not exact matches for your request."
    else:
        head += (
            " I could not find close alternatives either. "
            "Try another city, category, or a higher budget."
        )
    return head


async def _search_purpose_alternatives_in_city(
    database,
    *,
    categories: list[str],
    city: str | None,
    max_price,
    limit: int,
    filters: dict,
) -> tuple[list, str | None]:
    """Find machines in the SAME city across purpose-recommended categories."""
    if not categories:
        return [], None

    seen: set[str] = set()
    combined: list = []
    matched_cat = None
    per_cat = max(2, limit // len(categories) + 1)

    for cat in categories:
        batch = await search_by_filters(
            database,
            category=cat,
            city=city,
            max_price=max_price,
            limit=per_cat,
            exact_category=True,
            filters={**filters, "category": cat, "city": city},
        )
        for machine in batch:
            mid = str(machine.get("id") or machine.get("_id") or "")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            combined.append(machine)
            matched_cat = matched_cat or cat
        if len(combined) >= limit:
            break

    reason = None
    if combined and matched_cat:
        reason = (
            f"Showing {category_label(matched_cat)} and related options "
            f"in {str(city or '').title()} for your purpose."
        )
    return combined[:limit], reason


def _build_free_reply(category, city, lowest) -> str:
    label = category_label(category) if category else "machines"
    where = f" in {str(city).title()}" if city else ""
    if lowest:
        return (
            "Free machines are not available in the marketplace. "
            f"Here are the lowest-priced {label}{where} instead:\n\n"
            + _format_machine_lines(lowest)
        )
    if category and city:
        return (
            f"Free {label} are not available in {str(city).title()}. "
            "Tell me another category or city and I will show the lowest-priced options."
        )
    if category:
        return (
            f"Free {label} are not available in the marketplace. "
            "Tell me which city you need and I will show the lowest-priced options."
        )
    return (
        "Free machines are not available in the marketplace. "
        "Tell me a category and city and I will show the lowest-priced options."
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def chatbot_response(session_id: str, user_message: str, database):
    """Entry point — delegates to central assistant router."""
    from app.ai.assistant_router import handle_assistant_message

    return await handle_assistant_message(session_id, user_message, database)


async def execute_machine_search_turn(
    session_id: str,
    user_message: str,
    database,
    classification: dict | None = None,
    forced_filters: dict | None = None,
):
    """Machine search, clarification, and recommendation (search path only)."""

    session_id = (session_id or "").strip()
    if not session_id:
        raise ValueError("session_id is required")

    user_message = (user_message or "").strip()
    reply_lang = detect_query_language(user_message)

    if forced_filters:
        merged_force = {**_DEFAULT_FILTERS, **_get_last_filters(session_id), **forced_filters}
        _save_last_filters(session_id, merged_force)
        print(f"[execute_search] forced_filters applied: {merged_force}")

    last_filters = _get_last_filters(session_id)
    pending = _get_pending_clarification(session_id)
    rec_ctx = _get_recommendation_context(session_id)
    session_ctx = _get_session_context(session_id)
    greeted = bool(session_ctx.get("greeted"))

    intent = await resolve_user_intent(
        session_id,
        user_message,
        last_filters=last_filters,
        pending=pending,
        recommendation_context=rec_ctx,
        greeted=greeted,
    )

    if intent.get("mark_greeted"):
        _save_session_context(session_id, {**session_ctx, "greeted": True})
    if intent.get("clear_pending_clarification"):
        _save_pending_clarification(session_id, None)
    elif intent.get("save_pending_clarification"):
        _save_pending_clarification(session_id, intent["save_pending_clarification"])
    if intent.get("clear_recommendation_context"):
        _save_recommendation_context(session_id, None)
    elif intent.get("save_recommendation_context"):
        _save_recommendation_context(session_id, intent["save_recommendation_context"])

    used_image_context = intent.get("used_image_context", False)
    is_fup = intent.get("is_follow_up", False)
    list_all = intent.get("list_all", False)
    free_request = intent.get("free_request", False)
    override = intent.get("override", False)
    spell_ctx = intent.get("spell_context")

    if classification:
        print(
            "[execute_search]",
            f"classified_intent={classification.get('intent')}",
            f"should_search={classification.get('should_search_machines')}",
        )

    # --- Spelling confirmation (ambiguous typo — ask before searching) -------
    if intent.get("intent") == "spell_confirmation":
        from app.ai.spell_correction import spell_confirmation_message

        spell_ctx = intent.get("spell_context") or {}
        reply = spell_confirmation_message(
            spell_ctx.get("corrections") or [],
            spell_ctx.get("corrected_query") or user_message,
        )
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="spell_confirmation",
                pending_clarification=intent.get("pending_clarification"),
                spell_context=spell_ctx,
                reply_language=reply_lang,
            ),
        )

    # --- Project recommendation clarification --------------------------------
    if intent.get("assistant_mode") == "recommendation_clarification":
        reply = recommendation_clarification_message(lang=reply_lang)
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                assistant_mode="recommendation_clarification",
                pending_clarification=intent.get("pending_clarification"),
                spell_context=spell_ctx,
                reply_language=reply_lang,
                suggestions=["Highway", "Earthwork", "Compaction", "Concrete road"],
            ),
        )

    merged = dict(intent.get("filters") or {})
    purpose_alt_cats = merged.pop("alternative_categories", None)
    purpose_requested = merged.pop("requested_category", None)
    purpose_key = merged.pop("purpose_key", None)

    # --- Purpose answer → search alternatives in same city -------------------
    if purpose_alt_cats and merged.get("city"):
        alt_raw, alt_reason = await _search_purpose_alternatives_in_city(
            database,
            categories=purpose_alt_cats,
            city=merged.get("city"),
            max_price=merged.get("max_price"),
            limit=_DEFAULT_LIMIT,
            filters=merged,
        )
        alternatives = deduplicate_machines(without_embeddings(alt_raw))
        req_cat = purpose_requested or merged.get("category")
        matched = alternatives[0].get("category") if alternatives else None
        if alternatives:
            reply, _ = enrich_no_result_message(
                matched,
                merged.get("city"),
                alternatives,
                fallback_reason=alt_reason,
                purpose_based=True,
                requested_category=req_cat,
            )
            reply += "\n\n" + _format_machine_lines(alternatives)
            reply += "\n\nThese are purpose-based alternatives, not exact matches."
        else:
            from app.chatbot.language import localized_purpose_no_match

            nearby = await nearby_cities_with_listings(
                database, merged.get("city") or "",
            )
            reply = localized_purpose_no_match(
                str(merged.get("city") or ""),
                nearby,
                reply_lang,
            )
        save_conversation(session_id, user_message, reply)
        _save_last_filters(session_id, {**_DEFAULT_FILTERS, **{
            k: merged.get(k) for k in (
                "category", "city", "max_price", "listing_type", "brand", "model",
            ) if merged.get(k) is not None
        }})
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=alternatives,
                exact_results=[],
                alternatives=alternatives,
                filters={
                    "category": matched,
                    "city": merged.get("city"),
                    "max_price": merged.get("max_price"),
                    "requested_category": req_cat,
                },
                search_status={
                    "exact_match_found": False,
                    "requested_category": req_cat,
                    "matched_category": matched,
                    "fallback_used": True,
                    "fallback_reason": alt_reason or "purpose_based_alternatives",
                    "purpose_key": purpose_key,
                },
                assistant_mode="purpose_alternatives" if alternatives else "no_result",
                spell_context=spell_ctx,
                reply_language=reply_lang,
            ),
        )

    # --- Clarification before search -----------------------------------------
    if intent.get("intent") == "clarification":
        clarify = intent.get("pending_clarification") or intent.get("save_pending_clarification")
        suggestions: list[str] = []

        if intent.get("negative_pivot"):
            reply = clarification_question(
                clarify.get("category") if clarify else None,
                "filters",
                city=clarify.get("city") if clarify else None,
                lang=reply_lang,
            )
            if clarify:
                _save_pending_clarification(session_id, clarify)
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    filters={
                        "category": clarify.get("category") if clarify else None,
                        "city": clarify.get("city") if clarify else None,
                    },
                    assistant_mode="clarification",
                    pending_clarification=clarify,
                    spell_context=spell_ctx,
                    reply_language=reply_lang,
                    suggestions=list(_CATEGORY_CHIPS)[:6],
                ),
            )

        if clarify and clarify.get("missing_field") == "category" and clarify.get("city"):
            available = await available_categories_in_city(database, clarify["city"])
            nearby: list[str] = []
            if not available:
                nearby = await nearby_cities_with_listings(
                    database, clarify["city"],
                )
            clarify["available_categories"] = available
            clarify["nearby_cities"] = nearby
            _save_pending_clarification(session_id, clarify)
            reply = city_category_clarification_message(
                clarify["city"], available, lang=reply_lang,
                max_show=_MAX_CITY_CATEGORIES_SHOW,
                nearby_cities=nearby,
            )
            if available:
                suggestions = chips_from_categories(
                    available[:_MAX_CITY_CATEGORIES_SHOW],
                )
            else:
                suggestions = [
                    f"Check {c.title()}" for c in nearby[:3]
                ] or list(_CATEGORY_CHIPS)[:4]
        else:
            reply = clarification_question(
                clarify.get("category") if clarify else None,
                clarify.get("missing_field") if clarify else "filters",
                city=clarify.get("city") if clarify else None,
                listing_type=clarify.get("listing_type") if clarify else None,
                lang=reply_lang,
            )

        if intent.get("save_filters"):
            _save_last_filters(session_id, intent["save_filters"])
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=[],
                filters={
                    "category": clarify.get("category") if clarify else None,
                    "city": clarify.get("city") if clarify else None,
                    "listing_type": clarify.get("listing_type") if clarify else None,
                },
                assistant_mode="clarification",
                pending_clarification=clarify,
                spell_context=spell_ctx,
                reply_language=reply_lang,
                suggestions=suggestions,
            ),
        )

    requested_category = merged.get("category")
    city = merged.get("city")
    region = merged.get("region")
    max_price = merged.get("max_price")
    listing_type = merged.get("listing_type")

    limit = _LIST_ALL_LIMIT if list_all else _DEFAULT_LIMIT

    if intent.get("save_filters"):
        _save_last_filters(session_id, {**_DEFAULT_FILTERS, **intent["save_filters"]})

    # --- Special intent: free / unrealistic budget -------------------------
    if free_request:
        lowest_raw = await search_by_filters(
            database,
            category=requested_category,
            city=city,
            max_price=None,
            limit=limit,
            exact_category=True,
            sort_by="price",
        )
        lowest = deduplicate_machines(without_embeddings(lowest_raw))
        reply = _build_free_reply(requested_category, city, lowest)
        save_conversation(session_id, user_message, reply)

        advice = generate_machine_advice(
            user_message,
            lowest,
            exact_match_found=False,
            requested_category=requested_category,
        )

        return success_response(
            message=reply,
            data={
                "advisor_message": (
                    advice.get("advice") if advice.get("success") else None
                ),
                "machines": lowest,
                "exact_results": [],
                "alternatives": lowest,
                "filters": {
                    "category": requested_category,
                    "city": city,
                    "max_price": None,
                },
                "search_status": {
                    "exact_match_found": False,
                    "requested_category": requested_category,
                    "matched_category": None,
                    "fallback_used": True,
                    "fallback_reason": "free_or_unrealistic_budget",
                },
                "context": {
                    "used_previous_context": is_fup,
                    "intent": "free_request",
                    "list_all": list_all,
                    "result_limit": limit,
                },
            },
        )

    # --- Search ------------------------------------------------------------
    exact_raw: list = []
    alternatives_raw: list = []
    exact_match_found = False
    matched_category = None
    fallback_used = False
    fallback_reason = None

    if requested_category:
        # Strict category mode: never let another category appear as a direct
        # match. Tiered fallback only relaxes constraints for ALTERNATIVES.
        if region:
            cities_in_region = region_cities(region)
            exact_raw = await search_by_region(
                database,
                region_cities=cities_in_region,
                category=requested_category,
                max_price=max_price,
                limit=limit,
                filters=merged,
            )
        else:
            exact_raw = await search_by_filters(
                database,
                category=requested_category,
                city=city,
                max_price=max_price,
                limit=limit,
                exact_category=True,
                filters=merged,
            )

        if exact_raw:
            exact_match_found = True
            matched_category = requested_category
        else:
            label = category_label(requested_category)

            # Tier 1: same category + city, drop the budget.
            if max_price is not None and city:
                alt = await search_by_filters(
                    database, category=requested_category, city=city,
                    max_price=None, limit=limit, exact_category=True,
                )
                if alt:
                    alternatives_raw = alt
                    matched_category = requested_category
                    fallback_reason = (
                        f"No {label} found in {str(city).title()} under ₹{max_price}. "
                        "Showing nearest options above your budget."
                    )

            # When a city was specified, stay in the SAME city — never cross-city dump.
            elif city or region:
                relaxed_filters = {
                    **merged,
                    "brand": None,
                    "model": None,
                    "condition": None,
                }
                brand_hint = merged.get("brand") or merged.get("model")
                cond_hint = merged.get("condition")

                if brand_hint or cond_hint:
                    relaxed = await search_by_filters(
                        database,
                        category=requested_category,
                        city=city,
                        max_price=max_price,
                        limit=limit,
                        exact_category=True,
                        filters=relaxed_filters,
                    )
                    if relaxed:
                        exact_raw = relaxed
                        exact_match_found = True
                        matched_category = requested_category
                        if brand_hint:
                            fallback_reason = (
                                f"No {brand_hint} {label} in {str(city).title()}. "
                                f"Showing other {label} options in {str(city).title()}."
                            )
                        else:
                            fallback_reason = (
                                f"No {cond_hint} {label} in {str(city).title()}. "
                                f"Showing available {label} in {str(city).title()}."
                            )
                        fallback_used = True

                if not exact_match_found and not alternatives_raw:
                    sim_cats = similar_category_keys(requested_category)
                    if sim_cats and city:
                        alt_raw, alt_reason = await _search_purpose_alternatives_in_city(
                            database,
                            categories=sim_cats,
                            city=city,
                            max_price=max_price,
                            limit=limit,
                            filters=relaxed_filters,
                        )
                        if alt_raw:
                            alternatives_raw = alt_raw
                            matched_category = (
                                alternatives_raw[0].get("category")
                                if alternatives_raw else None
                            )
                            fallback_used = True
                            fallback_reason = (
                                f"No {label} in {str(city).title()}. "
                                f"Showing similar machines available in "
                                f"{str(city).title()}."
                            )

                if not exact_match_found and not alternatives_raw:
                    from app.chatbot.language import localized_no_exact_in_city

                    nearby = await nearby_cities_with_listings(
                        database, city or "",
                    )
                    reply = localized_no_exact_in_city(
                        label=label,
                        city=city or "",
                        similar=similar_category_suggestions(requested_category),
                        nearby_cities=nearby,
                        lang=reply_lang,
                    )
                    purpose_pending = build_purpose_pending(
                        requested_category,
                        city,
                        max_price=max_price,
                        listing_type=listing_type,
                        brand=merged.get("brand"),
                        model=merged.get("model"),
                    )
                    _save_pending_clarification(session_id, purpose_pending)
                    save_conversation(session_id, user_message, reply)
                    return success_response(
                        message=reply,
                        data=_assistant_payload(
                            message=reply,
                            machines=[],
                            filters={
                                "category": requested_category,
                                "city": city,
                                "max_price": max_price,
                            },
                            assistant_mode="no_result",
                            pending_clarification=purpose_pending,
                            spell_context=spell_ctx,
                            reply_language=reply_lang,
                            suggestions=(
                                [f"Check {c.title()}" for c in nearby[:3]]
                                or purpose_clarification_chips()[:4]
                            ),
                            search_status={
                                "exact_match_found": False,
                                "requested_category": requested_category,
                                "fallback_used": False,
                                "fallback_reason": "no_match_in_city",
                            },
                        ),
                    )

            # No city filter — limited same-category fallback (no cross-city dump).
            elif not alternatives_raw and requested_category == "hydra crane":
                alt = await search_by_filters(
                    database, category="crane", city=None,
                    max_price=max_price, limit=limit, exact_category=True,
                    filters={**merged, "category": "crane"},
                )
                if alt:
                    alternatives_raw = alt
                    matched_category = "crane"
                    fallback_reason = (
                        "No exact Hydra Crane found. Showing similar Crane options."
                    )

            if alternatives_raw:
                fallback_used = True
    else:
        # No explicit category -> brand/model/city/price aware search.
        query_parts = []
        if merged.get("brand"):
            query_parts.append(merged["brand"])
        if merged.get("model"):
            query_parts.append(merged["model"])
        if city:
            query_parts.append(f"in {city}")
        if max_price is not None:
            query_parts.append(f"under {max_price}")
        search_query = " ".join(query_parts) or user_message

        if merged.get("brand") or merged.get("model") or city or max_price is not None:
            exact_raw = await search_by_filters(
                database,
                city=city,
                max_price=max_price,
                limit=limit,
                filters=merged,
            )
            if not exact_raw:
                sem = await intelligent_machine_search(search_query, database, limit=limit)
                exact_raw = sem
        else:
            # Never dump random machines for vague queries without filters.
            reply = clarification_question(None, "filters", lang=reply_lang)
            save_conversation(session_id, user_message, reply)
            return success_response(
                message=reply,
                data=_assistant_payload(
                    message=reply,
                    machines=[],
                    assistant_mode="clarification",
                    spell_context=spell_ctx,
                    reply_language=reply_lang,
                    suggestions=list(_CATEGORY_CHIPS)[:6],
                ),
            )

        exact_match_found = bool(exact_raw)
        matched_category = None

    # Deduplicate before returning so the same listing is never repeated, even
    # if duplicate documents still exist in the database.
    exact_results = deduplicate_machines(without_embeddings(exact_raw))
    alternatives = deduplicate_machines(without_embeddings(alternatives_raw))
    display = exact_results if exact_match_found else alternatives

    # Too many broad results — ask refinement instead of dumping all.
    threshold = settings.TOO_MANY_RESULTS_THRESHOLD
    if (
        exact_match_found
        and len(display) > threshold
        and not requested_category
        and not list_all
    ):
        reply = too_many_results_message(len(display), lang=reply_lang)
        save_conversation(session_id, user_message, reply)
        return success_response(
            message=reply,
            data=_assistant_payload(
                message=reply,
                machines=display[:_DEFAULT_LIMIT],
                filters={"category": requested_category, "city": city, "max_price": max_price},
                assistant_mode="too_many_results",
                spell_context=spell_ctx,
                reply_language=reply_lang,
            ),
        )

    # --- Reply -------------------------------------------------------------
    if exact_match_found:
        reply = _build_found_reply(
            requested_category, city, max_price, display, lang=reply_lang,
        )
        if fallback_reason:
            reply = f"{fallback_reason}\n\n{reply}"
    elif requested_category:
        reply, no_result_meta = enrich_no_result_message(
            requested_category,
            city,
            alternatives,
            fallback_reason=fallback_reason,
        )
        if alternatives:
            reply += "\n\n" + _format_machine_lines(alternatives)
            reply += "\n\n" + localized_alternatives_footer(reply_lang)
        elif no_result_meta.get("handover_suggested"):
            reply += " I could not find close alternatives either."
    elif display:
        reply = _build_found_reply(
            None, city, max_price, display, lang=reply_lang,
        )
    else:
        reply = localized_no_results_generic(reply_lang)

    # --- Advisor (category-aware) -----------------------------------------
    advice = generate_machine_advice(
        user_message,
        display,
        exact_match_found=exact_match_found,
        requested_category=requested_category,
    )
    advisor_message = advice.get("advice") if advice.get("success") else None

    # --- Persist + analytics ----------------------------------------------
    save_conversation(session_id, user_message, reply)

    if requested_category or city or region:
        _save_last_filters(session_id, {
            **_DEFAULT_FILTERS,
            "category": requested_category,
            "city": city,
            "region": region,
            "max_price": max_price,
            "brand": merged.get("brand"),
            "model": merged.get("model"),
            "listing_type": listing_type,
            "rent_type": merged.get("rent_type"),
        })

    try:
        await save_search_log(
            database=database,
            session_id=session_id,
            user_message=user_message,
            search_query=str(merged),
            filters=merged,
            result_count=len(display),
            fallback_used=fallback_used,
            fallback_query=fallback_reason,
        )
    except Exception as log_error:
        print(f"[search_logger] Failed to save search log: {log_error}")

    if (
        listing_type == "sell"
        and requested_category
        and not exact_match_found
        and not alternatives
    ):
        reply = (
            f"No {category_label(requested_category)} available for purchase"
            + (f" in {str(city).title()}" if city else "")
            + ". Do you want rental options?"
        )

    assistant_mode = (
        intent.get("assistant_mode")
        if intent.get("intent") == "project_recommendation"
        else ("search" if exact_match_found else "no_result")
    )
    handover = None
    if not exact_match_found and requested_category and not alternatives:
        handover = build_handover(
            f"No exact {category_label(requested_category)} found"
            + (f" in {str(city).title()}" if city else "")
            + (f" in {region.replace('_', ' ').title()}" if region else "")
        )

    payload_extra = {}
    if intent.get("intent") == "project_recommendation":
        payload_extra["recommended_categories"] = intent.get("recommended_categories", [])

    _persist_last_results(
        session_id,
        display,
        {
            "category": requested_category,
            "city": city,
            "region": region,
            "max_price": max_price,
            "listing_type": listing_type,
        },
    )

    return success_response(
        message=reply,
        data=_assistant_payload(
            message=reply,
            advisor_message=advisor_message,
            machines=display,
            exact_results=exact_results,
            alternatives=alternatives,
            filters={
                "category": requested_category,
                "city": city,
                "region": region,
                "max_price": max_price,
                "listing_type": listing_type,
                "brand": merged.get("brand"),
                "model": merged.get("model"),
            },
            search_status={
                "exact_match_found": exact_match_found,
                "requested_category": requested_category,
                "matched_category": matched_category,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "similar_categories": similar_category_suggestions(requested_category or ""),
            },
            assistant_mode=assistant_mode,
            handover=handover,
            spell_context=spell_ctx,
            reply_language=reply_lang,
            context_extra={
                "used_previous_context": is_fup,
                "used_image_context": used_image_context,
                "intent": intent.get("intent") or ("list_all" if list_all else "search"),
                "list_all": list_all,
                "result_limit": limit,
                "override": override,
                "confidence": intent.get("confidence"),
            },
            **payload_extra,
        ),
    )
