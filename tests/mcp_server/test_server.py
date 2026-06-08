"""Tests for the MCP server tools.

Uses ``create_mcp_server()`` with injected fakes — no module globals,
no monkeypatching, no ``importlib.reload()``.
"""

import pytest

from mcp.server.fastmcp.exceptions import ToolError

from tests.fakes import FakeEmbeddingClient, FakeRow, FakeSessionMaker


# ── Factory fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def server():
    """Build a fake-wired MCP server via the factory."""
    from backend.mcp_server.server import create_mcp_server

    client = FakeEmbeddingClient()
    sm = FakeSessionMaker()
    mod = create_mcp_server(embedding_client=client, sessionmaker=sm)
    return mod, client, sm


# ── search_corpus tests ──────────────────────────────────────────────────────


class TestSearchCorpusTool:
    """search_corpus tool via FastMCP.call_tool."""

    async def test_returns_scoped_results(self, server):
        """Results are returned for the requested corpus."""
        mod, _client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="Hello world",
                    source_filename="doc.md"),
        ]

        result = await mod.call_tool("search_corpus", {
            "query": "hello",
            "corpus_id": "corpus_a",
            "top_k": 5,
        })

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
        mod, _client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="Hello",
                    source_filename="doc.md"),
        ]

        result = await mod.call_tool("search_corpus", {
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
        mod, _client, _sm = server
        with pytest.raises(ToolError, match="Unknown tool"):
            await mod.call_tool("nonexistent_tool", {})


# ── read_document tests ─────────────────────────────────────────────────────


class TestReadDocumentTool:
    """read_document tool via FastMCP.call_tool."""

    async def test_returns_source_level_chunks(self, server):
        """All chunks from the same source file are returned."""
        mod, _client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="Doc chunk 1",
                    source_filename="doc1.md"),
            FakeRow(id=2, corpus_id="corpus_a", content="Doc chunk 2",
                    source_filename="doc1.md"),
            FakeRow(id=3, corpus_id="corpus_a", content="Other doc chunk",
                    source_filename="doc2.md"),
        ]

        result = await mod.call_tool("read_document", {
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
        mod, _client, sm = server
        sm.chunks = [
            FakeRow(id=1, corpus_id="corpus_a", content="A chunk",
                    source_filename="a.md"),
            FakeRow(id=4, corpus_id="corpus_b", content="B chunk",
                    source_filename="b.md"),
        ]

        result = await mod.call_tool("read_document", {
            "chunk_ids": [4],  # corpus_b
            "corpus_id": "corpus_a",
        })

        import json
        body = json.loads(result[0].text)
        assert body["error"] is None
        assert body["results"] == []
