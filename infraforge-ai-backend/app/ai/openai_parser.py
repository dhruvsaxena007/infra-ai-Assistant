"""
OpenAI-powered intent extraction for marketplace search queries.

Disabled by default. Requires:
  ENABLE_OPENAI=true
  AI_PROVIDER=openai
  OPENAI_API_KEY=sk-...
  USE_OPENAI_INTENT_PARSER=true
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

OPENAI_DISABLED_MSG = "OpenAI provider disabled"

DEFAULT_INTENT: dict[str, Any] = {
    "category": "",
    "city": "",
    "max_price": None,
    "brand": "",
    "model": "",
    "condition": "",
    "pincode": "",
    "listing_type": "",
    "rent_type": "",
}

OPENAI_MODEL = __import__("os").getenv("OPENAI_MODEL", "gpt-4o-mini")

_client: Optional[Any] = None


def _ensure_openai_allowed() -> None:
    if not settings.openai_intent_enabled:
        raise ValueError(OPENAI_DISABLED_MSG)


def _get_client() -> Any:
    """Create the OpenAI client once (lazy loading)."""
    global _client
    _ensure_openai_allowed()

    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is missing. Add it to your .env file when ENABLE_OPENAI=true."
        )

    if _client is None:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    return _client


def _normalize_intent(data: dict[str, Any]) -> dict[str, Any]:
    def _str_field(key: str) -> str:
        return str(data.get(key) or "").strip().lower()

    category = _str_field("category")
    city = _str_field("city")
    brand = str(data.get("brand") or "").strip()
    model = str(data.get("model") or "").strip()
    condition = _str_field("condition")
    pincode = str(data.get("pincode") or "").strip()
    listing_type = _str_field("listing_type")
    rent_type = _str_field("rent_type")

    max_price = data.get("max_price")
    if max_price in (None, "", "null"):
        max_price = None
    else:
        try:
            max_price = int(float(max_price))
            if max_price < 0:
                max_price = None
        except (TypeError, ValueError):
            max_price = None

    return {
        "category": category,
        "city": city,
        "max_price": max_price,
        "brand": brand or None,
        "model": model or None,
        "condition": condition or None,
        "pincode": pincode or None,
        "listing_type": listing_type or None,
        "rent_type": rent_type or None,
    }


def _parse_json_content(content: Optional[str]) -> dict[str, Any]:
    if not content or not content.strip():
        logger.warning("OpenAI returned empty content for intent extraction")
        return dict(DEFAULT_INTENT)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.exception("Failed to decode OpenAI JSON response: %s", content)
        return dict(DEFAULT_INTENT)

    if not isinstance(parsed, dict):
        logger.warning("OpenAI JSON was not an object: %s", type(parsed))
        return dict(DEFAULT_INTENT)

    return _normalize_intent(parsed)


async def extract_intent(query: str) -> dict[str, Any]:
    """
    Use GPT to extract search filters from a natural language message.
    Returns empty defaults when OpenAI is disabled — never bills credits.
    """
    query = (query or "").strip()
    if not query:
        return dict(DEFAULT_INTENT)

    if not settings.openai_intent_enabled:
        return dict(DEFAULT_INTENT)

    system_prompt = """
You extract search filters from user messages about renting or buying construction machines
(excavators, crawler drills, cranes, backhoe loaders, dump trucks, etc.).

Return ONLY valid JSON with exactly these keys:
{
  "category": "",
  "city": "",
  "max_price": null,
  "brand": "",
  "model": "",
  "condition": "",
  "pincode": "",
  "listing_type": "",
  "rent_type": ""
}

Rules:
- category: machine type if mentioned (e.g. crawler drill, excavator, backhoe loader), else ""
- city: city name if mentioned, else ""
- max_price: number if user mentions budget (under 500, below 8k), else null
- brand: brand if mentioned (EPIROC, JCB, CAT), else ""
- model: model if mentioned (AIR ROC D-35, 3DX), else ""
- condition: used/new if mentioned, else ""
- pincode: 6-digit Indian pincode if mentioned, else ""
- listing_type: rent or sell if mentioned, else ""
- rent_type: daily/hourly if mentioned, else ""
- Use lowercase for category, city, condition, listing_type, rent_type
- Do not include any text outside the JSON object
""".strip()

    try:
        from openai import APIConnectionError, APIStatusError, OpenAIError, RateLimitError

        client = _get_client()

        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
        )

        content = response.choices[0].message.content
        return _parse_json_content(content)

    except ValueError:
        raise

    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name in ("RateLimitError", "APIConnectionError", "APIStatusError", "OpenAIError"):
            logger.error("OpenAI API error during intent extraction: %s", exc)
        else:
            logger.exception("Unexpected error during intent extraction")
        return dict(DEFAULT_INTENT)
