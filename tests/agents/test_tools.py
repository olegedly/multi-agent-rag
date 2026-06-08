"""Tests for ADK RAG tool functions.

Uses the ``make_rag_tools`` factory with injected fakes, plus a minimal
fake ``ToolContext`` that mimics ``context.state.get()`` for corpus ID
resolution.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import FakeEmbeddingClient, FakeRow, FakeSessionMaker


# ── Fake ToolContext ─────────────────────────────────────────────────────────


class FakeToolContext:
    """Mimics ``ToolContext`` (ADK's ``Context``) just enough for tools.

    ``tool_context.state`` is a dict (ADK uses a ``State`` object with the
    same ``.get()`` interface).
    """

    def __init__(self, state: dict[str, Any] | None = None):
        self._state = state or {}

    @property
    def state(self) -> dict[str, Any]:
        return self._state


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def embedding_client():
    return FakeEmbeddingClient()


@pytest.fixture
def sessionmaker():
    return FakeSessionMaker()


@pytest.fixture
def tools(embedding_client, sessionmaker):
    """Build the pair of tool functions via the factory with fakes."""
    from backend.agents.tools import make_rag_tools

    return make_rag_tools(
        sessionmaker=sessionmaker,
        embedding_client=embedding_client,
    )


@pytest.fixture
def corpus_a_chunks():
    return [
        FakeRow(
            id=1, corpus_id="corpus_a", content="RAG chunk one",
            source_filename="doc.md",
        ),
        FakeRow(
            id=2, corpus_id="corpus_a", content="RAG chunk two",
            source_filename="doc.md",
        ),
    ]


# ── Tracer: rag_search ──────────────────────────────────────────────────────


class TestRagSearch:
    """rag_search: corpus-scoped semantic search via ADK FunctionTool."""

    async def test_returns_corpus_scoped_results(
        self, tools, sessionmaker, corpus_a_chunks,
    ):
        """Tracer bullet: corpusId from tool_context.state is used to scope."""
        rag_search, _rag_read = tools
        sessionmaker.chunks = corpus_a_chunks
        ctx = FakeToolContext(state={"corpusId": "corpus_a"})

        result = await rag_search(
            query="test query",
            top_k=5,
            tool_context=ctx,
        )

        assert result["error"] is None
        assert len(result["results"]) == 2
        for r in result["results"]:
            assert r["corpus_id"] == "corpus_a"

    async def test_missing_corpus_id_returns_error(
        self, tools, sessionmaker, corpus_a_chunks,
    ):
        """No corpusId in state → error, not a crash."""
        rag_search, _rag_read = tools
        sessionmaker.chunks = corpus_a_chunks
        ctx = FakeToolContext(state={})  # no corpusId

        result = await rag_search(query="test", tool_context=ctx)

        assert result["error"] is not None
        assert result["results"] == []

    async def test_missing_corpus_in_db_returns_empty(
        self, tools, sessionmaker, corpus_a_chunks,
    ):
        """A corpusId that exists in state but has no data → empty."""
        rag_search, _rag_read = tools
        sessionmaker.chunks = corpus_a_chunks
        ctx = FakeToolContext(state={"corpusId": "nonexistent"})

        result = await rag_search(query="test", tool_context=ctx)

        assert result["error"] is None
        assert result["results"] == []


# ── rag_read_document ───────────────────────────────────────────────────────


class TestRagReadDocument:
    """rag_read_document: full source context from chunk IDs."""

    @pytest.fixture
    def multi_file_chunks(self):
        return [
            FakeRow(id=1, corpus_id="corpus_a", content="Doc1 chunk 1",
                    source_filename="doc1.md"),
            FakeRow(id=2, corpus_id="corpus_a", content="Doc1 chunk 2",
                    source_filename="doc1.md"),
            FakeRow(id=3, corpus_id="corpus_a", content="Doc2 chunk 1",
                    source_filename="doc2.md"),
            FakeRow(id=4, corpus_id="corpus_b", content="Other corpus",
                    source_filename="other.md"),
        ]

    async def test_returns_all_chunks_from_same_source(
        self, tools, sessionmaker, multi_file_chunks,
    ):
        """Given chunk 1 (doc1.md), returns both chunks from doc1.md."""
        _rag_search, rag_read = tools
        sessionmaker.chunks = multi_file_chunks
        ctx = FakeToolContext(state={"corpusId": "corpus_a"})

        result = await rag_read(chunk_ids=[1], tool_context=ctx)

        assert result["error"] is None
        assert len(result["results"]) == 2
        assert {r["id"] for r in result["results"]} == {1, 2}

    async def test_cross_corpus_chunk_ids_returns_empty(
        self, tools, sessionmaker, multi_file_chunks,
    ):
        """A chunk from corpus_b requested with corpus_a scope → empty."""
        _rag_search, rag_read = tools
        sessionmaker.chunks = multi_file_chunks
        ctx = FakeToolContext(state={"corpusId": "corpus_a"})

        result = await rag_read(chunk_ids=[4], tool_context=ctx)

        assert result["error"] is None
        assert result["results"] == []

    async def test_missing_corpus_id_returns_error(
        self, tools, sessionmaker, multi_file_chunks,
    ):
        """No corpusId in state → error, not crash."""
        _rag_search, rag_read = tools
        sessionmaker.chunks = multi_file_chunks
        ctx = FakeToolContext(state={})

        result = await rag_read(chunk_ids=[1], tool_context=ctx)

        assert result["error"] is not None
        assert result["results"] == []
