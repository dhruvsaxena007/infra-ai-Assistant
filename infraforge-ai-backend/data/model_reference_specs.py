"""
Reference specifications for common construction equipment models.

Used for knowledge/spec queries - not live marketplace listings.
Values are typical manufacturer specs for India-market models.
"""

from __future__ import annotations

from typing import Any, Optional

# (brand_lower, model_lower) -> spec dict
MODEL_SPECS: dict[tuple[str, str], dict[str, Any]] = {
    ("komatsu", "pc210"): {
        "engine_power": "123 HP (93 kW)",
        "operating_weight": "21,000 kg",
        "bucket_capacity": "0.8-1.2 m3",
        "max_digging_depth": "6.6 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "General excavation, trenching, earthmoving, road and building projects",
    },
    ("komatsu", "pc200"): {
        "engine_power": "148 HP (110 kW)",
        "operating_weight": "20,500 kg",
        "bucket_capacity": "0.8-1.0 m3",
        "max_digging_depth": "6.5 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "Medium excavation, utilities, urban construction",
    },
    ("jcb", "3dx"): {
        "engine_power": "74 HP (55 kW)",
        "operating_weight": "8,080 kg",
        "bucket_capacity": "1.0 m3 (loader) / 0.26 m3 (backhoe)",
        "fuel_type": "Diesel",
        "category": "backhoe loader",
        "applications": "Urban construction, utilities, small-to-mid excavation, loading",
    },
    ("cat", "320d"): {
        "engine_power": "121 HP (90 kW)",
        "operating_weight": "21,300 kg",
        "bucket_capacity": "0.9-1.2 m3",
        "max_digging_depth": "6.7 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "Heavy excavation, mining support, infrastructure",
    },
    ("caterpillar", "320d"): {
        "engine_power": "121 HP (90 kW)",
        "operating_weight": "21,300 kg",
        "bucket_capacity": "0.9-1.2 m3",
        "max_digging_depth": "6.7 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "Heavy excavation, mining support, infrastructure",
    },
    ("tata hitachi", "zaxis 140"): {
        "engine_power": "98 HP (73 kW)",
        "operating_weight": "14,200 kg",
        "bucket_capacity": "0.5-0.7 m3",
        "max_digging_depth": "5.5 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "Medium excavation, urban sites, utilities",
    },
    ("hyundai", "r140lc-9"): {
        "engine_power": "95 HP (71 kW)",
        "operating_weight": "14,000 kg",
        "bucket_capacity": "0.5-0.7 m3",
        "max_digging_depth": "5.4 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "General excavation, road work, building foundations",
    },
    ("hyundai", "r210"): {
        "engine_power": "148 HP (110 kW)",
        "operating_weight": "21,500 kg",
        "bucket_capacity": "0.9-1.2 m3",
        "max_digging_depth": "6.7 m",
        "fuel_type": "Diesel",
        "fuel_consumption": "14-18 L/hr (typical working load)",
        "category": "excavator",
        "applications": "Medium-to-heavy excavation, road projects, quarry support",
    },
    ("schwing stetter", "am"): {
        "drum_capacity": "6-8 m3 (model dependent)",
        "output_capacity": "Up to 100 m3/hr (plant dependent)",
        "fuel_type": "Diesel",
        "category": "concrete mixer",
        "applications": "Ready-mix concrete production, batching plants, infrastructure projects",
        "note": "Schwing Stetter AM series covers transit mixers and batching plant equipment.",
    },
    ("volvo", "ec210"): {
        "engine_power": "160 HP (119 kW)",
        "operating_weight": "21,800 kg",
        "bucket_capacity": "0.9-1.2 m3",
        "max_digging_depth": "6.8 m",
        "fuel_type": "Diesel",
        "category": "excavator",
        "applications": "Excavation, quarry, heavy earthmoving",
    },
}

_CATEGORY_FALLBACK: dict[str, dict[str, str]] = {
    "excavator": {
        "applications": "Digging, trenching, earthmoving, demolition support",
        "fuel_type": "Diesel (typical)",
        "note": "Specs vary by model - share brand/model for exact figures.",
    },
    "backhoe loader": {
        "applications": "Loading, backhoe digging, urban utilities, small sites",
        "fuel_type": "Diesel (typical)",
        "note": "JCB 3DX is the most common backhoe loader in India.",
    },
    "concrete mixer": {
        "applications": "On-site concrete mixing, RMC supply, building and road projects",
        "fuel_type": "Diesel (typical)",
        "note": "Specs vary by drum size and chassis — share brand/model for exact figures.",
    },
    "concrete mixer truck": {
        "applications": "Transporting ready-mix concrete from plant to pour site",
        "fuel_type": "Diesel (typical)",
        "note": "Drum capacity and chassis specs vary by model.",
    },
}


def lookup_model_specs(
    *,
    brand: str | None = None,
    model: str | None = None,
    category: str | None = None,
) -> Optional[dict[str, Any]]:
    """Return reference specs for brand+model, or category fallback."""
    b = (brand or "").strip().lower()
    m = (model or "").strip().lower().replace("-", " ")

    if b and m:
        key = (b, m)
        if key in MODEL_SPECS:
            return {**MODEL_SPECS[key], "brand": brand, "model": model}
        compact_m = m.replace(" ", "")
        for (bk, mk), specs in MODEL_SPECS.items():
            if bk == b and mk.replace(" ", "") == compact_m:
                return {**specs, "brand": brand, "model": model}

    cat = (category or "").strip().lower().replace("-", " ")
    if cat and cat in _CATEGORY_FALLBACK:
        return {**_CATEGORY_FALLBACK[cat], "category": category}
    return None
