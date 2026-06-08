"""Fake LLM client, embedding client, and async session for testing.

All fakes satisfy the runtime-checkable Protocols from the backend
modules so tests stay fast without real HTTP or database calls.
"""

import json
from dataclasses import dataclass, field
from typing import AsyncIterable

import httpx

from backend.llm.protocol import LLMClient, LLMResponse, Message, StreamEvent, ToolDef, Usage
from backend.llm.transport import Transport


# ── LLM Client Fakes ─────────────────────────────────────────────────────────


class FakeTransport(Transport):
    """A fake HTTP transport for testing LLM clients.

    Pre-records response bodies (plain for non-streaming, chunk-lists for
    streaming) so that ``OpenAIClient`` / ``AnthropicClient`` tests can
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
            from backend.llm.protocol import LLMError

            raise LLMError(status=self.status, message="API error", details=self._body.decode())
        return httpx.Response(status_code=self.status, content=self._body)

    async def send_stream(self, url: str, headers: dict, json_body: dict):
        self.sent_requests.append((url, headers, json_body))
        if self.status >= 400:
            from backend.llm.protocol import LLMError

            raise LLMError(status=self.status, message="API error")
        for chunk in (self.stream_chunks or []):
            yield chunk

    async def close(self) -> None:
        pass


class FakeLLMClient(LLMClient):
    """A fake LLM client with deterministic responses.

    Cycles through ``responses`` in order.  For streaming, yields text
    deltas then a final event with usage.
    """

    def __init__(self, responses: list[str] | None = None):
        self.model = "fake-model"
        self.responses = responses or ["Fake response"]
        self._call_index = 0

    def _next_response(self) -> str:
        text = self.responses[self._call_index % len(self.responses)]
        self._call_index += 1
        return text

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> LLMResponse:
        text = self._next_response()
        usage = Usage(input_tokens=10, output_tokens=len(text))
        return LLMResponse(content=text, usage=usage)

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> AsyncIterable[StreamEvent]:
        text = self._next_response()
        chars = list(text)
        for char in chars:
            yield StreamEvent(content=char)
        usage = Usage(input_tokens=10, output_tokens=len(text))
        yield StreamEvent(usage=usage)


class CollectingLLMClient(LLMClient):
    """Records every call for assertion; always returns the same response."""

    def __init__(self, response: str = "collected"):
        self.model = "collector"
        self.calls: list[tuple[list[Message], str | None, list[ToolDef] | None]] = []
        self._response = response

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> LLMResponse:
        self.calls.append((messages, system, tools))
        usage = Usage(input_tokens=5, output_tokens=len(self._response))
        return LLMResponse(content=self._response, usage=usage)

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> AsyncIterable[StreamEvent]:
        self.calls.append((messages, system, tools))
        usage = Usage(input_tokens=5, output_tokens=len(self._response))
        for char in self._response:
            yield StreamEvent(content=char)
        yield StreamEvent(usage=usage)


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
