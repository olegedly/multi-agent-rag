from functools import lru_cache

from typing import Any

from pydantic import PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    _budget_store: object | None = PrivateAttr(default=None)
    app_name: str = "multi-agent-rag"

    # Postgres / RAG
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Embedding provider — abstracted behind EmbeddingClient
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_dimensions: int = 768

    # LLM provider — passed straight to langchain_openai.ChatOpenAI
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_max_tokens: int = 4096

    # Cross-environment copy
    dev_database_url: str = ""
    supabase_direct_url: str = ""

    # Public demo abuse prevention
    demo_disable_budget: bool = False
    demo_daily_budget_tokens: int = 1_000_000
    demo_budget_file: str = "/data/demo-budget.json"
    demo_max_query_length: int = 500
    demo_max_user_messages: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def budget_store(self) -> Any | None:
        """Return a BudgetStore instance, or None if budget is disabled.

        Consumers (ChatGuard, TokenBudgetCallback) share this single
        instance via the Settings object.
        """
        if self.demo_disable_budget:
            return None
        if self._budget_store is None:
            from backend.middleware import JsonFileBudget

            self._budget_store = JsonFileBudget(
                path=self.demo_budget_file,
                daily_limit=self.demo_daily_budget_tokens,
            )
        return self._budget_store


@lru_cache
def get_settings() -> Settings:
    return Settings(**{})


settings = get_settings()
