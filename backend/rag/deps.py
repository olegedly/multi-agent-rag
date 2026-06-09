"""Shared lazily-initialised RAG dependencies.

Both ``backend/agents/langchain_tools.py`` and
``backend/mcp_server/server.py`` need the same pattern: accept optional
``embedding_client`` and ``sessionmaker``, then lazily create real ones
on first tool call.  This module provides the common implementation.
"""

from __future__ import annotations

from typing import Callable, cast

from backend.config import get_settings
from backend.db import create_db_sessionmaker
from backend.embeddings.factory import create_embedding_client
from backend.embeddings.protocol import EmbeddingClient
from backend.rag.search import AsyncSessionMaker


RagDepsFactory = Callable[[], tuple[EmbeddingClient, AsyncSessionMaker]]
"""Type of the callable returned by :func:`make_rag_deps`."""


def make_rag_deps(
    embedding_client: EmbeddingClient | None = None,
    sessionmaker: AsyncSessionMaker | None = None,
) -> RagDepsFactory:
    """Return a ``_ensure_initialised``-style callable for RAG dependencies.

    The returned zero-arg callable lazily initialises any ``None``
    dependencies on first invocation and caches them via closure
    mutation.  Subsequent calls are a no-op fast path.

    Parameters
    ----------
    embedding_client : optional
        Inject a fake/stub for testing.
    sessionmaker : optional
        Inject a fake sessionmaker for testing.

    Returns
    -------
    Callable[[], tuple[EmbeddingClient, AsyncSessionMaker]]
        ``fn()`` that returns the resolved (embedding_client, sessionmaker).
    """
    _embedding_client: EmbeddingClient | None = embedding_client
    _sessionmaker: AsyncSessionMaker | None = sessionmaker

    def _ensure_initialised() -> tuple[EmbeddingClient, AsyncSessionMaker]:
        nonlocal _embedding_client, _sessionmaker
        if _embedding_client is None:
            _embedding_client = create_embedding_client()
        if _sessionmaker is None:
            settings = get_settings()
            _sessionmaker = cast(
                AsyncSessionMaker, create_db_sessionmaker(settings.database_url)
            )
        return _embedding_client, _sessionmaker

    return _ensure_initialised
