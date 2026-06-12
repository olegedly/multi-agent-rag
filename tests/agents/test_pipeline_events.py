"""Tests for pipeline AG-UI event emission.

Exercises ``run_pipeline()`` with a mocked ``agent.astream()`` to verify
the correct sequence and shape of AG-UI protocol events under the new
streaming model (``stream_mode="messages"``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from ag_ui.core.events import (
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel

from backend.corpus_config import CorporaConfig


@pytest.fixture
def corpora_config():
    return CorporaConfig.from_dicts([
        {
            "id": "corpus-a-uuid",
            "slug": "eu-ai-act",
            "name": "EU AI Act",
            "description": "Test corpus",
            "chunker": "markdown-heading",
            "documents": "corpora/eu-ai-act/**/*.md",
        },
    ])


@pytest.fixture
def mock_model():
    """A fake BaseChatModel that sidesteps real API credentials."""
    return AsyncMock(spec=BaseChatModel)


# ── Tracer bullet 1: run_pipeline with text-only streaming ──────────────────


@pytest.fixture
def mock_astream_text():
    """Mock agent so astream yields text-only AIMessageChunks."""
    async def _astream(*args, **kwargs):
        yield AIMessageChunk(content="Hello, "), {"langgraph_node": "agent"}
        yield AIMessageChunk(content="world!"), {"langgraph_node": "agent"}

    mock_agent = AsyncMock()
    mock_agent.astream = _astream
    with patch("langchain.agents.create_agent", return_value=mock_agent):
        yield


class TestPipelineTextEvents:
    """run_pipeline() yields AG-UI text events in correct order."""

    async def test_emits_run_started_first(self, corpora_config, mock_astream_text, mock_model):
        """First event must be RunStartedEvent with thread/run IDs."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)
        assert len(events) >= 1
        first = events[0]
        assert isinstance(first, RunStartedEvent)
        assert first.thread_id == "th-default"
        assert first.run_id == "run-default"
        assert first.timestamp is not None

    async def test_emits_text_message_events(self, corpora_config, mock_astream_text, mock_model):
        """Content chunks yield TEXT_MESSAGE_START/CONTENT/CONTENT/END."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        text_events = [
            e
            for e in events
            if isinstance(e, (TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent))
        ]
        assert len(text_events) >= 3

        # Two content events from the two chunks
        contents = [e for e in text_events if isinstance(e, TextMessageContentEvent)]
        assert len(contents) == 2
        assert contents[0].delta == "Hello, "
        assert contents[1].delta == "world!"

    async def test_emits_run_finished_last(self, corpora_config, mock_astream_text, mock_model):
        """Last event must be RunFinishedEvent."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.thread_id == "th-default"
        assert last.run_id == "run-default"

    async def test_full_text_sequence(self, corpora_config, mock_astream_text, mock_model):
        """Verify complete event type sequence for text-only stream."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        types = [type(e).__name__ for e in events]
        assert types == [
            "RunStartedEvent",
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]

    async def test_unknown_corpus_returns_no_events(self, corpora_config):
        """Unknown corpus slug yields zero events."""
        events = await collect_pipeline_events(corpora_config, slug="nonexistent")
        assert events == []


# ── Tracer bullet 2: tool call streaming ────────────────────────────────────


@pytest.fixture
def mock_astream_tools():
    """Mock agent so astream yields tool calls then results then answer."""
    async def _astream(*args, **kwargs):
        # Agent decides to call rag_search
        yield AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": '{"query":', "id": "call-1", "index": 0},
            ],
        ), {"langgraph_node": "agent"}
        # LangGraph merges tool_call_chunks by index — subsequent chunk
        # has id=None / name=None but carries the args continuation
        yield AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": None, "args": '"EU AI Act"}', "id": None, "index": 0},
            ],
        ), {"langgraph_node": "agent"}
        # Tool returns result
        yield ToolMessage(
            content="Found 3 relevant documents about EU AI Act.",
            tool_call_id="call-1",
        ), {"langgraph_node": "tools"}
        # Final answer
        yield AIMessageChunk(content="Based on search results"), {"langgraph_node": "agent"}
        yield AIMessageChunk(content=" EU AI Act affects..."), {"langgraph_node": "agent"}

    mock_agent = AsyncMock()
    mock_agent.astream = _astream
    with patch("langchain.agents.create_agent", return_value=mock_agent):
        yield


class TestPipelineToolEvents:
    """run_pipeline() yields TOOL_CALL_* events alongside text."""

    async def test_emits_tool_call_events(self, corpora_config, mock_astream_tools, mock_model):
        """Tool call chunks yield START/ARGS/ARGS events."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        tool_starts = [e for e in events if isinstance(e, ToolCallStartEvent)]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_call_id == "call-1"
        assert tool_starts[0].tool_call_name == "rag_search"

        tool_args = [e for e in events if isinstance(e, ToolCallArgsEvent)]
        assert len(tool_args) == 2
        # Even the merged chunk (id=None on wire) must have resolved id
        assert all(a.tool_call_id == "call-1" for a in tool_args)

    async def test_emits_tool_result_events(self, corpora_config, mock_astream_tools, mock_model):
        """Tool result yields TOOL_CALL_END + TOOL_CALL_RESULT."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        ends = [e for e in events if isinstance(e, ToolCallEndEvent)]
        assert len(ends) == 1

        results = [e for e in events if isinstance(e, ToolCallResultEvent)]
        assert len(results) == 1
        assert results[0].tool_call_id == "call-1"
        assert "EU AI Act" in results[0].content

    async def test_full_tool_sequence(self, corpora_config, mock_astream_tools, mock_model):
        """Verify complete event sequence for tool-using agent."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        types = [type(e).__name__ for e in events]
        assert types == [
            "RunStartedEvent",
            "ToolCallStartEvent",
            "ToolCallArgsEvent",
            "ToolCallArgsEvent",
            "ToolCallEndEvent",
            "ToolCallResultEvent",
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]


# ── Tracer bullet 3: reasoning content streaming ────────────────────────────


@pytest.fixture
def mock_astream_reasoning():
    """Mock agent so astream yields reasoning then text."""
    async def _astream(*args, **kwargs):
        # Reasoning phase
        yield AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "Let me think about "},
        ), {"langgraph_node": "agent"}
        yield AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "the EU AI Act"},
        ), {"langgraph_node": "agent"}
        # Answer phase
        yield AIMessageChunk(content="Here is my analysis"), {"langgraph_node": "agent"}

    mock_agent = AsyncMock()
    mock_agent.astream = _astream
    with patch("langchain.agents.create_agent", return_value=mock_agent):
        yield


class TestPipelineReasoningEvents:
    """run_pipeline() yields REASONING_MESSAGE_* events."""

    async def test_emits_reasoning_events(self, corpora_config, mock_astream_reasoning, mock_model):
        """Reasoning chunks yield REASONING_MESSAGE_START/CONTENT/CONTENT/END."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        starts = [e for e in events if isinstance(e, ReasoningMessageStartEvent)]
        assert len(starts) == 1

        contents = [e for e in events if isinstance(e, ReasoningMessageContentEvent)]
        assert len(contents) == 2
        assert contents[0].delta == "Let me think about "
        assert contents[1].delta == "the EU AI Act"

        ends = [e for e in events if isinstance(e, ReasoningMessageEndEvent)]
        assert len(ends) == 1

    async def test_full_reasoning_sequence(self, corpora_config, mock_astream_reasoning, mock_model):
        """Verify complete event sequence for reasoning + answer."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        types = [type(e).__name__ for e in events]
        assert types == [
            "RunStartedEvent",
            "StepStartedEvent",
            "ReasoningMessageStartEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageEndEvent",
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]


# ── Tracer bullet 4: error handling ────────────────────────────────────────


@pytest.fixture
def mock_astream_crash():
    """Mock agent so astream raises an exception."""
    async def _astream(*args, **kwargs):
        yield AIMessageChunk(content="Before crash"), {"langgraph_node": "agent"}
        raise RuntimeError("API failure")

    mock_agent = AsyncMock()
    mock_agent.astream = _astream
    with patch("langchain.agents.create_agent", return_value=mock_agent):
        yield


class TestPipelineErrors:
    """run_pipeline() handles errors gracefully."""

    async def test_emits_run_error_on_crash(self, corpora_config, mock_astream_crash, mock_model):
        """When agent crashes, pipeline yields RUN_ERROR (not RUN_FINISHED)."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        errors = [e for e in events if isinstance(e, RunErrorEvent)]
        assert len(errors) == 1
        assert "API failure" in errors[0].message

    async def test_crash_does_not_emit_run_finished(self, corpora_config, mock_astream_crash, mock_model):
        """When agent crashes, no RUN_FINISHED event."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        finished = [e for e in events if isinstance(e, RunFinishedEvent)]
        assert len(finished) == 0

    async def test_text_block_closed_before_error(self, corpora_config, mock_astream_crash, mock_model):
        """Open text block is closed before RUN_ERROR."""
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        ends = [e for e in events if isinstance(e, TextMessageEndEvent)]
        assert len(ends) == 1

        error_idx = next(i for i, e in enumerate(events) if isinstance(e, RunErrorEvent))
        end_idx = next(i for i, e in enumerate(events) if isinstance(e, TextMessageEndEvent))
        assert end_idx < error_idx


# ── Helper ───────────────────────────────────────────────────────────────────


async def collect_pipeline_events(
    corpora_config: CorporaConfig,
    slug: str = "eu-ai-act",
    model=None,
) -> list[object]:
    """Collect pipeline events into a list."""
    from backend.agents.pipeline import run_pipeline
    from backend.config import Settings

    settings = Settings(demo_disable_budget=True)  # no /data/ needed

    events: list[object] = []
    async for event in run_pipeline(
        messages=[{"role": "user", "content": "test"}],
        corpus_slug=slug,
        corpora_config=corpora_config,
        settings=settings,
        thread_id="th-default",
        run_id="run-default",
        model=model,
    ):
        events.append(event)
    return events
