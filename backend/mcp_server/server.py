"""FastMCP server exposing corpus-scoped RAG tools.

Provides two tools:
- ``search_corpus`` — semantic search over a single corpus.
- ``read_document`` — retrieve full source context for given chunk IDs.

Both tools lazily init their DB and embedding config on first call,
reading from the project's ``.env`` via ``get_settings()``.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from backend.config import get_settings
from backend.db import create_db_sessionmaker
from backend.embeddings.factory import create_embedding_client
from backend.embeddings.protocol import EmbeddingClient
from backend.rag.search import read_document as _read_document
from backend.rag.search import search_corpus as _search_corpus

mcp = FastMCP("RAG Tools", instructions="Semantic search and document retrieval over RAG corpora")

# Lazy initialisers — set at module level so tests can replace them.
_embedding_client: EmbeddingClient | None = None
_sessionmaker: Any = None


def _ensure_initialised() -> None:
    """Create embedding client and sessionmaker on first use."""
    global _embedding_client, _sessionmaker
    if _embedding_client is None:
        _embedding_client = create_embedding_client()
    if _sessionmaker is None:
        settings = get_settings()
        _sessionmaker = create_db_sessionmaker(settings.database_url)


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
async def search_corpus(query: str, corpus_id: str, top_k: int = 5) -> dict:
    """Semantic search over a single corpus.

    Embeds *query*, then finds the *top_k* most similar chunks in the
    corpus identified by *corpus_id* using cosine similarity.

    Args:
        query: Natural-language search query.
        corpus_id: UUID of the corpus to search (e.g. ``315e41aa-8657-46c0-ac4b-ea4355babf0a``).
        top_k: Number of results to return (default 5).

    Returns:
        A dict with ``results`` (list of ``SearchResult`` dicts) or
        ``error`` plus ``results`` on failure.
    """
    _ensure_initialised()
    assert _embedding_client is not None and _sessionmaker is not None
    try:
        results = await _search_corpus(
            query=query,
            corpus_id=corpus_id,
            top_k=top_k,
            embedding_client=_embedding_client,
            sessionmaker=_sessionmaker,
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
    source file(s) within the specified corpus.  Use this after a
    ``search_corpus`` hit to expand to the full document context.

    Args:
        chunk_ids: One or more chunk IDs to look up.
        corpus_id: UUID of the corpus the chunks belong to.

    Returns:
        A dict with ``results`` (list of ``SearchResult`` dicts) or
        ``error`` plus ``results`` on failure.
    """
    _ensure_initialised()
    assert _sessionmaker is not None
    try:
        results = await _read_document(
            chunk_ids=chunk_ids,
            corpus_id=corpus_id,
            sessionmaker=_sessionmaker,
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
