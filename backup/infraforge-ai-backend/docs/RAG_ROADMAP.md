# RAG Roadmap — InfraForge AI Backend

## Current (NOW)

| Component | Implementation |
|-----------|----------------|
| PDF text | `pypdf` via `pdf_service.py` |
| Chunking | Fixed 500-char windows, in-memory list |
| Embeddings | **Shared** `embedding_service` (single SentenceTransformer) |
| Similarity | **NumPy** `vector_math.cosine_similarity` |
| Retrieval | **Top-3** chunks, min score `0.2` |
| Answer | Groq `llama-3.3-70b-versatile`, temperature 0, context-only rules |
| Storage | In-process `document_chunks` (lost on restart) |

Endpoints unchanged:

- `POST /rag/upload-text`
- PDF upload route
- `POST /rag/ask`

## Optimizations applied

- Removed duplicate SentenceTransformer in `rag_service.py`
- Removed scikit-learn dependency
- Top-K retrieval reduces missed context vs single-chunk

## Future (requires approval)

### Mongo-backed RAG chunks

```text
Collection: rag_documents
  - document_id, chunk_text, embedding[], source, uploaded_at
```

Benefits: survives restarts, multi-document, audit trail.

### MongoDB Atlas Vector Search

- Index on `embedding` field
- `$vectorSearch` in aggregation for scalable retrieval
- Requires Atlas tier + index definition

### Redis cache

- Hot cache for last N questions per session
- Optional embedding cache for frequent PDFs

### Persistent vector DB

- Pinecone/Qdrant/Weaviate — **only if** Atlas Vector Search is insufficient
- Prefer Mongo-native vector search first (no new paid vendor)

## Hallucination controls (current)

- Answer prompt: "ONLY the context below"
- Low similarity → no answer
- Empty PDF text → `chunks_added: 0` message

## Not in scope now

- Paid embedding APIs (OpenAI embeddings, Cohere, etc.)
