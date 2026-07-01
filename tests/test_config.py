"""Tests for Pydantic Settings / config module."""

from backend.config import Settings


class TestSettingsDefaults:
    def test_default_app_name(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.app_name == "multi-agent-rag"

    def test_llm_defaults_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.llm_model == ""
        assert s.llm_api_key == ""
        assert s.llm_base_url == ""

    def test_postgres_defaults(self, monkeypatch) -> None:
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_PORT", raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
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
        s = Settings(llm_model="gpt-4o")
        assert s.llm_model == "gpt-4o"


class TestDemoBudgetDefaults:
    def test_daily_budget_default(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.demo_daily_budget_tokens == 1_000_000

    def test_budget_file_default(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.demo_budget_file == "/data/demo-budget.json"

    def test_max_query_length_default(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.demo_max_query_length == 500

    def test_max_user_messages_default(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.demo_max_user_messages == 50


    def test_budget_store_disabled_when_demo_disable_budget(self) -> None:
        """budget_store is None when demo_disable_budget=True."""
        s = Settings(_env_file=None, demo_disable_budget=True)  # type: ignore[call-arg]
        assert s.budget_store is None

    def test_budget_store_returns_budget_store_instance(self, tmp_path) -> None:
        """budget_store returns a BudgetStore instance when enabled."""
        from backend.middleware import BudgetStore
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            demo_disable_budget=False,
            demo_daily_budget_tokens=100,
            demo_budget_file=str(tmp_path / "demo-budget.json"),
        )
        store = s.budget_store
        assert store is not None
        assert isinstance(store, BudgetStore)
        assert store.daily_limit == 100
class TestSettingsEnvFile:
    def test_ignores_extra_keys(self) -> None:
        """SettingsConfigDict(extra='ignore') discards unknown env vars."""
        s = Settings(_extra={"UNRELATED": "should-be-ignored"})  # type: ignore[call-arg]
        # Should not raise, and unrelated keys are silently dropped
        assert s.app_name == "multi-agent-rag"
