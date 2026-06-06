"""Tests for the config-driven LLM client factory.

These tests restore the original factory function after patching because
``test_main.py`` replaces it with ``FakeLLMClient`` at module load time.
The fixture ensures isolation regardless of import order.
"""

import pytest

from backend.llm import factory as factory_mod
from backend.llm.anthropic import AnthropicClient
from backend.llm.openai import OpenAIClient
from backend.llm.protocol import LLMClient


# Capture the original before any other test module can patch it
_ORIGINAL_FACTORY = factory_mod.create_llm_client


@pytest.fixture(autouse=True)
def _restore_factory():
    """Restore the original factory before and after each test."""
    factory_mod.create_llm_client = _ORIGINAL_FACTORY
    yield
    factory_mod.create_llm_client = _ORIGINAL_FACTORY


@pytest.fixture
def with_openai_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER_TYPE", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_API_KEY", "sk-openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(factory_mod.settings, "llm_provider_type", "openai")
    monkeypatch.setattr(factory_mod.settings, "llm_model", "gpt-4o")
    monkeypatch.setattr(factory_mod.settings, "llm_api_key", "sk-openai")
    monkeypatch.setattr(factory_mod.settings, "llm_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(factory_mod.settings, "llm_max_tokens", 2048)


@pytest.fixture
def with_anthropic_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER_TYPE", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4")
    monkeypatch.setenv("LLM_API_KEY", "sk-anthropic")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.anthropic.com/v1")
    monkeypatch.setattr(factory_mod.settings, "llm_provider_type", "anthropic")
    monkeypatch.setattr(factory_mod.settings, "llm_model", "claude-sonnet-4")
    monkeypatch.setattr(factory_mod.settings, "llm_api_key", "sk-anthropic")
    monkeypatch.setattr(factory_mod.settings, "llm_base_url", "https://api.anthropic.com/v1")
    monkeypatch.setattr(factory_mod.settings, "llm_max_tokens", 4096)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestCreateLlmClient:
    def test_returns_openai_client(self, with_openai_env) -> None:
        client = _ORIGINAL_FACTORY()
        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4o"
        assert client.base_url == "https://api.openai.com/v1"
        assert client.api_key == "sk-openai"
        assert client.max_tokens == 2048

    def test_returns_anthropic_client(self, with_anthropic_env) -> None:
        client = _ORIGINAL_FACTORY()
        assert isinstance(client, AnthropicClient)
        assert client.model == "claude-sonnet-4"
        assert client.base_url == "https://api.anthropic.com/v1"
        assert client.api_key == "sk-anthropic"
        assert client.max_tokens == 4096

    def test_raises_on_unknown_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(factory_mod.settings, "llm_provider_type", "ollama")

        with pytest.raises(ValueError, match="Unknown LLM provider type"):
            _ORIGINAL_FACTORY()

    def test_returns_llm_client_protocol(self, with_openai_env) -> None:
        """Factory always returns something conforming to the protocol."""
        client = _ORIGINAL_FACTORY()
        assert isinstance(client, LLMClient)
