"""Tests for ``rag/search.py`` — semantic search and document retrieval.

Uses fake embedding client + fake async session that mimics the
SQLAlchemy async session interface so tests stay fast and isolated.
"""

import pytest

from backend.rag.search import read_document, search_corpus
from tests.fakes import FakeEmbeddingClient, FakeRow, FakeSessionMaker


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def embedding_client():
    return FakeEmbeddingClient()


@pytest.fixture
def corpus_a_chunks():
    return [
        FakeRow(
            id=1,
            corpus_id="corpus_a",
            content="Document A chunk 1",
            source_filename="a.md",
        ),
        FakeRow(
            id=2,
            corpus_id="corpus_a",
            content="Document A chunk 2",
            source_filename="a.md",
        ),
    ]


@pytest.fixture
def corpus_b_chunks():
    return [
        FakeRow(
            id=3,
            corpus_id="corpus_b",
            content="Document B chunk 1",
            source_filename="b.md",
        ),
    ]


@pytest.fixture
def mixed_chunks(corpus_a_chunks, corpus_b_chunks):
    return corpus_a_chunks + corpus_b_chunks


# ── search_corpus tests ──────────────────────────────────────────────────────


class TestSearchCorpus:
    """search_corpus: semantic vector search over a single corpus."""

    async def test_returns_only_chunks_from_correct_corpus(
        self, embedding_client, mixed_chunks
    ):
        """search_corpus filters by corpus_id."""
        sessionmaker = FakeSessionMaker(mixed_chunks)
        results = await search_corpus(
            query="test query",
            corpus_id="corpus_a",
            top_k=5,
            embedding_client=embedding_client,
            sessionmaker=sessionmaker,
        )

        assert len(results) == 2
        assert all(r.corpus_id == "corpus_a" for r in results)
        assert embedding_client.calls == [["test query"]]

    async def test_returns_cosine_similarity_scores(
        self, embedding_client, corpus_a_chunks
    ):
        """Results include a score in [0, 1]."""
        sessionmaker = FakeSessionMaker(corpus_a_chunks)
        results = await search_corpus(
            query="test query",
            corpus_id="corpus_a",
            top_k=5,
            embedding_client=embedding_client,
            sessionmaker=sessionmaker,
        )

        for r in results:
            assert r.score is not None
            assert 0.0 <= r.score <= 1.0

    async def test_missing_corpus_returns_empty(self, embedding_client, mixed_chunks):
        """Unknown corpus_id yields empty results."""
        sessionmaker = FakeSessionMaker(mixed_chunks)
        results = await search_corpus(
            query="test query",
            corpus_id="nonexistent",
            top_k=5,
            embedding_client=embedding_client,
            sessionmaker=sessionmaker,
        )

        assert results == []

    async def test_empty_corpus_returns_empty(self, embedding_client):
        """No chunks at all yields empty results."""
        sessionmaker = FakeSessionMaker([])
        results = await search_corpus(
            query="test query",
            corpus_id="corpus_a",
            top_k=5,
            embedding_client=embedding_client,
            sessionmaker=sessionmaker,
        )

        assert results == []

    async def test_respects_top_k(self, embedding_client):
        """top_k limits the number of results."""
        chunks = [
            FakeRow(
                id=i,
                corpus_id="corpus_a",
                content=f"Chunk {i}",
                source_filename="doc.md",
            )
            for i in range(10)
        ]
        sessionmaker = FakeSessionMaker(chunks)
        results = await search_corpus(
            query="test query",
            corpus_id="corpus_a",
            top_k=3,
            embedding_client=embedding_client,
            sessionmaker=sessionmaker,
        )

        assert len(results) == 3


# ── read_document tests ─────────────────────────────────────────────────────


class TestReadDocument:
    """read_document: returns all chunks from the same source file(s)."""

    @pytest.fixture
    def multi_file_chunks(self):
        return [
            # corpus_a: two source files
            FakeRow(
                id=1,
                corpus_id="corpus_a",
                content="A doc1 chunk 1",
                source_filename="doc1.md",
            ),
            FakeRow(
                id=2,
                corpus_id="corpus_a",
                content="A doc1 chunk 2",
                source_filename="doc1.md",
            ),
            FakeRow(
                id=3,
                corpus_id="corpus_a",
                content="A doc2 chunk 1",
                source_filename="doc2.md",
            ),
            # corpus_b: one source file
            FakeRow(
                id=4,
                corpus_id="corpus_b",
                content="B doc chunk 1",
                source_filename="doc_b.md",
            ),
            FakeRow(
                id=5,
                corpus_id="corpus_b",
                content="B doc chunk 2",
                source_filename="doc_b.md",
            ),
        ]

    async def test_returns_all_chunks_from_same_source(self, multi_file_chunks):
        """Given chunk 1 (doc1.md), returns both chunks from doc1.md."""
        sessionmaker = FakeSessionMaker(multi_file_chunks)
        results = await read_document(
            chunk_ids=[1],
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
        )

        assert len(results) == 2
        result_ids = {r.id for r in results}
        assert result_ids == {1, 2}

    async def test_cross_corpus_chunk_ids_returns_empty(self, multi_file_chunks):
        """A chunk from corpus_b requested with corpus_id=corpus_a returns empty."""
        sessionmaker = FakeSessionMaker(multi_file_chunks)
        results = await read_document(
            chunk_ids=[4],  # this is corpus_b
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
        )

        assert results == []

    async def test_multiple_chunk_ids_across_files(self, multi_file_chunks):
        """Given chunks from multiple source files, returns all from all those files."""
        sessionmaker = FakeSessionMaker(multi_file_chunks)
        results = await read_document(
            chunk_ids=[1, 3],  # doc1.md and doc2.md
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
        )

        assert len(results) == 3
        result_ids = {r.id for r in results}
        assert result_ids == {1, 2, 3}

    async def test_result_has_no_score(self, multi_file_chunks):
        """read_document returns documents without a similarity score."""
        sessionmaker = FakeSessionMaker(multi_file_chunks)
        results = await read_document(
            chunk_ids=[1],
            corpus_id="corpus_a",
            sessionmaker=sessionmaker,
        )

        for r in results:
            assert r.score is None
