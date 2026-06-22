"""
OpenAI-powered intent extraction for marketplace search queries.

Reads OPENAI_API_KEY from .env (via python-dotenv).
Install dependency: pip install openai
"""

import json
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAIError, RateLimitError

from app.core.config import settings

load_dotenv()

logger = logging.getLogger(__name__)

# Default shape when OpenAI is unavailable or JSON parsing fails
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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Create the OpenAI client once (lazy loading)."""
    global _client

    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is missing. Add it to your .env file, for example: "
            "OPENAI_API_KEY=sk-your-key-here"
        )

    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    return _client


def _normalize_intent(data: dict[str, Any]) -> dict[str, Any]:
    """
    Clean and validate the parsed JSON so callers always get a safe shape.
    """
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
    """Parse the model's JSON string safely."""
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

    Example input:
        "I need excavator in delhi under 8000"

    Example output:
        {
            "category": "excavator",
            "city": "delhi",
            "max_price": 8000
        }

    On errors (API failure, bad JSON, etc.) returns empty defaults so the app
    does not crash. Check logs if results look wrong.
    """
    query = (query or "").strip()
    if not query:
        return dict(DEFAULT_INTENT)

    if not settings.USE_OPENAI_INTENT_PARSER:
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

    except RateLimitError:
        logger.error("OpenAI rate limit hit during intent extraction")
        return dict(DEFAULT_INTENT)

    except APIConnectionError:
        logger.error("Could not connect to OpenAI API")
        return dict(DEFAULT_INTENT)

    except APIStatusError as exc:
        logger.error("OpenAI API error: %s", exc.message)
        return dict(DEFAULT_INTENT)

    except OpenAIError:
        logger.exception("Unexpected OpenAI error during intent extraction")
        return dict(DEFAULT_INTENT)

    except ValueError:
        # Missing API key — re-raise so developers fix .env early
        raise

    except Exception:
        logger.exception("Unexpected error during intent extraction")
        return dict(DEFAULT_INTENT)
