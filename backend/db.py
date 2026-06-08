"""Database engine, session factory, and migration for multi-agent-rag.

Use ``create_db_sessionmaker(database_url)`` to create a sessionmaker
lazily instead of at import time.

Use ``migrate_db(database_url)`` to run schema migrations (pgvector
extension, table creation, indexes, foreign keys).  This is a single
call that owns its own engine lifecycle — callers don't need to manage
engines themselves.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base


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


async def migrate_db(database_url: str) -> None:
    """Run all schema migrations: pgvector extension, tables, indexes, FK.

    Owns its own engine — creates it, runs migrations, disposes it.
    Call this once at deploy time (e.g. from the seed script).
    """
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            # 1. pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # 2. Create all tables
            await conn.run_sync(Base.metadata.create_all)
            # 3. IVFFlat index for cosine-similarity search
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_documents_embedding "
                "ON documents USING ivfflat (embedding vector_cosine_ops) "
                "WITH (lists = 10)"
            ))
            # 4. FK migration (idempotent — skips if constraint already exists)
            await conn.execute(text(
                "DO $$ BEGIN "
                "ALTER TABLE documents "
                "ADD CONSTRAINT fk_document_source "
                "FOREIGN KEY (corpus_id, source_filename) "
                "REFERENCES document_sources(corpus_id, filename) "
                "ON DELETE CASCADE; "
                "EXCEPTION WHEN duplicate_object THEN NULL; "
                "END $$"
            ))
    finally:
        await engine.dispose()
