"""Config-driven embedding client factory.

Reads ``EMBEDDING_MODEL``, ``EMBEDDING_API_KEY``, ``EMBEDDING_BASE_URL``,
and ``EMBEDDING_DIMENSIONS`` from :class:`Settings` and returns the
configured :class:`OpenRouterEmbeddingClient`.

Mirrors the LLM client factory pattern.
"""

from backend.config import get_settings
from backend.embeddings.openai import OpenRouterEmbeddingClient
from backend.embeddings.protocol import EmbeddingClient

settings = get_settings()


def create_embedding_client() -> EmbeddingClient:
    """Create an embedding client from environment configuration.

    Returns
    -------
    EmbeddingClient
        A configured embedding client instance.

    Raises
    ------
    ValueError
        If ``EMBEDDING_MODEL`` is not set.
    """
    if not settings.embedding_model:
        raise ValueError(
            "EMBEDDING_MODEL is not set. "
            "Set EMBEDDING_MODEL, EMBEDDING_API_KEY, EMBEDDING_BASE_URL, "
            "and EMBEDDING_DIMENSIONS in your .env or environment."
        )

    return OpenRouterEmbeddingClient(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions or 768,
    )
