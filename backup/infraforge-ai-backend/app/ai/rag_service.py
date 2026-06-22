import re

from app.ai.embedding_service import generate_embedding
from app.core.config import settings
from app.core.groq_client import client
from app.utils.vector_math import cosine_similarity
from app.database.persistent_store import load_rag_chunks_async, persist_rag_chunks

# In-memory cache — hydrated from MongoDB on startup; writes go to Mongo + cache
document_chunks: list[dict] = []
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


async def hydrate_rag_from_mongo(database) -> int:
    """Load persisted RAG chunks into memory on server start."""
    global document_chunks, _rag_hydrated
    if _rag_hydrated:
        return len(document_chunks)
    loaded = await load_rag_chunks_async(database)
    document_chunks = loaded
    _rag_hydrated = True
    return len(document_chunks)


def add_document_to_rag(text: str) -> dict:
    global document_chunks

    chunks = split_text(text)
    if not chunks:
        return {
            "success": False,
            "message": "No text content found in document",
            "chunks_added": 0,
            "total_chunks": len(document_chunks),
        }

    new_items = []
    for chunk in chunks:
        item = {"text": chunk, "embedding": generate_embedding(chunk)}
        new_items.append(item)
        document_chunks.append(item)

    persist_rag_chunks(new_items)

    return {
        "success": True,
        "message": "Document added successfully",
        "chunks_added": len(chunks),
        "total_chunks": len(document_chunks),
        "persisted": True,
    }


def _retrieve_top_chunks(question: str, top_k: int = RAG_TOP_K) -> list[dict]:
    question_embedding = generate_embedding(question)
    scored = []
    for item in document_chunks:
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

    try:
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
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return response.choices[0].message.content.strip(), "groq"
    except Exception as exc:
        return (
            _extractive_answer(question, [{"text": context}]),
            "extractive_fallback",
        )


def ask_rag_question(question: str) -> dict:
    if not document_chunks:
        return {
            "success": False,
            "message": "No document uploaded yet",
        }

    question = (question or "").strip()
    if not question:
        return {
            "success": False,
            "message": "Question is required",
        }

    top_chunks = _retrieve_top_chunks(question)
    if not top_chunks or top_chunks[0]["score"] < RAG_MIN_SCORE:
        return {
            "success": False,
            "message": "Could not find relevant information",
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

    return {
        "success": True,
        "question": question,
        "similarity_score": round(top_score, 4),
        "answer": final_answer,
        "answer_source": top_chunks[0]["text"],
        "answer_mode": answer_source,
        "message": "Answer generated from relevant document sections",
    }
