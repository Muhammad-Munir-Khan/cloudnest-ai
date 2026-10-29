"""Application settings, overridable via environment variables or .env."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

PROJECT_ROOT = Path(__file__).parent.parent.parent

# In production, secrets can be mounted as files at /run/secrets/<field_name>
# (Docker / Kubernetes secrets). pydantic-settings reads them automatically when
# the directory exists. Environment variables and .env still take PRECEDENCE,
# so development is unchanged. We only point at the directory when it actually
# exists, to avoid a noisy startup warning in dev where there are no file
# secrets. To use it in production, mount a secret named after the (lowercase)
# field, e.g. a Docker secret `jwt_secret` -> /run/secrets/jwt_secret feeds the
# `jwt_secret` setting; likewise groq_api_key, openrouter_api_key,
# smtp_password, langfuse_secret_key, database_url, and the oauth client secrets.
_SECRETS_DIR = "/run/secrets" if Path("/run/secrets").is_dir() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        secrets_dir=_SECRETS_DIR,
    )

    data_dir: Path = PROJECT_ROOT / "data"
    llm_provider: str
    llm_temperature: float

    # Ollama
    ollama_chat_model: str
    ollama_base_url: str
    ollama_vision_model: str

    # Groq
    groq_api_key: str | None = None
    groq_chat_model: str
    groq_vision_model: str
    groq_ensemble_models: str
    groq_ensemble_judge_model: str

    # OpenRouter
    openrouter_api_key: str | None = None
    openrouter_chat_model: str
    openrouter_base_url: str
    openrouter_site_url: str | None = None
    openrouter_app_name: str | None = None
    openrouter_vision_model: str
    openrouter_ensemble_models: str
    openrouter_ensemble_judge_model: str

    # Embeddings
    embedding_model: str

    # Retrieval
    chunk_size: int
    chunk_overlap: int
    top_k: int

    # Agent
    max_agent_iterations: int
    memory_window: int

    # Voice - STT
    whisper_model: str
    whisper_compute_type: str
    whisper_language: str | None = None
    enable_voice: bool = True

    # Voice - TTS
    tts_backend: str
    piper_voice: str
    edge_tts_voice: str

    # API
    api_host: str
    api_port: int
    cors_origins: list[str]

    # Observability
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str

    # Tools
    enable_web_search: bool
    enable_calculator: bool
    web_search_max_results: int

    # OAuth
    google_oauth_client_id: str
    google_oauth_client_secret: str
    github_oauth_client_id: str
    github_oauth_client_secret: str

    # URLs
    frontend_url: str
    backend_url: str

    # Ensemble
    ensemble_max_tokens: int
    ensemble_timeout_sec: int

    # Database
    database_url: str

    # Auth
    jwt_secret: str
    jwt_lifetime_seconds: int

    # SMTP
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_from_name: str

    # Weaviate
    weaviate_url: str
    weaviate_grpc_port: int
    weaviate_index_name: str
    # API key for Weaviate. Unset = anonymous access (local dev). Required by
    # the production compose overlay, which disables anonymous access.
    weaviate_api_key: str | None = None

    REDIS_URL : str
    COOKIE_SECURE :bool  # true in production (HTTPS)
    REQUIRE_EMAIL_VERIFICATION :bool # true in production once SMTP works
    SENTRY_DSN : str
    ENVIRONMENT :str
    SENTRY_TRACES_SAMPLE_RATE :float

    # Derived paths
    @property
    def docs_dir(self) -> Path:
        return self.data_dir / "docs"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    # Provider helper
    @property
    def provider(self) -> str:
        return self.llm_provider.lower()

    # Ensemble logic
    @property
    def ensemble_models_list(self) -> list[str]:
        if self.provider == "openrouter":
            raw = self.openrouter_ensemble_models
        elif self.provider == "groq":
            raw = self.groq_ensemble_models
        else:
            return []

        return [m.strip() for m in raw.split(",") if m.strip()]

    @property
    def active_judge_model(self) -> str:
        if self.provider == "openrouter":
            return self.openrouter_ensemble_judge_model
        return self.groq_ensemble_judge_model

    @property
    def active_chat_model(self) -> str:
        if self.provider == "groq":
            return self.groq_chat_model
        if self.provider == "openrouter":
            return self.openrouter_chat_model
        return self.ollama_chat_model

    @property
    def active_vision_model(self) -> str:
        if self.provider == "groq":
            return self.groq_vision_model
        if self.provider == "openrouter":
            return self.openrouter_vision_model
        return self.ollama_vision_model

    # Voice language mapping
    @property
    def edge_tts_voice_by_lang(self) -> dict[str, str]:
        return {
            "en": "en-US-AriaNeural",
            "ur": "ur-PK-UzmaNeural",
            "ar": "ar-EG-SalmaNeural",
            "hi": "hi-IN-SwaraNeural",
            "es": "es-ES-ElviraNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "it": "it-IT-ElsaNeural",
            "pt": "pt-BR-FranciscaNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ja": "ja-JP-NanamiNeural",
            "ko": "ko-KR-SunHiNeural",
            "tr": "tr-TR-EmelNeural",
            "nl": "nl-NL-FennaNeural",
            "pl": "pl-PL-AgnieszkaNeural",
            "sv": "sv-SE-SofieNeural",
            "id": "id-ID-GadisNeural",
            "th": "th-TH-PremwadeeNeural",
            "vi": "vi-VN-HoaiMyNeural",
            "bn": "bn-IN-TanishaaNeural",
            "ta": "ta-IN-PallaviNeural",
            "te": "te-IN-ShrutiNeural",
            "mr": "mr-IN-AarohiNeural",
            "ml": "ml-IN-SobhanaNeural",
            "gu": "gu-IN-DhwaniNeural",
            "kn": "kn-IN-SapnaNeural",
            "fa": "fa-IR-DilaraNeural",
            "he": "he-IL-HilaNeural",
            "el": "el-GR-AthinaNeural",
            "cs": "cs-CZ-VlastaNeural",
            "ro": "ro-RO-AlinaNeural",
            "hu": "hu-HU-NoemiNeural",
            "uk": "uk-UA-PolinaNeural",
            "fil": "fil-PH-BlessicaNeural",
            "ms": "ms-MY-YasminNeural",
            "sw": "sw-TZ-RehemaNeural",
        }

# INIT
settings = Settings()
for d in (settings.docs_dir, settings.audio_dir):
    d.mkdir(parents=True, exist_ok=True)