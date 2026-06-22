import os

from dotenv import load_dotenv

# Load environment variables from .env as early as possible so that every
# setting below (and any module that imports `settings`) sees the real values
# regardless of import order. load_dotenv() does not override variables that
# are already present in the real environment, so it is safe in production.
load_dotenv()


class Settings:
    PROJECT_NAME = "Infra AI-Assistant for Marketplace"
    PROJECT_VERSION = "1.0.0"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Primary MongoDB settings. The project's .env uses MONGODB_URL /
    # DATABASE_NAME, so those are read first. MONGO_URI / MONGO_DB_NAME are
    # kept as backward-compatible fallbacks.
    MONGODB_URL = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI")
    DATABASE_NAME = os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB_NAME")

    # Aliases (do not remove) — existing code / docs may reference these names.
    MONGO_URI = MONGODB_URL
    MONGO_DB_NAME = DATABASE_NAME

    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
    AUDIO_UPLOAD_DIR = os.getenv("AUDIO_UPLOAD_DIR", "uploads/audio")
    IMAGE_SEARCH_UPLOAD_DIR = os.getenv(
        "IMAGE_SEARCH_UPLOAD_DIR",
        "uploads/image_search"
    )
    RAG_PDF_UPLOAD_DIR = os.getenv(
        "RAG_PDF_UPLOAD_DIR",
        "uploads/rag_pdfs"
    )

    # -------------------------------------------------------------------------
    # AI feature flags (local-first defaults — set "true" only when needed)
    # -------------------------------------------------------------------------
    USE_GROQ_TEXT_UNDERSTANDING = os.getenv(
        "USE_GROQ_TEXT_UNDERSTANDING", "false"
    ).lower() in ("1", "true", "yes")
    USE_GROQ_ADVISOR = os.getenv("USE_GROQ_ADVISOR", "false").lower() in (
        "1", "true", "yes"
    )
    USE_GROQ_RAG_ANSWER = os.getenv("USE_GROQ_RAG_ANSWER", "false").lower() in (
        "1", "true", "yes"
    )
    USE_OPENAI_INTENT_PARSER = os.getenv(
        "USE_OPENAI_INTENT_PARSER", "false"
    ).lower() in ("1", "true", "yes")
    USE_GROQ_INTENT_CLASSIFIER = os.getenv(
        "USE_GROQ_INTENT_CLASSIFIER", "false"
    ).lower() in ("1", "true", "yes")
    # Preload embeddings in a background thread so first /chat search is fast.
    WARMUP_EMBEDDING_ON_STARTUP = os.getenv(
        "WARMUP_EMBEDDING_ON_STARTUP", "true"
    ).lower() in ("1", "true", "yes")

    # Image search: auto = YOLO if weights exist, else MobileNet+OpenCV
    IMAGE_CLASSIFIER = os.getenv("IMAGE_CLASSIFIER", "auto").lower()
    YOLO_MODEL_PATH = os.getenv(
        "YOLO_MODEL_PATH",
        os.path.join("models", "infraforge_yolov8n_cls", "best.pt"),
    )

    # Human handover placeholders (configure in .env for production).
    SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "+91-1800-000-0000")
    SUPPORT_WHATSAPP = os.getenv("SUPPORT_WHATSAPP") or os.getenv(
        "SUPPORT_PHONE", "+91-1800-000-0000"
    )
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@infraforge.in")

    # When broad search exceeds this count, ask user to refine instead of dumping all.
    TOO_MANY_RESULTS_THRESHOLD = int(os.getenv("TOO_MANY_RESULTS_THRESHOLD", "20"))


settings = Settings()