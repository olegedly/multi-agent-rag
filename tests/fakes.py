"""Fakes for embedding client, HTTP transport, and async database sessions.

All fakes satisfy runtime-checkable Protocols from the backend modules
so tests stay fast without real HTTP or database calls.
"""

import json
from dataclasses import dataclass, field

import httpx

from backend.http_client import Transport, TransportError


# ── HTTP Transport Fake ──────────────────────────────────────────────────────


class FakeTransport(Transport):
    """A fake HTTP transport for testing LLM clients.

    Pre-records response bodies (plain for non-streaming, chunk-lists for
    streaming) so that embedding client tests can
    exercise request/response parsing without ``pytest-httpx``.
    """

    def __init__(self, status: int = 200, body: bytes | None = None):
        self.status = status
        self._body = body if body is not None else b'{"content": "ok"}'
        self.stream_chunks: list[str] | None = None
        self.sent_requests: list[tuple[str, dict, dict]] = []  # (url, headers, json_body)

    @classmethod
    def with_body(cls, body: bytes, status: int = 200) -> "FakeTransport":
        return cls(status=status, body=body)

    @classmethod
    def with_stream(cls, chunks: list[str], status: int = 200) -> "FakeTransport":
        t = cls(status=status)
        t.stream_chunks = chunks
        return t

    @classmethod
    def with_error(cls, status: int, body: bytes | None = None) -> "FakeTransport":
        if body is None:
            body = json.dumps({"error": {"message": "API error"}}).encode()
        return cls(status=status, body=body)

    async def send(
        self, url: str, headers: dict, json_body: dict
    ) -> httpx.Response:
        self.sent_requests.append((url, headers, json_body))
        if self.status >= 400:
            raise TransportError(status=self.status, message="API error", details=self._body.decode())
        return httpx.Response(status_code=self.status, content=self._body)

    async def send_stream(self, url: str, headers: dict, json_body: dict):
        self.sent_requests.append((url, headers, json_body))
        if self.status >= 400:
            raise TransportError(status=self.status, message="API error")
        for chunk in (self.stream_chunks or []):
            yield chunk

    async def close(self) -> None:
        pass


# ── Embedding Client Fake ────────────────────────────────────────────────────


class FakeEmbeddingClient:
    """Fixed-dimension vector for every input text.

    Returns all-zero vectors with a 1.0 at the first position, so
    cosine-similarity results are deterministic and non-trivial.
    """

    def __init__(self, ndim: int = 768):
        self.ndim = ndim
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        vec = [0.0] * self.ndim
        vec[0] = 1.0
        return [vec for _ in texts]


# ── RAG / Database Fakes ─────────────────────────────────────────────────────


@dataclass
class FakeRow:
    """Mimics a SQLAlchemy Result row for RAG tests."""

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

    Satisfies ``AsyncSession`` from ``backend.rag.search`` (runtime-checkable).
    Supports ``async with sessionmaker() as session:`` via ``__aenter__`` / ``__aexit__``.
    Routes ``execute()`` based on the SQL string so both ``search_corpus``
    and ``read_document`` queries work.
    """

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

        if "ORDER BY embedding <=> CAST(:query_vec AS vector)" in sql_str:
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
    """Callable returning a ``FakeSession`` (sync, like ``async_sessionmaker``).

    Satisfies ``AsyncSessionMaker`` from ``backend.rag.search`` (runtime-checkable).
    """

    def __init__(self, chunks: list[FakeRow] | None = None):
        self.chunks = chunks or []

    def __call__(self, **kwargs: object) -> FakeSession:
        return FakeSession(self.chunks)
