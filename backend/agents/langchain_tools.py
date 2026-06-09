"""LangChain RAG tool factory.

Replaces the old ADK ``FunctionTool`` pattern with LangChain ``@tool``
decorators.  ``corpus_id`` is baked into the closure by the factory —
the LLM never sees it.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from typing import cast

from backend.db import create_db_sessionmaker
from backend.embeddings.factory import create_embedding_client
from backend.embeddings.protocol import EmbeddingClient
from backend.rag.search import (
    AsyncSessionMaker,
    read_document as _read_document,
    search_corpus as _search_corpus,
)


def create_rag_tools(
    corpus_id: str,
    sessionmaker: AsyncSessionMaker | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> list[BaseTool]:
    """Build and return LangChain RAG tools with *corpus_id* baked in.

    Parameters
    ----------
    corpus_id : str
        UUID of the corpus to scope searches to.  Set per-route by the
        FastAPI endpoint — invisible to the LLM.
    sessionmaker : optional
        Inject a fake sessionmaker for testing.  When ``None`` (default)
        the tools lazily create a real one on first call.
    embedding_client : optional
        Inject a fake embedding client for testing.  When ``None``
        (default) the tools lazily create a real one on first call.

    Returns
    -------
    list[BaseTool]
        ``[rag_search, rag_read_document]`` — two LangChain tool objects
        ready to pass to ``create_agent(tools=[...])``.
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

            _sessionmaker = cast(AsyncSessionMaker, create_db_sessionmaker(settings.database_url))
        return _embedding_client, _sessionmaker

    @tool
    async def rag_search(query: str, top_k: int = 5) -> dict[str, Any]:
        """Semantic search over the active knowledge base corpus.

        Use this tool when you need to find relevant information in the
        knowledge base.  Returns ranked chunks with content, metadata,
        and similarity scores.

        Args:
            query: Natural-language search query (2-10 words recommended).
            top_k: Number of results to return (default 5, max 20).
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
            return {"results": [r.model_dump() for r in results], "error": None}
        except Exception as exc:
            return {"results": [], "error": str(exc)}

    @tool
    async def rag_read_document(chunk_ids: list[int]) -> dict[str, Any]:
        """Retrieve full source context for given chunk IDs.

        Given one or more chunk IDs, returns ALL chunks from the same
        source file(s) within the active corpus.  Use this when a search
        hit looks promising and you want the surrounding document context.

        Args:
            chunk_ids: One or more chunk IDs to look up.
        """
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

    return [rag_search, rag_read_document]
