"""Tests for ``rag/search.py`` — semantic search and document retrieval.

Uses fake embedding client + fake async session that mimics the
SQLAlchemy async session interface so tests stay fast and isolated.
"""

from dataclasses import dataclass, field

import pytest

from backend.rag.search import read_document, search_corpus

# ── Fakes ─────────────────────────────────────────────────────────────────────


class FakeEmbeddingClient:
    """Returns a fixed-dimension vector for every input text.

    For fast, deterministic tests.  The vector is all zeros plus 1.0
    at a fixed offset so cosine similarity can be non-trivial.
    """

    def __init__(self, ndim: int = 768):
        self.ndim = ndim
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        vec = [0.0] * self.ndim
        vec[0] = 1.0
        return [vec for _ in texts]


@dataclass
class FakeRow:
    """Mimics a SQLAlchemy async Result row."""

    id: int
    corpus_id: str
    content: str
    metadata: dict = field(default_factory=dict)
    score: float | None = None
    source_filename: str = ""


class FakeResult:
    """Mimics a SQLAlchemy ``Result`` (sync iteration over rows)."""

    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Mimics an async SQLAlchemy session with pre-loaded chunks.

    Supports the ``async with`` protocol so it can be used with
    ``async with sessionmaker() as session:``.
    """

    def __init__(self, chunks: list[FakeRow] | None = None):
        self.chunks = chunks or []
        self.executed_sql: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def execute(self, statement, parameters: object | None = None):
        self.executed_sql.append(str(statement))
        sql_str = str(statement)
        params = parameters if isinstance(parameters, dict) else {}

        if "ORDER BY embedding <=> :query_vec" in sql_str:
            # search_corpus query
            corpus_id = params.get("corpus_id")
            top_k = params.get("top_k", 5)
            matching = [
                FakeRow(
                    id=c.id,
                    corpus_id=c.corpus_id,
                    content=c.content,
                    metadata=c.metadata,
                    score=0.85,
                    source_filename=c.source_filename,
                )
                for c in self.chunks
                if c.corpus_id == corpus_id
            ]
            return FakeResult(matching[:top_k])

        if "AND source_filename IN (" in sql_str:
            # read_document query
            corpus_id = params.get("corpus_id")
            chunk_ids = params.get("chunk_ids", [])
            source_files = {
                c.source_filename
                for c in self.chunks
                if c.id in chunk_ids and c.corpus_id == corpus_id
            }
            matching = [
                FakeRow(
                    id=c.id,
                    corpus_id=c.corpus_id,
                    content=c.content,
                    metadata=c.metadata,
                    source_filename=c.source_filename,
                )
                for c in self.chunks
                if c.corpus_id == corpus_id and c.source_filename in source_files
            ]
            return FakeResult(matching)

        return FakeResult([])


class FakeSessionMaker:
    """Mimics ``async_sessionmaker`` — callable that returns a FakeSession.

    ``async with FakeSessionMaker() as session:`` works because
    ``__call__`` is a coroutine that returns a ``FakeSession`` with
    ``__aenter__`` / ``__aexit__``.
    """

    def __init__(self, chunks: list[FakeRow] | None = None):
        self.chunks = chunks or []

    def __call__(self, **kwargs: object) -> FakeSession:
        """Return a fresh FakeSession."""
        return FakeSession(self.chunks)


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
