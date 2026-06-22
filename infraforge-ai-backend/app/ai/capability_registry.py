"""
Phase 12 — authoritative InfraForge capability and catalog validation.

Categories, brands, purposes come from catalog/taxonomy — not router hardcoding.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.domain_models import CapabilityValidation, DomainEntities

# Marketplace action families (verbs — not asset-specific)
_MARKETPLACE_ACTION_RE = re.compile(
    r"\b(?:rent|rental|hire|kiraye|kiraya|buy|purchase|sell|auction|tender|"
    r"book(?:ing)?|listing|listings|available|availability|price|cost|quote|"
    r"search|find|show|dikhao|dikhado|chahiye|chaiye|need|want|milta|milega)\b",
    re.I,
)

# Platform support operations
_SUPPORT_ACTION_RE = re.compile(
    r"\b(?:refund|payment|paid|transaction|booking\s*id|order\s*id|txn|"
    r"cancel|complaint|issue|problem|not\s+working|broken\s+machine)\b",
    re.I,
)

# Document / policy
_DOCUMENT_RE = re.compile(
    r"\b(?:policy|policies|terms|document|pdf|uploaded|agreement|warranty\s+terms)\b",
    re.I,
)

# Construction / equipment domain vocabulary (from taxonomy keys — not example phrases)
def _domain_vocabulary_tokens() -> set[str]:
    from app.ai.category_mapping import CATEGORY_SYNONYMS
    from app.ai.purpose_taxonomy import PURPOSE_TO_CATEGORIES
    from app.chatbot.assistant_intelligence import PURPOSE_ALIASES

    tokens: set[str] = set()
    for cat in CATEGORY_SYNONYMS:
        tokens.add(cat.lower())
    for synonyms in CATEGORY_SYNONYMS.values():
        for s in synonyms:
            if len(s) > 2:
                tokens.add(s.lower())
    for purpose in PURPOSE_TO_CATEGORIES:
        tokens.add(purpose.lower())
    for alias, pk in PURPOSE_ALIASES.items():
        if len(alias) > 3:
            tokens.add(alias.lower())
        tokens.add(pk.lower())
    return tokens


def supported_categories() -> list[str]:
    from app.ai.category_mapping import CANONICAL_CATEGORIES
    return list(CANONICAL_CATEGORIES)


def supported_purposes() -> list[str]:
    from app.ai.purpose_taxonomy import PURPOSE_TO_CATEGORIES
    return list(PURPOSE_TO_CATEGORIES.keys())


def supported_marketplace_actions() -> list[str]:
    return [
        "search_listings", "rent", "buy", "sell", "auction", "tender",
        "compare_listings", "brand_inventory", "price_inquiry",
        "availability_check", "owner_contact", "booking_inquiry",
    ]


def supported_knowledge_areas() -> list[str]:
    return [
        "equipment_selection", "applications", "specifications", "maintenance",
        "troubleshooting", "safety", "productivity", "operating_suitability",
        "construction_methods", "comparison_reasoning",
    ]


def supported_tools() -> list[str]:
    from app.ai.tool_permission_matrix import (
        TOOL_CLARIFICATION,
        TOOL_COMPARISON,
        TOOL_CONVERSATIONAL,
        TOOL_IMAGE_CONTEXT,
        TOOL_MONGODB_BRAND_INVENTORY,
        TOOL_MONGODB_SEARCH,
        TOOL_RAG,
        TOOL_RECOMMENDATION,
        TOOL_SUPPORT,
    )
    return [
        TOOL_MONGODB_SEARCH, TOOL_MONGODB_BRAND_INVENTORY, TOOL_COMPARISON,
        TOOL_RECOMMENDATION, TOOL_SUPPORT, TOOL_RAG, TOOL_IMAGE_CONTEXT,
        TOOL_CONVERSATIONAL, TOOL_CLARIFICATION,
    ]


def resolve_catalog_entities(message: str, *, parsed: dict | None = None) -> DomainEntities:
    """Resolve entities via central catalog resolver."""
    from app.ai.catalog_entity_resolver import resolve_entities
    from app.chatbot.assistant_intelligence import resolve_purpose_key

    resolved = resolve_entities(message, parsed=parsed)
    purpose = resolve_purpose_key(message)
    return DomainEntities(
        category=resolved.get("category"),
        purpose=purpose,
        city=resolved.get("city"),
        brand=resolved.get("brand"),
        model=resolved.get("model"),
        budget=resolved.get("max_price"),
        listing_type=resolved.get("listing_type"),
        requested_asset=resolved.get("category") or purpose or resolved.get("brand"),
    )


def validate_catalog_entities(entities: DomainEntities) -> CapabilityValidation:
    """Check whether resolved entities exist in supported catalog."""
    from app.ai.category_mapping import canonicalize_category
    from app.ai.brand_catalog import detect_brand
    from app.ai.purpose_taxonomy import categories_for_purpose

    cap = CapabilityValidation(registry_checked=True, catalog_checked=True)
    has_cat = bool(entities.category and canonicalize_category(entities.category))
    has_purpose = bool(entities.purpose and categories_for_purpose(entities.purpose))
    has_brand = bool(entities.brand and detect_brand(entities.brand or ""))

    if has_cat:
        cap.requested_asset_supported = True
        cap.catalog_match_type = "category"
        cap.closest_supported_capability = canonicalize_category(entities.category)
    elif has_purpose:
        cap.requested_asset_supported = True
        cap.catalog_match_type = "purpose"
        cats = categories_for_purpose(entities.purpose or "")
        cap.closest_supported_capability = cats[0] if cats else entities.purpose
    elif has_brand:
        cap.requested_asset_supported = True
        cap.catalog_match_type = "brand"
        cap.closest_supported_capability = f"brand:{entities.brand}"
    elif entities.model:
        cap.requested_asset_supported = None
        cap.catalog_match_type = "model"
        cap.notes.append("model_requires_category_confirmation")
    else:
        cap.requested_asset_supported = False
        cap.catalog_match_type = "none"

    return cap


def has_marketplace_action_signal(message: str) -> bool:
    return bool(_MARKETPLACE_ACTION_RE.search(message or ""))


def has_support_action_signal(message: str) -> bool:
    text = message or ""
    if _SUPPORT_ACTION_RE.search(text):
        return True
    # Explicit support / help desk requests
    if re.search(
        r"\b(?:help\s+from\s+support|contact\s+support|need\s+support|"
        r"platform\s+support|customer\s+support|talk\s+to\s+support|"
        r"support\s+team|support\s+help|madad\s+chahiye|support\s+se)\b",
        text,
        re.I,
    ):
        return True
    # Issue/problem with booking/order/payment — support, not unsupported listing
    if re.search(
        r"\b(?:booking|order|payment|transaction|invoice|deposit)\b.{0,30}\b(?:issue|problem|help|failed|stuck)\b",
        text,
        re.I,
    ):
        return True
    if re.search(
        r"\b(?:issue|problem|help)\b.{0,30}\b(?:booking|order|payment|refund)\b",
        text,
        re.I,
    ):
        return True
    return False


def has_document_signal(message: str) -> bool:
    return bool(_DOCUMENT_RE.search(message or ""))


def message_has_domain_vocabulary(message: str) -> bool:
    lower = (message or "").lower()
    if not lower:
        return False
    vocab = _domain_vocabulary_tokens()
    for token in vocab:
        if len(token) <= 3:
            continue
        if token in lower:
            return True
        if re.search(rf"\b{re.escape(token)}s?\b", lower):
            return True
    return False


def closest_supported_capability_for_message(
    message: str,
    entities: DomainEntities,
) -> str | None:
    """Suggest nearest supported capability when request is adjacent/unsupported."""
    if entities.purpose:
        from app.ai.purpose_taxonomy import categories_for_purpose
        cats = categories_for_purpose(entities.purpose)
        if cats:
            return f"machine_search:{cats[0]}"
    if entities.category:
        from app.ai.category_mapping import canonicalize_category
        cat = canonicalize_category(entities.category)
        if cat:
            return f"machine_search:{cat}"
    if message_has_domain_vocabulary(message):
        return "machine_recommendation"
    return "machine_search"


def validate_marketplace_request(
    message: str,
    *,
    parsed: dict | None = None,
    entities: DomainEntities | None = None,
) -> CapabilityValidation:
    """
    Validate before routing to broad_machine_request.
    Returns whether asset/action is supported by catalog.
    """
    entities = entities or resolve_catalog_entities(message, parsed=parsed)
    cap = validate_catalog_entities(entities)
    cap.requested_action_supported = has_marketplace_action_signal(message) or bool(
        entities.category or entities.purpose or entities.city
    )

    if cap.requested_asset_supported is False and has_marketplace_action_signal(message):
        if message_has_domain_vocabulary(message):
            cap.requested_asset_supported = None
            cap.notes.append("domain_vocab_but_no_catalog_entity")
        else:
            cap.notes.append("marketplace_action_without_catalog_match")
            cap.closest_supported_capability = closest_supported_capability_for_message(
                message, entities,
            )

    return cap


def capability_summary_for_prompt() -> dict[str, Any]:
    """Compact capability summary for LLM prompts (no secrets)."""
    return {
        "supported_domains": ["construction", "infrastructure", "heavy_equipment", "marketplace"],
        "supported_marketplace_actions": supported_marketplace_actions(),
        "supported_knowledge_areas": supported_knowledge_areas(),
        "category_count": len(supported_categories()),
        "purpose_count": len(supported_purposes()),
        "restricted": [
            "confirm_booking", "confirm_payment", "claim_availability",
            "invent_prices", "invent_owner_contact", "mutate_database",
        ],
    }
