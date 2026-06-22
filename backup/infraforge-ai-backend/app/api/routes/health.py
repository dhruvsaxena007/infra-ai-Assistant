from fastapi import APIRouter

from app.ai.embedding_service import is_model_ready
from app.ai.rag_service import document_chunks
from app.ai.yolo_classification_service import resolve_yolo_model_path, yolo_model_available
from app.core.config import settings
from app.database.mongodb import database
from app.database.persistent_store import count_rag_chunks_async
from app.utils.response import success_response, error_response

router = APIRouter()


@router.get("/health")
async def health():
    """Liveness/readiness check. Confirms the API is up and MongoDB reachable."""

    try:
        await database.command("ping")

        return success_response(
            message="Service is healthy",
            data={
                "status": "healthy",
                "database": "connected",
                "ai": {
                    "mode": "local-first",
                    "embedding_model": "ready" if is_model_ready() else "warming_or_lazy",
                    "tensorflow_image": "lazy",
                    "yolo_image": (
                        "ready" if yolo_model_available() else "not_trained"
                    ),
                    "yolo_model_path": resolve_yolo_model_path() or None,
                    "image_classifier_mode": settings.IMAGE_CLASSIFIER,
                    "groq_whisper": bool(settings.GROQ_API_KEY),
                    "persistence": {
                        "rag_chunks_memory": len(document_chunks),
                        "rag_chunks_mongo": await count_rag_chunks_async(database),
                        "sessions": "mongodb_assistant_sessions",
                    },
                    "flags": {
                        "USE_GROQ_TEXT_UNDERSTANDING": settings.USE_GROQ_TEXT_UNDERSTANDING,
                        "USE_GROQ_ADVISOR": settings.USE_GROQ_ADVISOR,
                        "USE_GROQ_RAG_ANSWER": settings.USE_GROQ_RAG_ANSWER,
                        "USE_OPENAI_INTENT_PARSER": settings.USE_OPENAI_INTENT_PARSER,
                        "WARMUP_EMBEDDING_ON_STARTUP": settings.WARMUP_EMBEDDING_ON_STARTUP,
                    },
                },
            },
        )

    except Exception as e:
        return error_response(
            message="Service is unhealthy",
            error={
                "status": "error",
                "database": str(e)
            }
        )
