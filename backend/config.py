from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "multi-agent-rag"

    # Postgres / RAG
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # LLM provider — abstracted behind LLMClient
    llm_provider_type: str = ""  # "anthropic" | "openai"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_max_tokens: int = 4096

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


@lru_cache
def get_settings() -> Settings:
    return Settings(**{})


settings = get_settings()
