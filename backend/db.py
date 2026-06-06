"""Database engine and session factory for multi-agent-rag.

Use ``create_db_sessionmaker(database_url)`` to create a sessionmaker
lazily instead of at import time. The module-level ``get_db`` helper and
``init_db`` helper remain available for FastAPI dependency injection.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def create_db_sessionmaker(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Create an async SQLAlchemy sessionmaker bound to *database_url*.

    Call once during application startup (e.g. from ``create_app()``)
    and pass the result to FastAPI dependencies.
    """
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )


async def get_db(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-compatible dependency that yields a session from *sessionmaker*."""
    async with sessionmaker() as session:
        yield session


async def init_db(database_url: str) -> None:
    """Initialize the database: create the pgvector extension."""
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await engine.dispose()
