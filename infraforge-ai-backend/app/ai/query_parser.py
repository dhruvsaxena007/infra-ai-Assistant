"""

Deterministic query parser for InfraForge marketplace search.



Return shape:

    {

        city, category, max_price,

        brand, model, condition, pincode,

        listing_type, rent_type,

    }

"""



from app.ai.category_mapping import (
    detect_all_brands,
    detect_brand,
    detect_city,
    detect_condition,
    detect_entity_validation_notes,
    detect_listing_type,
    detect_max_price,
    detect_model,
    detect_pincode,
    detect_region,
    detect_rent_type,
    detect_requested_category,
)
from app.ai.numeric_normalizer import expand_numeric_shorthand
from app.ai.transcript_normalizer import normalize_transcribed_text
from app.ai.purpose_intent_engine import enrich_parsed_with_purpose


def _normalize_query_text(query: str) -> str:
    """Apply numeric + Hindi/Latin normalization for consistent entity detection."""
    text = (query or "").strip()
    if not text:
        return ""
    # Expand 7k, 8.5k, lakh BEFORE transcript normalizer (which can split decimals)
    text = expand_numeric_shorthand(text)
    return normalize_transcribed_text(text) or text


def parse_query(query: str):
    normalized = _normalize_query_text(query)
    result = {
        "city": detect_city(normalized),
        "region": detect_region(normalized),
        "category": detect_requested_category(normalized),
        "max_price": detect_max_price(normalized),
        "brand": detect_brand(normalized),
        "brands": detect_all_brands(normalized),
        "model": detect_model(normalized),
        "condition": detect_condition(normalized),
        "pincode": detect_pincode(normalized),
        "listing_type": detect_listing_type(normalized),
        "rent_type": detect_rent_type(normalized),
    }
    result["validation_notes"] = detect_entity_validation_notes(normalized, result)
    return enrich_parsed_with_purpose(result, normalized)





def is_empty_filters(filters: dict) -> bool:

    return not any(

        filters.get(key)

        for key in (
            "category", "city", "region", "brand", "model",
            "condition", "pincode", "listing_type",
        )

    ) and filters.get("max_price") is None


