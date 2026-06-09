"""ADK RAG tool functions — wired via ``FunctionTool``, not through MCP.

Provides two async functions (``rag_search``, ``rag_read_document``) that
read ``corpusId`` from ``tool_context.state`` (auto-injected by ADK) and
call ``backend/rag/search.py`` — the same functions the MCP server uses.

Use the :func:`make_rag_tools` factory to inject dependencies for testing.
When *sessionmaker* or *embedding_client* are omitted they are created
lazily on first tool call (matching the ``create_mcp_server`` pattern).
"""

from __future__ import annotations

import logging
from typing import Any, cast

from google.adk.tools.tool_context import ToolContext

log = logging.getLogger(__name__)

from backend.db import create_db_sessionmaker
from backend.embeddings.factory import create_embedding_client
from backend.embeddings.protocol import EmbeddingClient
from backend.rag.search import AsyncSessionMaker
from backend.rag.search import read_document as _read_document
from backend.rag.search import search_corpus as _search_corpus

# Re-export for convenience
__all__ = ["make_rag_tools"]


def make_rag_tools(
    sessionmaker: AsyncSessionMaker | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> tuple[Any, Any]:
    """Build and return a pair of ADK-compatible RAG tool functions.

    Parameters
    ----------
    sessionmaker : optional
        Inject a fake sessionmaker for testing. When ``None`` (default) the
        tools lazily create a real one on first call.
    embedding_client : optional
        Inject a fake embedding client for testing. When ``None`` (default)
        the tools lazily create a real one on first call.

    Returns
    -------
    tuple[Callable, Callable]
        ``(rag_search, rag_read_document)`` — two async functions whose
        ``tool_context`` parameter is auto-detected and stripped from the
        LLM declaration by ADK's ``FunctionTool``.
    """
    _sessionmaker: AsyncSessionMaker | None = sessionmaker
    _embedding_client: EmbeddingClient | None = embedding_client

    def _ensure_initialised() -> tuple[EmbeddingClient, AsyncSessionMaker]:
        nonlocal _embedding_client, _sessionmaker
        if _embedding_client is None:
            _embedding_client = create_embedding_client()
        if _sessionmaker is None:
            from backend.config import get_settings

            settings = get_settings()
            # cast: SQLAlchemy's ``async_sessionmaker`` is structurally
            # compatible with our ``AsyncSessionMaker`` protocol, but
            # pyright rejects it due to ``**kw`` vs ``**kwargs`` naming.
            _sessionmaker = cast(AsyncSessionMaker, create_db_sessionmaker(settings.database_url))
        return _embedding_client, _sessionmaker  # pyright: ignore[reportReturnType]

    async def rag_search(
        query: str,
        top_k: int = 5,
        tool_context: ToolContext | None = None,
    ) -> dict:
        """Semantic search over the active corpus.

        Reads ``corpusId`` from ``tool_context.state`` — this is set
        per-conversation by the frontend and is invisible to the LLM.

        Args:
            query: Natural-language search query.
            top_k: Number of results to return (default 5).
            tool_context: Auto-injected by ADK ``FunctionTool``.

        Returns:
            A dict with ``results`` (list of ``SearchResult`` dicts) and
            ``error`` (``None`` on success, error string on failure).
        """
        corpus_id = None
        if tool_context is not None:
            log.warning(f"rag_search: tool_context.state = {tool_context.state!r}")
            corpus_id = tool_context.state.get("corpusId")
        else:
            log.warning("rag_search: tool_context is None!")
        log.warning(f"rag_search: corpus_id = {corpus_id!r}")
        if not corpus_id:
            return {
                "results": [],
                "error": "No active corpus — start a conversation from a knowledge base route",
            }

        ec, sm = _ensure_initialised()
        try:
            results = await _search_corpus(
                query=query,
                corpus_id=corpus_id,
                top_k=top_k,
                embedding_client=ec,
                sessionmaker=sm,
            )
            return {"results": [r.model_dump() for r in results], "error": None}
        except Exception as exc:
            return {"results": [], "error": str(exc)}

    async def rag_read_document(
        chunk_ids: list[int],
        tool_context: ToolContext | None = None,
    ) -> dict:
        """Retrieve full source context for given chunk IDs.

        Reads ``corpusId`` from ``tool_context.state``. Returns all chunks
        from the same source file(s) as the given chunk IDs.

        Args:
            chunk_ids: One or more chunk IDs to look up.
            tool_context: Auto-injected by ADK ``FunctionTool``.

        Returns:
            A dict with ``results`` (list of ``SearchResult`` dicts) and
            ``error`` (``None`` on success, error string on failure).
        """
        corpus_id = None
        if tool_context is not None:
            corpus_id = tool_context.state.get("corpusId")
        if not corpus_id:
            return {
                "results": [],
                "error": "No active corpus — start a conversation from a knowledge base route",
            }

        _ec, sm = _ensure_initialised()
        try:
            results = await _read_document(
                chunk_ids=chunk_ids,
                corpus_id=corpus_id,
                sessionmaker=sm,
            )
            return {"results": [r.model_dump() for r in results], "error": None}
        except Exception as exc:
            return {"results": [], "error": str(exc)}

    return rag_search, rag_read_document
