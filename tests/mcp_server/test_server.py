"""Tests for the MCP server tools.

Uses ``FastMCP.call_tool()`` to invoke tools in-process after injecting
fake dependencies into the server module.
"""

from dataclasses import dataclass, field

import pytest

from mcp.server.fastmcp.exceptions import ToolError


# ── Fakes ─────────────────────────────────────────────────────────────────────


class FakeEmbeddingClient:
    """Fixed-dimension vector for every input text."""

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
    """Mimics a SQLAlchemy Result row."""

    id: int
    corpus_id: str
    content: str
    metadata: dict = field(default_factory=dict)
    score: float | None = None
    source_filename: str = ""


class FakeResult:
    """Mimics a SQLAlchemy Result (sync iteration over rows)."""

    def __init__(self, rows: list):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return self._rows


class FakeSession:
    """Mimics an async SQLAlchemy session with pre-loaded chunks."""

    def __init__(self, chunks: list[FakeRow] | None = None):
        self.chunks = chunks or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def close(self):
        pass

    async def commit(self):
        pass
    async def rollback(self):
        pass

    async def execute(self, statement, parameters: object | None = None):
        sql_str = str(statement)
        params = parameters if isinstance(parameters, dict) else {}

        if "ORDER BY embedding <=> :query_vec" in sql_str:
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
    """Callable returning a FakeSession (sync, like ``async_sessionmaker``)."""

    def __init__(self, chunks: list[FakeRow] | None = None):
        self.chunks = chunks or []

    def __call__(self, **kwargs: object) -> FakeSession:
        return FakeSession(self.chunks)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def server():
    """Import the server module and inject fakes."""
    import importlib
    import backend.mcp_server.server as mod

    # Force re-import so lazy globals are fresh
    importlib.reload(mod)

    client = FakeEmbeddingClient()
    sm = FakeSessionMaker()
    mod._embedding_client = client
    mod._sessionmaker = sm

    return mod, client, sm


# ── search_corpus tests ──────────────────────────────────────────────────────


class TestSearchCorpusTool:
    """search_corpus tool via FastMCP.call_tool."""

    async def test_returns_scoped_results(self, server):
        """Results are returned for the requested corpus."""
        mod, client, sm = server
        # Seed a chunk via the sessionmaker
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="Hello world",
                    source_filename="doc.md"),
        ]

        result = await mod.mcp.call_tool("search_corpus", {
            "query": "hello",
            "corpus_id": "corpus_a",
            "top_k": 5,
        })

        # call_tool returns list[TextContent]
        assert len(result) == 1
        assert result[0].type == "text"

        import json
        body = json.loads(result[0].text)
        assert body["error"] is None
        assert len(body["results"]) == 1
        assert body["results"][0]["corpus_id"] == "corpus_a"
        assert body["results"][0]["content"] == "Hello world"

    async def test_missing_corpus_returns_empty_results(self, server):
        """Unknown corpus_id yields empty results (no error)."""
        mod, client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="Hello",
                    source_filename="doc.md"),
        ]

        result = await mod.mcp.call_tool("search_corpus", {
            "query": "hello",
            "corpus_id": "nonexistent",
            "top_k": 5,
        })

        import json
        body = json.loads(result[0].text)
        assert body["error"] is None
        assert body["results"] == []

    async def test_nonexistent_tool_returns_proper_error(self, server):
        """Calling an unknown tool should raise or return error."""
        mod, client, sm = server
        with pytest.raises(ToolError, match="Unknown tool"):
            await mod.mcp.call_tool("nonexistent_tool", {})


# ── read_document tests ─────────────────────────────────────────────────────


class TestReadDocumentTool:
    """read_document tool via FastMCP.call_tool."""

    async def test_returns_source_level_chunks(self, server):
        """All chunks from the same source file are returned."""
        mod, client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="Doc chunk 1",
                    source_filename="doc1.md"),
            FakeRow(id=2, corpus_id="corpus_a", content="Doc chunk 2",
                    source_filename="doc1.md"),
            FakeRow(id=3, corpus_id="corpus_a", content="Other doc chunk",
                    source_filename="doc2.md"),
        ]

        result = await mod.mcp.call_tool("read_document", {
            "chunk_ids": [1],
            "corpus_id": "corpus_a",
        })

        import json
        body = json.loads(result[0].text)
        assert body["error"] is None
        assert len(body["results"]) == 2
        result_ids = {r["id"] for r in body["results"]}
        assert result_ids == {1, 2}

    async def test_cross_corpus_returns_empty(self, server):
        """Chunks from another corpus are not returned."""
        mod, client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="A chunk",
                    source_filename="a.md"),
            FakeRow(id=4, corpus_id="corpus_b", content="B chunk",
                    source_filename="b.md"),
        ]

        result = await mod.mcp.call_tool("read_document", {
            "chunk_ids": [4],  # corpus_b
            "corpus_id": "corpus_a",
        })

        import json
        body = json.loads(result[0].text)
        assert body["error"] is None
        assert body["results"] == []
