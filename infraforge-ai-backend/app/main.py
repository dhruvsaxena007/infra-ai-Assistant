import time
import uuid
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chatbot
from app.api.routes import health
from app.api.routes import machines
from app.api.routes import voice
from app.api.routes import image_search
from app.api.routes import rag
from app.api.routes import assistant
from app.api.routes import support
from app.ai.clip_image_classifier import warmup_clip_background
from app.ai.embedding_service import warmup_embeddings_background
from app.ai.rag_service import hydrate_rag_from_mongo
from app.ai.yolo_classification_service import warmup_yolo_background
from app.core.config import settings
from app.database.mongodb import database
from app.database.persistent_store import ensure_session_indexes, warm_session_cache_async
from app.utils.response import success_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.WARMUP_EMBEDDING_ON_STARTUP:
        warmup_embeddings_background()
        warmup_clip_background()
    warmup_yolo_background()
    try:
        ensure_session_indexes()
        rag_n = await hydrate_rag_from_mongo(database)
        if rag_n:
            print(f"[rag] Loaded {rag_n} persisted chunks from MongoDB")
        n = await warm_session_cache_async(database)
        print(f"[sessions] Warmed {n} assistant sessions from MongoDB")
    except Exception as exc:
        print(f"[persist] Startup hydrate skipped: {exc}")
    yield


app = FastAPI(
    title="Infra AI-Assistant for Marketplace",
    version="1.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — localhost for dev; set CORS_ORIGINS on deploy (comma-separated URLs).
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = f"REQ-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    print(f"[{request_id}] Started {request.method} {request.url.path}")

    try:
        response = await call_next(request)
        process_time = round(time.time() - start_time, 4)
        response.headers["X-Request-ID"] = request_id
        print(
            f"[{request_id}] Completed {request.method} {request.url.path} "
            f"with {response.status_code} in {process_time}s"
        )
        return response

    except Exception as e:
        process_time = round(time.time() - start_time, 4)
        print(
            f"[{request_id}] ERROR {request.method} {request.url.path} "
            f"in {process_time}s"
        )
        print(traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "data": {},
                "error": {
                    "request_id": request_id,
                    "details": str(e),
                },
            },
            headers={"X-Request-ID": request_id},
        )


app.include_router(health.router)
app.include_router(machines.router)
app.include_router(chatbot.router)
app.include_router(voice.router)
app.include_router(image_search.router)
app.include_router(rag.router)
app.include_router(assistant.router)
app.include_router(support.router)


@app.get("/")
async def root():
    return success_response(
        message="AI Marketplace Assistant Running",
        data={
            "project": "Infra AI-Assistant for Marketplace",
            "version": "1.1.0",
            "optimization": "local-first",
            "docs": "/docs",
        },
    )
