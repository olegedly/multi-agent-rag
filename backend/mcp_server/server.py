"""FastMCP server exposing corpus-scoped RAG tools.

Provides two tools:
- ``search_corpus`` — semantic search over a single corpus.
- ``read_document`` — retrieve full source context for given chunk IDs.

Dependencies can be injected via :func:`create_mcp_server` for testing.
The module-level ``mcp`` instance is created lazily for standalone use.
"""

from __future__ import annotations

from typing import cast

from mcp.server.fastmcp import FastMCP

from backend.config import get_settings
from backend.db import create_db_sessionmaker
from backend.embeddings.factory import create_embedding_client
from backend.embeddings.protocol import EmbeddingClient
from backend.rag.search import AsyncSessionMaker, read_document as _read_document
from backend.rag.search import search_corpus as _search_corpus


def create_mcp_server(
    embedding_client: EmbeddingClient | None = None,
    sessionmaker: AsyncSessionMaker | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Build and return a configured FastMCP instance.

    Parameters
    ----------
    embedding_client : optional
        Inject a fake/stub for testing. When ``None`` (default) the server
        lazily creates a real client on first tool call.
    sessionmaker : optional
        Inject a fake sessionmaker for testing. When ``None`` (default) the
        server lazily creates one on first tool call.
    host : str
        Bind address for SSE transport (default ``"127.0.0.1"``).
    port : int
        Bind port for SSE transport (default ``8000``).

    Returns
    -------
    FastMCP
        A fully wired MCP server with ``search_corpus`` and
        ``read_document`` tools.
    """
    mcp = FastMCP(
        "RAG Tools",
        instructions="Semantic search and document retrieval over RAG corpora",
        host=host,
        port=port,
    )

    # Capture deps in closures — resolved once on first tool call
    _embedding_client: EmbeddingClient | None = embedding_client
    _sessionmaker: AsyncSessionMaker | None = sessionmaker

    def _ensure_initialised() -> tuple[EmbeddingClient, AsyncSessionMaker]:
        nonlocal _embedding_client, _sessionmaker
        if _embedding_client is None:
            _embedding_client = create_embedding_client()
        if _sessionmaker is None:
            settings = get_settings()
            _sessionmaker = cast(AsyncSessionMaker, create_db_sessionmaker(settings.database_url))
        return _embedding_client, _sessionmaker

    # ── Tools ─────────────────────────────────────────────────────────

    @mcp.tool()
    async def search_corpus(query: str, corpus_id: str, top_k: int = 5) -> dict:
        """Semantic search over a single corpus.

        Embeds *query*, then finds the *top_k* most similar chunks in the
        corpus identified by *corpus_id* using cosine similarity.

        Args:
            query: Natural-language search query.
            corpus_id: UUID of the corpus to search.
            top_k: Number of results to return (default 5).

        Returns:
            A dict with ``results`` (list of ``SearchResult`` dicts) or
            ``error`` plus ``results`` on failure.
        """
        ec, sm = _ensure_initialised()
        try:
            results = await _search_corpus(
                query=query,
                corpus_id=corpus_id,
                top_k=top_k,
                embedding_client=ec,
                sessionmaker=sm,
            )
            return {
                "results": [r.model_dump() for r in results],
                "error": None,
            }
        except Exception as exc:
            return {
                "results": [],
                "error": str(exc),
            }

    @mcp.tool()
    async def read_document(chunk_ids: list[int], corpus_id: str) -> dict:
        """Retrieve full source context for given chunk IDs.

        Given one or more chunk IDs, returns **all** chunks from the same
        source file(s) within the specified corpus.

        Args:
            chunk_ids: One or more chunk IDs to look up.
            corpus_id: UUID of the corpus the chunks belong to.

        Returns:
            A dict with ``results`` (list of ``SearchResult`` dicts) or
            ``error`` plus ``results`` on failure.
        """
        _ec, sm = _ensure_initialised()
        try:
            results = await _read_document(
                chunk_ids=chunk_ids,
                corpus_id=corpus_id,
                sessionmaker=sm,
            )
            return {
                "results": [r.model_dump() for r in results],
                "error": None,
            }
        except Exception as exc:
            return {
                "results": [],
                "error": str(exc),
            }

    return mcp


# Module-level instance for standalone use (``python -m backend.mcp_server``).
# Created lazily so importing the module doesn't trigger env-var reads.
_mcp: FastMCP | None = None


def __getattr__(name: str) -> FastMCP:
    """Lazy-init ``mcp`` for backward-compatible imports.

    ``from backend.mcp_server.server import mcp`` triggers this on
    first access.  Tests should use ``create_mcp_server(...)`` instead.
    """
    if name == "mcp":
        global _mcp
        if _mcp is None:
            _mcp = create_mcp_server()
        return _mcp
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
