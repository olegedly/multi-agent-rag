"""Config-driven LLM client factory."""

from backend.config import settings
from backend.llm.anthropic import AnthropicClient
from backend.llm.openai import OpenAIClient
from backend.llm.protocol import LLMClient


def create_llm_client() -> LLMClient:
    """Create an LLM client from Settings / environment variables.

    Required env vars (in .env):
        LLM_PROVIDER  — "anthropic" or "openai"
        LLM_MODEL     — model name (e.g. "deepseek-chat", "gpt-4o")
        LLM_API_KEY   — API key
        LLM_BASE_URL  — base URL for the API
        LLM_MAX_TOKENS — optional, default 4096
    """
    provider = settings.llm_provider
    model = settings.llm_model
    api_key = settings.llm_api_key
    base_url = settings.llm_base_url
    max_tokens = settings.llm_max_tokens

    if provider == "anthropic":
        return AnthropicClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    elif provider == "openai":
        return OpenAIClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}. Expected 'anthropic' or 'openai'.")
