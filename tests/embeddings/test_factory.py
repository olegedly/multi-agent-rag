"""Tests for the config-driven embedding client factory.

Mirrors the LLM factory test pattern.
"""

import pytest

from backend.embeddings import factory as factory_mod
from backend.embeddings.openai import OpenRouterEmbeddingClient
from backend.embeddings.protocol import EmbeddingClient


_ORIGINAL_FACTORY = factory_mod.create_embedding_client


@pytest.fixture(autouse=True)
def _restore_factory():
    """Restore the original factory before and after each test."""
    factory_mod.create_embedding_client = _ORIGINAL_FACTORY
    yield
    factory_mod.create_embedding_client = _ORIGINAL_FACTORY


@pytest.fixture
def with_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(factory_mod.settings, "embedding_model", "qwen/qwen3-embedding-768")
    monkeypatch.setattr(factory_mod.settings, "embedding_api_key", "sk-test")
    monkeypatch.setattr(factory_mod.settings, "embedding_base_url", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(factory_mod.settings, "embedding_dimensions", 768)


class TestCreateEmbeddingClient:
    def test_returns_openrouter_client(self, with_env) -> None:
        client = _ORIGINAL_FACTORY()
        assert isinstance(client, OpenRouterEmbeddingClient)
        assert client.model == "qwen/qwen3-embedding-768"
        assert client.api_key == "sk-test"
        assert client.base_url == "https://openrouter.ai/api/v1"
        assert client.dimensions == 768

    def test_satisfies_protocol(self, with_env) -> None:
        client = _ORIGINAL_FACTORY()
        assert isinstance(client, EmbeddingClient)

    def test_raises_on_incomplete_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing required settings raises ValueError."""
        monkeypatch.setattr(factory_mod.settings, "embedding_model", "")

        with pytest.raises(ValueError, match="EMBEDDING_MODEL"):
            _ORIGINAL_FACTORY()
