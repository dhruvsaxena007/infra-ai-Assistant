#!/usr/bin/env python3
"""
Assistant brain routing audit — reports intent, mode, route, memory, RAG, search.

Usage:
  python scripts/run_routing_audit.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import rag_service
from app.chatbot.chatbot_service import chatbot_response
from app.chatbot.memory import clear_conversation
from app.chatbot.image_context_memory import save_image_context, clear_image_context
from app.database.mongodb import database

DOC = (
    "Highway Project Equipment Guide. Motor grader, road roller, excavator required."
)

CASES = [
    ("greeting", "hi", None),
    ("machine_request_vague", "I need a machine", None),
    ("machine_request_specific", "excavator in Jaipur", None),
    ("machine_recommendation", "road project ke liye machine chahiye", None),
    ("recommendation_followup", "compaction", "rec_followup"),
    ("support_request", "how to rent a machine", None),
    ("refund_request", "refund chahiye", None),
    ("image_followup", "is this available in Jaipur?", "image_ctx"),
    ("document_question_no_doc", "what does the uploaded document say about machines?", None),
    ("document_question_with_doc", "What machines are needed for highway project?", "rag_doc"),
]


def _analyze(resp: dict, user_message: str) -> dict:
    data = resp.get("data") or {}
    ctx = data.get("context") or {}
    msg = (resp.get("message") or "").lower()
    sources = data.get("sources") or []
    has_answer = bool(data.get("answer") or (len(msg) > 40 and "upload" not in msg))
    rag_used = bool(sources) or ctx.get("rag_scope") not in (None, "none") or "document" in str(ctx.get("intent", ""))
    if ctx.get("intent") == "document_question" and sources:
        rag_used = True
    if ctx.get("intent") not in ("document_question",) and not sources:
        # RAG leak check: long doc-style answer without document intent
        if "highway project" in msg and "motor grader" in msg and "document_question" not in str(ctx.get("intent", "")):
            rag_used = True
    return {
        "intent": ctx.get("intent") or ctx.get("classification", {}).get("intent") if isinstance(ctx.get("classification"), dict) else ctx.get("intent"),
        "assistant_mode": ctx.get("assistant_mode") or data.get("assistant_mode"),
        "route_selected": _infer_route(ctx, data),
        "memory_used": bool(ctx.get("used_previous_context")),
        "rag_used": rag_used and bool(sources or data.get("answer")),
        "search_used": bool(data.get("machines")) or ctx.get("should_search_machines") or (data.get("search_status") or {}).get("exact_match_found") is not None,
        "machines": len(data.get("machines") or []),
        "message_preview": (resp.get("message") or "")[:80],
    }


def _infer_route(ctx: dict, data: dict) -> str:
    mode = ctx.get("assistant_mode") or ""
    intent = ctx.get("intent") or ""
    if mode == "document_qa" or intent == "document_question":
        return "rag_document_qa"
    if mode in ("refund_return", "payment_issue", "order_issue", "support"):
        return "support_response"
    if mode == "greeting":
        return "greeting"
    if mode in ("recommendation_clarification", "recommendation", "project_recommendation"):
        return "recommendation"
    if mode == "clarification":
        return "clarification"
    if mode == "image_clarification":
        return "image_clarify"
    if data.get("machines"):
        return "machine_search"
    if mode == "no_result":
        return "search_no_result"
    return mode or intent or "unknown"


async def _setup(session_id: str, setup: str | None):
    clear_conversation(session_id)
    rag_service.clear_rag_for_tests()
    if setup == "rag_doc":
        rag_service.add_document_to_rag(DOC, session_id=session_id)
    elif setup == "image_ctx":
        clear_image_context(session_id)
        save_image_context(session_id, detected_machine_type="excavator", search_query="excavator")
    elif setup == "rec_followup":
        await chatbot_response(session_id, "road project ke liye machine chahiye", database)


async def main():
    print("=" * 100)
    print("ASSISTANT ROUTING AUDIT")
    print("=" * 100)
    print(f"{'case':<28} {'intent':<22} {'mode':<22} {'route':<18} {'mem':<5} {'rag':<5} {'search':<6} {'#m':<4} OK?")
    print("-" * 100)

    issues = []
    for name, message, setup in CASES:
        sid = f"audit_{name}"
        await _setup(sid, setup)
        resp = await chatbot_response(sid, message, database)
        r = _analyze(resp, message)
        ok, note = _validate(name, r, setup)
        flag = "OK" if ok else f"BAD:{note}"
        if not ok:
            issues.append((name, note, r))
        print(
            f"{name:<28} {str(r['intent']):<22} {str(r['assistant_mode']):<22} "
            f"{r['route_selected']:<18} {str(r['memory_used']):<5} {str(r['rag_used']):<5} "
            f"{str(r['search_used']):<6} {r['machines']:<4} {flag}"
        )

    print("=" * 100)
    if issues:
        print("ISSUES FOUND:")
        for name, note, r in issues:
            print(f"  - {name}: {note}")
            print(f"    preview: {r['message_preview']!r}")
    else:
        print("All routing cases passed audit checks.")
    print("=" * 100)
    return 1 if issues else 0


def _validate(name: str, r: dict, setup: str | None) -> tuple[bool, str]:
    if name == "greeting":
        if r["rag_used"]:
            return False, "RAG on greeting"
        if r["route_selected"] != "greeting":
            return False, "not greeting route"
    if name == "machine_request_vague":
        if r["machines"] > 8:
            return False, "catalog dump (>8 machines)"
        if r["rag_used"]:
            return False, "RAG on vague machine request"
        if r["route_selected"] not in ("clarification", "machine_search"):
            return False, "should clarify not search dump"
    if name == "machine_request_specific":
        if r["rag_used"]:
            return False, "RAG on machine search"
    if name in ("machine_recommendation", "recommendation_followup"):
        if r["rag_used"]:
            return False, "RAG on recommendation"
    if name == "refund_request":
        if r["search_used"] and r["machines"] > 0:
            return False, "search on refund"
        if r["rag_used"]:
            return False, "RAG on refund"
    if name == "support_request":
        if r["rag_used"]:
            return False, "RAG on support/how-to"
    if name == "document_question_no_doc":
        if r["rag_used"]:
            return False, "RAG without document"
    if name == "document_question_with_doc":
        if not r["rag_used"] and r["route_selected"] != "rag_document_qa":
            return False, "should use RAG with session doc"
    if name == "image_followup":
        if r["route_selected"] == "rag_document_qa":
            return False, "RAG on image follow-up"
    return True, ""


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
