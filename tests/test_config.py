"""Tests for Pydantic Settings / config module."""

import os

from backend.config import Settings


class TestSettingsDefaults:
    def test_default_app_name(self) -> None:
        s = Settings(_env_file=None)
        assert s.app_name == "multi-agent-rag"

    def test_llm_defaults_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER_TYPE", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.llm_provider_type == ""
        assert s.llm_model == ""
        assert s.llm_api_key == ""
        assert s.llm_base_url == ""

    def test_postgres_defaults(self, monkeypatch) -> None:
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_PORT", raising=False)
        s = Settings(_env_file=None)
        assert s.postgres_host == "localhost"
        assert s.postgres_port == 5432


class TestSettingsEnvOverride:
    def test_database_url_property(self) -> None:
        s = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="rag",
            postgres_host="db.example.com",
            postgres_port=7432,
        )
        expected = "postgresql+asyncpg://u:p@db.example.com:7432/rag"
        assert s.database_url == expected

    def test_overrides_from_kwargs(self) -> None:
        s = Settings(llm_provider_type="anthropic", llm_model="claude-3")
        assert s.llm_provider_type == "anthropic"
        assert s.llm_model == "claude-3"


class TestSettingsEnvFile:
    def test_ignores_extra_keys(self) -> None:
        """SettingsConfigDict(extra='ignore') discards unknown env vars."""
        s = Settings(_extra={"UNRELATED": "should-be-ignored"})
        # Should not raise, and unrelated keys are silently dropped
        assert s.app_name == "multi-agent-rag"
