"""
Dynamic LLM response generator — controls HOW the assistant speaks.

Backend Response Plan defines WHAT; this module generates natural wording.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from app.ai.text_understanding_service import extract_json_from_text
from app.core.config import settings

_GENERATOR_PROMPT = """You are the final response writer for InfraForge assistant.

Your job:
Generate a natural, helpful, non-repetitive user-facing response.

You must follow the Response Plan exactly.

Rules:
- Do not change intent.
- Do not change backend action.
- Do not invent machines.
- Do not invent prices.
- Do not invent availability.
- Do not invent owner details.
- Do not invent refund status.
- Do not invent delivery date.
- Do not invent document facts.
- Do not claim ticket/order/action completed unless backend confirms it.
- Use only tool_result and known_context.
- Ask only for missing fields listed in must_ask.
- Keep response short and useful.
- Match user's language style: English, Hindi, or Hinglish.
- Avoid repeating previous wording listed in avoid_repeating / avoid_phrases.
- If user seems frustrated, be calm and empathetic.
- If result exists, present it clearly using only tool_result facts.
- If no result exists, suggest safe next steps from suggestions.

Return strict JSON only:
{
  "message": "...",
  "suggestions": [],
  "response_signature": "...",
  "next_best_action": "..."
}"""


def _local_fallback_from_plan(
    response_plan: dict[str, Any],
    *,
    session_id: str = "",
) -> dict[str, Any]:
    """Safe local fallback — uses plan facts, variant picker avoids repetition."""
    from app.ai.conversation_aware_response import generate_conversation_aware_response

    tool = response_plan.get("tool_result") or {}
    draft = tool.get("message") or ""
    goal = response_plan.get("response_goal") or "continue_followup"
    known = response_plan.get("known_context") or {}
    avoid = list(response_plan.get("avoid_repeating") or [])

    direct_answer_goals = frozenset({"domain_knowledge_answer", "assistant_identity"})
    if goal in direct_answer_goals and draft.strip():
        sig = compute_response_signature(draft, goal)
        return {
            "message": draft,
            "suggestions": list(response_plan.get("suggestions") or []),
            "response_signature": sig,
            "response_style": "informative",
            "next_best_action": goal,
            "gateway_used": True,
            "fallback_used": True,
            "llm_generated": False,
        }

    ctx = {
        "session_id": session_id or known.get("session_id"),
        "user_name": known.get("user_name"),
        "turn_count": 0,
        "recent_variant_ids": avoid,
        "recent_response_signatures": avoid,
        "avoid_repeating": avoid,
    }

    base = generate_conversation_aware_response(
        intent=response_plan.get("intent") or "unknown",
        assistant_mode=response_plan.get("assistant_mode") or "clarification",
        response_goal=goal,
        entities={"name": known.get("user_name")},
        missing_fields=known.get("pending_fields"),
        tool_result=tool,
        session_context=ctx,
        language=response_plan.get("language") or "english",
        sentiment=response_plan.get("user_sentiment") or "neutral",
        session_id=session_id or known.get("session_id") or "default",
        draft_message=draft,
    )
    sig = compute_response_signature(base["message"], goal)
    avoided = sig not in avoid
    if not avoided:
        for bump in range(1, 6):
            ctx["turn_count"] = bump
            retry = generate_conversation_aware_response(
                intent=response_plan.get("intent") or "unknown",
                assistant_mode=response_plan.get("assistant_mode") or "clarification",
                response_goal=goal,
                entities={"name": known.get("user_name")},
                missing_fields=known.get("pending_fields"),
                tool_result=tool,
                session_context=ctx,
                language=response_plan.get("language") or "english",
                sentiment=response_plan.get("user_sentiment") or "neutral",
                session_id=session_id or known.get("session_id") or "default",
                draft_message=draft,
            )
            retry_sig = compute_response_signature(retry["message"], goal)
            if retry_sig not in avoid:
                base = retry
                sig = retry_sig
                avoided = True
                break

    return {
        "message": base["message"],
        "suggestions": base.get("suggestions") or response_plan.get("suggestions") or [],
        "response_signature": sig,
        "next_best_action": base.get("next_best_action") or goal,
        "response_goal": goal,
        "response_style": base.get("response_style", "local_dynamic_fallback"),
        "response_variant_id": base.get("response_variant_id"),
        "preserve_machine_panel": tool.get("preserve_machine_panel", bool(tool.get("machines"))),
        "llm_generated": False,
        "fallback_used": True,
        "avoided_recent_signature": avoided,
    }


def compute_response_signature(message: str, response_goal: str = "") -> str:
    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())[:200]
    raw = f"{response_goal}|{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_llm_response(raw: str, response_plan: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        parsed = extract_json_from_text(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    message = str(parsed.get("message") or "").strip()
    if len(message) < 3:
        return None
    goal = response_plan.get("response_goal") or ""
    sig = str(parsed.get("response_signature") or "").strip() or compute_response_signature(message, goal)
    suggestions = parsed.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = response_plan.get("suggestions") or []
    return {
        "message": message,
        "suggestions": [str(s) for s in suggestions[:8]],
        "response_signature": sig,
        "next_best_action": str(parsed.get("next_best_action") or goal),
        "response_goal": goal,
        "response_style": "llm_dynamic",
        "preserve_machine_panel": bool((response_plan.get("tool_result") or {}).get("machines")),
        "llm_generated": True,
        "fallback_used": False,
    }


async def _call_llm_generator(
    response_plan: dict[str, Any],
    user_message: str,
    previous_responses: Optional[list[dict]] = None,
) -> Optional[dict[str, Any]]:
    if not settings.GROQ_API_KEY:
        return None
    if settings.openai_usable and settings.AI_PROVIDER == "openai":
        return None  # Groq primary unless OpenAI explicitly enabled later

    from app.core.groq_client import groq_chat_completion

    prev = previous_responses or []
    prev_block = json.dumps(
        [{"summary": p.get("summary"), "signature": p.get("signature")} for p in prev[-4:]],
        ensure_ascii=False,
    )
    plan_json = json.dumps(response_plan, ensure_ascii=False, default=str)
    goal = response_plan.get("response_goal") or ""
    direct_note = ""
    if goal in ("domain_knowledge_answer", "assistant_identity"):
        direct_note = (
            "\nIMPORTANT: The user asked a direct question. Answer it clearly in the first sentence. "
            "Do NOT ask what they need, do NOT say you are unsure, do NOT redirect to search unless "
            "offering it as an optional next step after answering.\n"
        )
    prompt = (
        f"{_GENERATOR_PROMPT}{direct_note}\n\n"
        f"USER MESSAGE:\n{user_message}\n\n"
        f"RESPONSE PLAN:\n{plan_json}\n\n"
        f"PREVIOUS RESPONSES:\n{prev_block}\n"
    )
    try:
        response = groq_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.35,
            tag="dynamic_response",
        )
    except Exception:
        return None
    if not response:
        return None
    raw = (response.choices[0].message.content or "").strip()
    return _parse_llm_response(raw, response_plan)


async def generate_dynamic_response(
    response_plan: dict[str, Any],
    user_message: str,
    session_context: Optional[dict[str, Any]] = None,
    previous_responses: Optional[list[dict]] = None,
    *,
    session_id: str = "",
) -> dict[str, Any]:
    """
    Generate final user-facing message from Response Plan.
    LLM when enabled; safe local fallback otherwise.
    """
    ctx = session_context or {}
    sid = session_id or (response_plan.get("known_context") or {}).get("session_id") or ""

    if settings.use_llm_response_generation:
        llm_out = await _call_llm_generator(response_plan, user_message, previous_responses)
        if llm_out:
            llm_out["gateway_used"] = True
            llm_out["avoided_recent_signature"] = True
            if settings.ENVIRONMENT in ("development", "dev", "local"):
                print(
                    "[dynamic_response] llm_ok",
                    f"goal={response_plan.get('response_goal')}",
                    f"sig={llm_out.get('response_signature')}",
                )
            return llm_out
        if settings.ENVIRONMENT in ("development", "dev", "local"):
            print(
                "[dynamic_response] llm_failed -> local_fallback",
                f"goal={response_plan.get('response_goal')}",
            )

    out = _local_fallback_from_plan(response_plan, session_id=sid)
    out["gateway_used"] = True
    return out
