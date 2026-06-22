"""
MongoDB persistence for RAG chunks and assistant session state.

Survives server restarts. Uses sync PyMongo for writes from sync helpers
and Motor for async startup loads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient

from app.core.config import settings

RAG_COLLECTION = "rag_chunks"
SESSIONS_COLLECTION = "assistant_sessions"

_sync_client: MongoClient | None = None
_session_index_ensured = False


def _sync_db():
    global _sync_client
    if _sync_client is None:
        if not settings.MONGODB_URL:
            raise RuntimeError("MONGODB_URL is not set")
        _sync_client = MongoClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=10_000,
            connectTimeoutMS=10_000,
            socketTimeoutMS=20_000,
        )
    return _sync_client[settings.DATABASE_NAME]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

def persist_rag_chunks(chunks: list[dict]) -> int:
    """Insert new RAG chunks. Each item: {text, embedding}."""
    if not chunks:
        return 0
    col = _sync_db()[RAG_COLLECTION]
    docs = []
    ts = _now()
    for item in chunks:
        docs.append({
            "text": item["text"],
            "embedding": item["embedding"],
            "created_at": ts,
        })
    col.insert_many(docs)
    return len(docs)


async def load_rag_chunks_async(database) -> list[dict]:
    col = database[RAG_COLLECTION]
    out = []
    async for doc in col.find({}, {"text": 1, "embedding": 1}).sort("created_at", 1):
        if doc.get("text") and doc.get("embedding"):
            out.append({"text": doc["text"], "embedding": doc["embedding"]})
    return out


async def count_rag_chunks_async(database) -> int:
    return await database[RAG_COLLECTION].count_documents({})


# ---------------------------------------------------------------------------
# Assistant sessions (chat history + filters + image context)
# ---------------------------------------------------------------------------

def ensure_session_indexes() -> None:
    """Create session indexes once at startup — never on every read/write."""
    global _session_index_ensured
    if _session_index_ensured:
        return
    try:
        _sync_db()[SESSIONS_COLLECTION].create_index("session_id", unique=True)
        _session_index_ensured = True
    except Exception as exc:
        print(f"[persist] session index skipped: {exc}")


def _session_col():
    return _sync_db()[SESSIONS_COLLECTION]


def load_session_doc(session_id: str) -> dict | None:
    session_id = (session_id or "").strip()
    if not session_id:
        return None
    try:
        return _session_col().find_one({"session_id": session_id})
    except Exception as exc:
        print(f"[persist] load_session_doc failed: {exc}")
        return None


def persist_session_fields(
    session_id: str,
    *,
    history: list | None = None,
    filters: dict | None = None,
    image_context: dict | None = None,
    pending_clarification: dict | None = None,
    recommendation_context: dict | None = None,
    session_context: dict | None = None,
) -> None:
    session_id = (session_id or "").strip()
    if not session_id:
        return

    update: dict[str, Any] = {"updated_at": _now()}
    if history is not None:
        update["history"] = history[-20:]
    if filters is not None:
        update["filters"] = filters
    if image_context is not None:
        update["image_context"] = image_context
    if pending_clarification is not None:
        update["pending_clarification"] = pending_clarification
    if recommendation_context is not None:
        update["recommendation_context"] = recommendation_context
    if session_context is not None:
        update["session_context"] = session_context

    try:
        _session_col().update_one(
            {"session_id": session_id},
            {"$set": update, "$setOnInsert": {"session_id": session_id, "created_at": _now()}},
            upsert=True,
        )
    except Exception as exc:
        print(f"[persist] persist_session_fields failed: {exc}")


async def warm_session_cache_async(database, *, limit: int = 500) -> int:
    """Load recent sessions into in-memory caches on startup."""
    from app.chatbot import chatbot_service
    from app.chatbot.image_context_memory import hydrate_image_context_cache
    from app.chatbot.memory import hydrate_history_cache

    count = 0
    cursor = database[SESSIONS_COLLECTION].find({}).sort("updated_at", -1).limit(limit)
    async for doc in cursor:
        sid = doc.get("session_id")
        if not sid:
            continue
        if doc.get("history"):
            hydrate_history_cache(sid, doc["history"])
        if doc.get("filters"):
            chatbot_service.hydrate_filters_cache(sid, doc["filters"])
        if doc.get("image_context"):
            hydrate_image_context_cache(sid, doc["image_context"])
        count += 1
    return count
