"""LLM factory with multi-provider support.

Providers:
  - ollama:     local models via http://localhost:11434
  - groq:       Groq cloud, native ChatGroq client
  - openrouter: OpenAI-compatible gateway to Claude, GPT-4, Gemini, Llama, etc.
                Uses ChatOpenAI under the hood pointing at openrouter.ai/api/v1.
"""
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _build_ollama(temperature: float) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
        temperature=temperature,
    )


def _build_groq(temperature: float) -> BaseChatModel:
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
            "and add it to your .env file."
        )

    try:
        from langchain_groq import ChatGroq
    except ImportError as e:
        raise RuntimeError(
            "langchain-groq is not installed. Run: pip install langchain-groq"
        ) from e

    return ChatGroq(
        model=settings.groq_chat_model,
        api_key=settings.groq_api_key,
        temperature=temperature,
    )


def _build_openrouter(temperature: float) -> BaseChatModel:
    """OpenRouter speaks the OpenAI API protocol, so we use LangChain's
    ChatOpenAI client with a custom base_url. This gives us access to ~100
    models (Claude, GPT-4, Gemini, Llama variants, Mistral, etc.) through a
    single API key, with per-model pricing handled by OpenRouter.
    """
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Get a key at https://openrouter.ai/keys "
            "and add it to your .env file."
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError(
            "langchain-openai is not installed. Run: pip install langchain-openai"
        ) from e

    # OpenRouter encourages clients to set HTTP-Referer + X-Title headers so
    # they can attribute traffic to your app on their dashboard. Optional.
    default_headers = {}
    if settings.openrouter_site_url:
        default_headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_app_name:
        default_headers["X-Title"] = settings.openrouter_app_name

    return ChatOpenAI(
        model=settings.openrouter_chat_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        default_headers=default_headers or None,
    )


@lru_cache(maxsize=4)
def get_llm(temperature: float | None = None) -> BaseChatModel:
    """Return a chat model bound to the configured provider.

    Cache is keyed on temperature so repeated calls reuse the same client.
    """
    t = settings.llm_temperature if temperature is None else temperature
    provider = settings.llm_provider.lower()

    if provider == "groq":
        log.info("using Groq provider with model=%s", settings.groq_chat_model)
        return _build_groq(t)
    if provider == "ollama":
        log.info("using Ollama provider with model=%s", settings.ollama_chat_model)
        return _build_ollama(t)
    if provider == "openrouter":
        log.info("using OpenRouter provider with model=%s", settings.openrouter_chat_model)
        return _build_openrouter(t)

    raise ValueError(
        f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. "
        f"Use 'ollama', 'groq', or 'openrouter'."
    )


def active_model_name() -> str:
    """Return the model identifier for whichever provider is active."""
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return settings.groq_chat_model
    if provider == "openrouter":
        return settings.openrouter_chat_model
    return settings.ollama_chat_model


def active_provider() -> str:
    return settings.llm_provider.lower()
