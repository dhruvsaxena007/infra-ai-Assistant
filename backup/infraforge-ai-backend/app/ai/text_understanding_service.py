"""
Text understanding for chat/voice routes.

Default: rules-first (no Groq). Set USE_GROQ_TEXT_UNDERSTANDING=true to fall back
to Groq for ambiguous messages only.
"""

import json
import re

from app.ai.rules_understanding import understand_user_text_rules
from app.core.config import settings
from app.core.groq_client import client

def extract_json_from_text(text: str):
    """
    Extract JSON object from LLM response safely.
    """

    text = text.strip()

    # Remove markdown json block if exists
    text = text.replace("```json", "")
    text = text.replace("```", "")
    text = text.strip()

    # Try direct JSON parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Extract first JSON object from text
    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL
    )

    if match:
        return json.loads(match.group())

    raise ValueError("No valid JSON found in model response")


def understand_user_text(message: str):
    """
    Understand user text — rules-first; optional Groq when USE_GROQ_TEXT_UNDERSTANDING=true.
    """
    rules_result = understand_user_text_rules(message)
    if rules_result.get("success") and not settings.USE_GROQ_TEXT_UNDERSTANDING:
        return rules_result

    if rules_result.get("success"):
        data = rules_result.get("data") or {}
        if data.get("machine_type") or data.get("brand") or data.get("city"):
            return rules_result

    try:

        prompt = f"""
You are an AI assistant for a construction machine marketplace.

User message:
{message}

Understand the message even if it is in:
- English
- Hindi
- Hinglish

Return ONLY valid JSON.
Do not write explanation.
Do not write markdown.
Do not write ```json.

JSON format:
{{
  "original_message": "{message}",
  "translated_query": "",
  "machine_type": "",
  "brand": "",
  "model": "",
  "city": "",
  "max_price": null,
  "min_price": null,
  "condition": "",
  "pincode": "",
  "listing_type": "",
  "rent_type": "",
  "intent": "",
  "is_follow_up": false
}}

Rules:
- translated_query must be English.
- machine_type examples: excavator, backhoe loader, hydra crane, crane,
  bulldozer, road roller, dump truck, concrete mixer, motor grader, wheel loader,
  crawler drill, concrete pump, air compressor, mobile crusher.
- IMPORTANT: "jcb", "jcb 3dx", "3dx", "jcb 4dx", "backhoe", "backhoe loader",
  "loader backhoe" all mean "backhoe loader". Never map JCB to excavator.
- "excavator", "earth excavator", "digger", "poclain", "digging machine" mean
  "excavator" only.
- Do NOT map a generic "earth mover" / "earthmoving" to excavator. If the user
  only says "earth mover" without naming excavator/bulldozer/loader, leave
  machine_type as "" (empty).
- city must be detected if present.
- max_price should be number or null.
- min_price should be number or null.
- intent must be one of:
  search,
  cheaper_options,
  city_switch,
  recommendation,
  comparison,
  free_request,
  list_all,
  override,
  unknown.
- If user says sasta, cheap, cheaper, low price, set intent as cheaper_options.
- If user says same in jaipur, what about mumbai, set intent as city_switch.
- If user says free, free of cost, zero cost, no cost, set intent as free_request.
- If user says list all, show all, all machines, set intent as list_all.
- If user says instead of, rather than, replace, set intent as override.
"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0
        )

        content = response.choices[0].message.content

        print("GROQ RAW RESPONSE:", content)

        parsed = extract_json_from_text(
            content
        )

        return {
            "success": True,
            "data": parsed
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }