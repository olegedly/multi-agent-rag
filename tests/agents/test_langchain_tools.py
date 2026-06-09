"""Tests for LangChain RAG tool factory.

Uses the ``create_rag_tools`` factory with injected fakes. The factory
returns LangChain ``BaseTool`` objects with ``corpus_id`` baked into
each closure.
"""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool

from tests.fakes import FakeEmbeddingClient, FakeRow, FakeSessionMaker


@pytest.fixture
def embedding_client():
    return FakeEmbeddingClient()


@pytest.fixture
def sessionmaker():
    return FakeSessionMaker()


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


# ── Tracer bullet 1: factory returns BaseTool objects ───────────────────────


class TestToolFactory:
    """create_rag_tools returns LangChain BaseTool objects."""

    @pytest.fixture
    def tools(self, embedding_client, sessionmaker):
        from backend.agents.langchain_tools import create_rag_tools

        return create_rag_tools(
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
            embedding_client=embedding_client,
        )

    def test_returns_two_tools(self, tools):
        assert len(tools) == 2

    def test_returns_basetool_instances(self, tools):
        for t in tools:
            assert isinstance(t, BaseTool), f"{t.name} is not a BaseTool"

    def test_named_rag_search_and_rag_read(self, tools):
        names = {t.name for t in tools}
        assert names == {"rag_search", "rag_read_document"}

    def test_rag_search_description(self, tools):
        search = next(t for t in tools if t.name == "rag_search")
        assert "semantic" in search.description.lower() or "search" in search.description.lower()

    def test_rag_read_description(self, tools):
        read = next(t for t in tools if t.name == "rag_read_document")
        assert "chunk" in read.description.lower() or "document" in read.description.lower()

    def test_rag_search_has_query_param(self, tools):
        search = next(t for t in tools if t.name == "rag_search")
        assert "query" in search.args
        assert "top_k" in search.args

    def test_rag_read_has_chunk_ids_param(self, tools):
        read = next(t for t in tools if t.name == "rag_read_document")
        assert "chunk_ids" in read.args


# ── Tracer bullet 2: tool execution with injected fakes ──────────────────


class TestRagSearchExecution:
    """rag_search dispatches to backend/rag/search.py with baked corpus_id."""

    @pytest.fixture
    def tools(self, embedding_client, sessionmaker):
        from backend.agents.langchain_tools import create_rag_tools

        return create_rag_tools(
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
            embedding_client=embedding_client,
        )

    async def test_returns_corpus_scoped_results(
        self, tools, sessionmaker, corpus_a_chunks,
    ):
        """corpus_id from factory is used to scope the search."""
        sessionmaker.chunks = corpus_a_chunks
        search_tool = next(t for t in tools if t.name == "rag_search")

        result = await search_tool.ainvoke({"query": "test query", "top_k": 5})

        assert result["error"] is None
        assert len(result["results"]) == 2
        for r in result["results"]:
            assert r["corpus_id"] == "corpus_a"

    async def test_missing_corpus_in_db_returns_empty(
        self, tools, sessionmaker, corpus_a_chunks,
    ):
        """A corpus_id that exists but has no data → empty, not crash."""
        sessionmaker.chunks = corpus_a_chunks
        from backend.agents.langchain_tools import create_rag_tools

        other_tools = create_rag_tools(
            corpus_id="no_data_corpus",
            sessionmaker=sessionmaker,
            embedding_client=FakeEmbeddingClient(),
        )
        search_tool = next(t for t in other_tools if t.name == "rag_search")

        result = await search_tool.ainvoke({"query": "test", "top_k": 5})

        assert result["error"] is None
        assert result["results"] == []


class TestRagReadDocumentExecution:
    """rag_read_document dispatches with baked corpus_id."""

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

    @pytest.fixture
    def tools(self, embedding_client, sessionmaker):
        from backend.agents.langchain_tools import create_rag_tools

        return create_rag_tools(
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
            embedding_client=embedding_client,
        )

    async def test_returns_all_chunks_from_same_source(
        self, tools, sessionmaker, multi_file_chunks,
    ):
        """Given chunk 1 (doc1.md), returns both chunks from doc1.md."""
        sessionmaker.chunks = multi_file_chunks
        read_tool = next(t for t in tools if t.name == "rag_read_document")

        result = await read_tool.ainvoke({"chunk_ids": [1]})

        assert result["error"] is None
        assert len(result["results"]) == 2
        assert {r["id"] for r in result["results"]} == {1, 2}

    async def test_cross_corpus_chunk_ids_returns_empty(
        self, tools, sessionmaker, multi_file_chunks,
    ):
        """A chunk from corpus_b requested with corpus_a scope → empty."""
        sessionmaker.chunks = multi_file_chunks
        read_tool = next(t for t in tools if t.name == "rag_read_document")

        result = await read_tool.ainvoke({"chunk_ids": [4]})

        assert result["error"] is None
        assert result["results"] == []
