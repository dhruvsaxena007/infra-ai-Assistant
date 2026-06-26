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
    OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip() or None
    OPENAI_CHAT_MODEL = (os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini").strip()
    OPENAI_VISION_MODEL = (os.getenv("OPENAI_VISION_MODEL") or "gpt-4o-mini").strip()
    OPENAI_WHISPER_MODEL = (os.getenv("OPENAI_WHISPER_MODEL") or "whisper-1").strip()
    USE_OPENAI_VISION = os.getenv("USE_OPENAI_VISION", "false").lower() in (
        "1", "true", "yes",
    )

    # Primary AI routing — Groq/local default; OpenAI optional and off by default.
    AI_PROVIDER = (os.getenv("AI_PROVIDER") or "groq").strip().lower()
    ENABLE_OPENAI = os.getenv("ENABLE_OPENAI", "false").lower() in (
        "1", "true", "yes"
    )
    # llm_first = Groq/OpenAI intent classifier primary; rules = fast-path/fallback only
    AI_INTENT_MODE = (os.getenv("AI_INTENT_MODE") or "rules_first").strip().lower()
    INTENT_CACHE_TTL_SECONDS = int(os.getenv("INTENT_CACHE_TTL_SECONDS", "120"))
    # Post-tool response polish only (finalize_assistant_reply / dynamic_response).
    # Does not affect intent routing, search execution, or tool permissions.
    USE_LLM_RESPONSE_GENERATION = os.getenv(
        "USE_LLM_RESPONSE_GENERATION", "true"
    ).lower() in ("1", "true", "yes")
    # Structured per-request JSON trace for /chat (logs only; no response shape change)
    ASSISTANT_DEBUG = os.getenv("ASSISTANT_DEBUG", "false").lower() in (
        "1", "true", "yes",
    )

    # Primary MongoDB settings. The project's .env uses MONGODB_URL /
    # DATABASE_NAME, so those are read first. MONGO_URI / MONGO_DB_NAME are
    # kept as backward-compatible fallbacks.
    MONGODB_URL = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI")
    DATABASE_NAME = os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB_NAME")

    # Aliases (do not remove) — existing code / docs may reference these names.
    MONGO_URI = MONGODB_URL
    MONGO_DB_NAME = DATABASE_NAME

    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # Comma-separated production frontend URLs for CORS (e.g. https://app.vercel.app).
    CORS_ORIGINS = (os.getenv("CORS_ORIGINS") or "").strip()
    CORS_ORIGIN_REGEX = (os.getenv("CORS_ORIGIN_REGEX") or "").strip()

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
    AUDIO_UPLOAD_DIR = os.getenv("AUDIO_UPLOAD_DIR", "uploads/audio")

    # Voice Phase V1 — reliability, security, text-chat parity
    VOICE_PIPELINE_V2 = os.getenv("VOICE_PIPELINE_V2", "false").lower() in (
        "1", "true", "yes",
    )
    VOICE_MAX_FILE_SIZE_MB = int(os.getenv("VOICE_MAX_FILE_SIZE_MB", "10"))
    VOICE_MAX_DURATION_SECONDS = int(os.getenv("VOICE_MAX_DURATION_SECONDS", "120"))
    VOICE_STT_TIMEOUT_SECONDS = float(os.getenv("VOICE_STT_TIMEOUT_SECONDS", "45"))
    VOICE_MAX_CONCURRENT_TRANSCRIPTIONS = int(
        os.getenv("VOICE_MAX_CONCURRENT_TRANSCRIPTIONS", "3")
    )
    # Optional ISO-639-1 hint (e.g. en, hi). Empty = Whisper auto-detect.
    VOICE_STT_LANGUAGE_HINT = (os.getenv("VOICE_STT_LANGUAGE_HINT") or "").strip() or None
    IMAGE_SEARCH_UPLOAD_DIR = os.getenv(
        "IMAGE_SEARCH_UPLOAD_DIR",
        "uploads/image_search"
    )
    IMAGE_SEARCH_MAX_FILE_SIZE_MB = int(os.getenv("IMAGE_SEARCH_MAX_FILE_SIZE_MB", "8"))
    IMAGE_SEARCH_MAX_DIMENSION = int(os.getenv("IMAGE_SEARCH_MAX_DIMENSION", "1600"))
    IMAGE_SEARCH_TEMP_CLEANUP = os.getenv("IMAGE_SEARCH_TEMP_CLEANUP", "true").lower() in (
        "1", "true", "yes",
    )
    IMAGE_SEARCH_CONFIDENCE_THRESHOLD = float(
        os.getenv("IMAGE_SEARCH_CONFIDENCE_THRESHOLD", "0.35")
    )
    IMAGE_SEARCH_REQUIRE_CLARIFICATION_FOR_UNCLEAR_INTENT = os.getenv(
        "IMAGE_SEARCH_REQUIRE_CLARIFICATION_FOR_UNCLEAR_INTENT", "true"
    ).lower() in ("1", "true", "yes")
    IMAGE_CONTEXT_TTL_SECONDS = int(os.getenv("IMAGE_CONTEXT_TTL_SECONDS", "1800"))
    IMAGE_SEARCH_LIMIT_PER_SESSION = int(os.getenv("IMAGE_SEARCH_LIMIT_PER_SESSION", "3"))
    VOICE_MESSAGE_LIMIT_PER_SESSION = int(os.getenv("VOICE_MESSAGE_LIMIT_PER_SESSION", "5"))
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
    USE_GROQ_MESSAGE_NORMALIZER = os.getenv(
        "USE_GROQ_MESSAGE_NORMALIZER", "false"
    ).lower() in ("1", "true", "yes")
    # auto = on when GROQ_API_KEY exists (universal understanding for ANY phrasing)
    _GROQ_UNIVERSAL_RAW = (os.getenv("USE_GROQ_UNIVERSAL_CLASSIFIER") or "auto").strip().lower()
    GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
    DISABLE_GROQ_SEMANTIC = os.getenv("DISABLE_GROQ_SEMANTIC", "false").lower() in (
        "1", "true", "yes",
    )
    # Preload embeddings in a background thread so first /chat search is fast.
    # Set false on Render free tier (512MB RAM) to avoid OOM at startup.
    WARMUP_EMBEDDING_ON_STARTUP = os.getenv(
        "WARMUP_EMBEDDING_ON_STARTUP", "true"
    ).lower() in ("1", "true", "yes")

    # auto = enable on Render (RENDER=true) and other low-RAM hosts unless overridden.
    LOW_MEMORY_MODE = (os.getenv("LOW_MEMORY_MODE") or "auto").strip().lower()
    SESSION_CACHE_WARMUP_LIMIT = int(os.getenv("SESSION_CACHE_WARMUP_LIMIT", "500"))

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

    @property
    def cors_origin_regex(self) -> str | None:
        """On Render, allow all Vercel preview/production URLs unless overridden."""
        if self.CORS_ORIGIN_REGEX:
            return self.CORS_ORIGIN_REGEX
        if os.getenv("RENDER") == "true":
            return r"https://.*\.vercel\.app"
        return None

    @property
    def low_memory_deploy(self) -> bool:
        """True on Render free tier and when LOW_MEMORY_MODE is forced on."""
        if self.LOW_MEMORY_MODE in ("1", "true", "yes", "on"):
            return True
        if self.LOW_MEMORY_MODE in ("0", "false", "no", "off"):
            return False
        # Render sets RENDER=true automatically on their platform.
        return os.getenv("RENDER") == "true"

    @property
    def session_cache_warmup_limit(self) -> int:
        if self.low_memory_deploy:
            return min(self.SESSION_CACHE_WARMUP_LIMIT, 50)
        return self.SESSION_CACHE_WARMUP_LIMIT

    @property
    def cors_origins(self) -> list[str]:
        """Local dev origins plus optional CORS_ORIGINS from env (deploy)."""
        origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
        if self.CORS_ORIGINS:
            for raw in self.CORS_ORIGINS.split(","):
                origin = raw.strip().rstrip("/")
                if origin and origin not in origins:
                    origins.append(origin)
        return origins

    @property
    def openai_usable(self) -> bool:
        """True only when OpenAI is explicitly enabled with a key and provider=openai."""
        return (
            self.ENABLE_OPENAI
            and self.AI_PROVIDER == "openai"
            and bool(self.OPENAI_API_KEY)
        )

    @property
    def openai_intent_enabled(self) -> bool:
        """OpenAI intent parser — requires both feature flag and provider enablement."""
        return self.openai_usable and self.USE_OPENAI_INTENT_PARSER

    @property
    def groq_universal_enabled(self) -> bool:
        """
        Semantic turn classifier for ANY phrasing (not example regex).
        auto (default): enabled when provider key exists.
        """
        if self.DISABLE_GROQ_SEMANTIC:
            return False
        if self._GROQ_UNIVERSAL_RAW in ("0", "false", "no", "off"):
            return False
        if self._GROQ_UNIVERSAL_RAW in ("1", "true", "yes", "on"):
            return bool(self.GROQ_API_KEY or self.openai_usable)
        # auto
        if self.openai_usable:
            return True
        return bool(self.GROQ_API_KEY) and self.AI_PROVIDER in ("groq", "local", "")

    @property
    def llm_intent_first(self) -> bool:
        """True when LLM is the primary intent understanding layer."""
        return self.AI_INTENT_MODE in ("llm_first", "llm-first", "llm")

    @property
    def llm_shadow(self) -> bool:
        """Shadow mode: call LLM classifier but route using rules; log comparison only."""
        return self.AI_INTENT_MODE in ("llm_shadow", "shadow")

    @property
    def use_llm_response_generation(self) -> bool:
        return self.USE_LLM_RESPONSE_GENERATION and bool(self.GROQ_API_KEY or self.openai_usable)

    # Phase 12 — Domain Intelligence Gateway rollout
    DOMAIN_INTELLIGENCE_MODE = (os.getenv("DOMAIN_INTELLIGENCE_MODE") or "hybrid").strip().lower()
    DOMAIN_INTELLIGENCE_USE_LLM = os.getenv(
        "DOMAIN_INTELLIGENCE_USE_LLM", "false"
    ).lower() in ("1", "true", "yes")
    DOMAIN_INTELLIGENCE_CONFIDENCE_MIN = float(
        os.getenv("DOMAIN_INTELLIGENCE_CONFIDENCE_MIN", "0.65")
    )

    @property
    def domain_intelligence_off(self) -> bool:
        return self.DOMAIN_INTELLIGENCE_MODE in ("off", "false", "0", "disabled")

    @property
    def domain_intelligence_shadow(self) -> bool:
        return self.DOMAIN_INTELLIGENCE_MODE in ("shadow",)

    @property
    def domain_intelligence_hybrid(self) -> bool:
        return self.DOMAIN_INTELLIGENCE_MODE in ("hybrid", "guarded")

    @property
    def domain_intelligence_use_llm(self) -> bool:
        return self.DOMAIN_INTELLIGENCE_USE_LLM and bool(self.GROQ_API_KEY or self.openai_usable)


settings = Settings()