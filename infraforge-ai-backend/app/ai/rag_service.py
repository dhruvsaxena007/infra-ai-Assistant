import re

from app.ai.embedding_service import generate_embedding
from app.core.config import settings
from app.core.groq_client import groq_chat_completion
from app.utils.vector_math import cosine_similarity
from app.database.persistent_store import load_rag_chunks_async, persist_rag_chunks

# Global (legacy) chunks — no session_id on upload
document_chunks: list[dict] = []
# Session-scoped chunks — keyed by session_id
_session_chunks: dict[str, list[dict]] = {}
_rag_hydrated = False

RAG_TOP_K = 3
RAG_MIN_SCORE = 0.2
RAG_EXTRACTIVE_SCORE = 0.42


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_text(text: str, chunk_size: int = 500) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _normalize_session_id(session_id: str | None) -> str | None:
    sid = (session_id or "").strip()
    return sid or None


def _chunks_for_scope(session_id: str | None) -> list[dict]:
    """Session docs when present; otherwise legacy global fallback."""
    sid = _normalize_session_id(session_id)
    if sid:
        session_docs = _session_chunks.get(sid) or []
        if session_docs:
            return list(session_docs)
        return list(document_chunks)
    return list(document_chunks)


def rag_scope_for(session_id: str | None) -> str:
    sid = _normalize_session_id(session_id)
    if sid and _session_chunks.get(sid):
        return "session"
    if document_chunks:
        return "global"
    return "none"


async def hydrate_rag_from_mongo(database) -> int:
    """Load persisted RAG chunks into memory on server start."""
    global document_chunks, _session_chunks, _rag_hydrated
    if _rag_hydrated:
        return len(document_chunks) + sum(len(v) for v in _session_chunks.values())
    loaded = await load_rag_chunks_async(database)
    document_chunks = []
    _session_chunks = {}
    for item in loaded:
        sid = item.get("session_id")
        if sid:
            _session_chunks.setdefault(sid, []).append(item)
        else:
            document_chunks.append(item)
    _rag_hydrated = True
    total = len(document_chunks) + sum(len(v) for v in _session_chunks.values())
    return total


def add_document_to_rag(text: str, session_id: str | None = None) -> dict:
    global document_chunks, _session_chunks

    sid = _normalize_session_id(session_id)
    chunks = split_text(text)
    if not chunks:
        return {
            "success": False,
            "message": "No text content found in document",
            "chunks_added": 0,
            "total_chunks": len(_chunks_for_scope(sid)),
            "rag_scope": "session" if sid else "global",
        }

    new_items = []
    for chunk in chunks:
        item = {
            "text": chunk,
            "embedding": generate_embedding(chunk),
            "session_id": sid,
        }
        new_items.append(item)
        if sid:
            _session_chunks.setdefault(sid, []).append(item)
        else:
            document_chunks.append(item)

    persist_rag_chunks(new_items)

    scope_chunks = _chunks_for_scope(sid)
    return {
        "success": True,
        "message": "Document added successfully",
        "chunks_added": len(chunks),
        "total_chunks": len(scope_chunks),
        "persisted": True,
        "rag_scope": "session" if sid else "global",
        "session_id": sid,
    }


def _retrieve_top_chunks(question: str, chunks: list[dict], top_k: int = RAG_TOP_K) -> list[dict]:
    if not chunks:
        return []
    question_embedding = generate_embedding(question)
    scored = []
    for item in chunks:
        score = cosine_similarity(question_embedding, item["embedding"])
        scored.append({"text": item["text"], "score": float(score)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _extractive_answer(question: str, chunks: list[dict]) -> str:
    """
    Grounded answer from retrieved chunks only (no LLM).
    """
    q_tokens = {
        t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2
    }
    parts: list[str] = []
    for chunk in chunks:
        text = chunk["text"]
        if not q_tokens:
            parts.append(text)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            lower = sentence.lower()
            if any(tok in lower for tok in q_tokens):
                parts.append(sentence.strip())
        if not parts:
            parts.append(text[:400].strip())

    combined = " ".join(parts[:3]).strip()
    if len(combined) > 500:
        combined = combined[:497] + "..."
    return combined or "Information is not available in the uploaded document."


def generate_answer_from_context(
    question: str,
    context: str,
    *,
    top_score: float,
) -> tuple[str, str]:
    """
    Return (answer, source) where source is 'extractive' or 'groq'.
    """
    if top_score >= RAG_EXTRACTIVE_SCORE and not settings.USE_GROQ_RAG_ANSWER:
        return _extractive_answer(question, [{"text": context}]), "extractive"

    if not settings.USE_GROQ_RAG_ANSWER:
        return _extractive_answer(
            question,
            [{"text": context}],
        ), "extractive"

    prompt = f"""
You are a helpful AI assistant for a construction equipment marketplace.

Answer the user's question using ONLY the context below.

Question:
{question}

Context:
{context}

Rules:
- Keep answer short and clear.
- Do not make up information.
- If context does not contain answer, say information is not available in document.

Return only final answer.
"""
    response = groq_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        tag="rag_answer",
    )
    if response and response.choices:
        return response.choices[0].message.content.strip(), "groq"
    return (
        _extractive_answer(question, [{"text": context}]),
        "extractive_fallback",
    )


def rag_has_documents(session_id: str | None = None) -> bool:
    """True when session docs exist, or legacy global docs when session has none."""
    return bool(_chunks_for_scope(session_id))


def clear_rag_for_tests() -> None:
    """Test helper — clear in-memory RAG without touching Mongo."""
    global document_chunks, _session_chunks
    document_chunks = []
    _session_chunks = {}


def ask_rag_question(question: str, session_id: str | None = None) -> dict:
    sid = _normalize_session_id(session_id)
    scope = rag_scope_for(sid)
    chunks = _chunks_for_scope(sid)

    if not chunks:
        if sid:
            return {
                "success": False,
                "message": "No document uploaded yet for this session",
                "rag_scope": "none",
            }
        return {
            "success": False,
            "message": "No document uploaded yet",
            "rag_scope": "none",
        }

    question = (question or "").strip()
    if not question:
        return {
            "success": False,
            "message": "Question is required",
            "rag_scope": scope,
        }

    top_chunks = _retrieve_top_chunks(question, chunks)
    if not top_chunks or top_chunks[0]["score"] < RAG_MIN_SCORE:
        return {
            "success": False,
            "message": "Could not find relevant information",
            "rag_scope": scope,
        }

    context = "\n\n".join(
        f"[section {i + 1}]\n{c['text']}"
        for i, c in enumerate(top_chunks)
        if c["score"] >= RAG_MIN_SCORE
    )

    top_score = top_chunks[0]["score"]
    if top_score >= RAG_EXTRACTIVE_SCORE and not settings.USE_GROQ_RAG_ANSWER:
        final_answer = _extractive_answer(question, top_chunks)
        answer_source = "extractive"
    else:
        final_answer, answer_source = generate_answer_from_context(
            question,
            context,
            top_score=top_score,
        )

    sources = [
        {
            "text": (c["text"][:280] + "…") if len(c["text"]) > 280 else c["text"],
            "score": round(float(c["score"]), 4),
        }
        for c in top_chunks
        if c["score"] >= RAG_MIN_SCORE
    ]

    return {
        "success": True,
        "question": question,
        "similarity_score": round(top_score, 4),
        "answer": final_answer,
        "answer_source": top_chunks[0]["text"],
        "sources": sources,
        "answer_mode": answer_source,
        "rag_scope": scope,
        "message": "Answer generated from relevant document sections",
    }
