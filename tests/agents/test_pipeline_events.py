"""Tests for pipeline AG-UI event emission.

Exercises ``run_pipeline()`` with a mocked model to verify
the correct sequence and shape of AG-UI protocol events under the new
multi-agent orchestrator (Researcher → Critic → Synthesizer).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

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
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from backend.corpus_config import CorporaConfig


@pytest.fixture
def corpora_config():
    return CorporaConfig.from_dicts(
        [
            {
                "id": "corpus-a-uuid",
                "slug": "eu-ai-act",
                "name": "EU AI Act",
                "description": "Test corpus",
                "chunker": "markdown-heading",
                "documents": "corpora/eu-ai-act/**/*.md",
            },
        ]
    )


@pytest.fixture
def mock_model():
    """A fake BaseChatModel that sidesteps real API credentials."""
    return AsyncMock(spec=BaseChatModel)


# ── Tracer bullet 1: run_pipeline with text-only streaming ──────────────────


@pytest.fixture
def mock_text_only():
    """Set up model for text-only agent calls (no tool calls).

    3 agents, each producing 2 text chunks via astream + no-tool ainvoke.
    """
    call_count: list[int] = [0]
    # Each agent needs: astream (2 chunks) + ainvoke (1 result) = 3 calls
    # 3 agents × 2 calls each = 6 calls total (astream=3, ainvoke=3)
    TEXT_CHUNKS = ["Hello, ", "world!"]

    async def _astream_impl(messages, **kwargs):
        for chunk in TEXT_CHUNKS:
            yield AIMessageChunk(content=chunk)

    async def _ainvoke_impl(messages):
        call_count[0] += 1
        return AIMessage(content="Hello, world!")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model

    yield _apply


class TestPipelineTextEvents:
    """run_pipeline() yields AG-UI text events in correct order."""

    async def test_emits_run_started_first(
        self, corpora_config, mock_text_only, mock_model
    ):
        """First event must be RunStartedEvent with thread/run IDs."""
        mock_text_only(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)
        assert len(events) >= 1
        first = events[0]
        assert isinstance(first, RunStartedEvent)
        assert first.thread_id == "th-default"
        assert first.run_id == "run-default"
        assert first.timestamp is not None

    async def test_emits_text_message_events(
        self, corpora_config, mock_text_only, mock_model
    ):
        """Three agents each produce TEXT_MESSAGE_START/CONTENT/END."""
        mock_text_only(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        text_events = [
            e
            for e in events
            if isinstance(
                e, (TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent)
            )
        ]
        # 3 agents × 3 events each (START, CONTENT×2, END) = ... actually CONTENT×2 = 4 per agent
        # Let's count: per agent = 1 START + 2 CONTENT + 1 END = 4
        # 3 agents × 4 = 12
        assert len(text_events) == 12

        # 3 agents × 2 content chunks = 6 content events
        contents = [e for e in text_events if isinstance(e, TextMessageContentEvent)]
        assert len(contents) == 6
        # Each agent gets the same two chunks
        assert contents[0].delta == "Hello, "
        assert contents[1].delta == "world!"
        assert contents[2].delta == "Hello, "
        assert contents[3].delta == "world!"
        assert contents[4].delta == "Hello, "
        assert contents[5].delta == "world!"

    async def test_emits_run_finished_last(
        self, corpora_config, mock_text_only, mock_model
    ):
        """Last event must be RunFinishedEvent."""
        mock_text_only(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.thread_id == "th-default"
        assert last.run_id == "run-default"

    async def test_full_text_sequence(self, corpora_config, mock_text_only, mock_model):
        """Verify complete event type sequence for text-only stream.

        With the multi-agent orchestrator, three agent nodes (Researcher,
        Critic, Synthesizer) each produce the same text events from the
        mocked stream.
        """
        mock_text_only(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        types = [type(e).__name__ for e in events]
        assert types == [
            "RunStartedEvent",
            # Researcher
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            # Critic
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            # Synthesizer
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]

    async def test_text_events_include_agent_names(
        self,
        corpora_config,
        mock_text_only,
        mock_model,
    ):
        """Each agent's TEXT_MESSAGE_START should carry the agent name."""
        mock_text_only(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        starts = [e for e in events if isinstance(e, TextMessageStartEvent)]
        assert len(starts) == 3
        assert starts[0].name == "Researcher"
        assert starts[1].name == "Critic"
        assert starts[2].name == "Synthesizer"

    async def test_unknown_corpus_returns_no_events(self, corpora_config):
        """Unknown corpus slug yields zero events."""
        events = await collect_pipeline_events(corpora_config, slug="nonexistent")
        assert events == []


# ── Tracer bullet 2: tool call streaming ────────────────────────────────────


@pytest.fixture
def mock_tool_calls():
    """Set up model for tool-calling agent.

    Each agent needs two model calls:
      1. astream yields tool call chunks (first call, no ToolMessages yet)
      2. astream yields answer text (second call, after tool results fed back)

    Decision is data-driven: if ``messages`` already contains a ToolMessage
    (tool execution result from a previous iteration) the model streams text;
    otherwise it streams tool call chunks.  This mirrors real model behaviour
    where tool call IDs from streaming chunks are used for tool execution.

    3 agents × (tool-chunk stream + text stream) = 6 astream calls.
    """

    async def _astream_impl(messages, **kwargs):
        # Check if any prior tool result exists in the conversation
        has_tool_results = any(
            isinstance(m, ToolMessage) for m in messages
        )
        if not has_tool_results:
            # First call: tool call chunks
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "rag_search",
                        "args": '{"query":',
                        "id": "call-1",
                        "index": 0,
                    },
                ],
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": None, "args": '"EU AI Act"}', "id": None, "index": 0},
                ],
            )
        else:
            # Second call: answer text
            yield AIMessageChunk(content="Based on search results")
            yield AIMessageChunk(content=" EU AI Act affects...")

    async def _ainvoke_impl(messages):
        # Still needed by orchestrator if ainvoke is called directly anywhere
        # Return a consistent AIMessage that matches the streaming chunks.
        has_tool_results = any(
            isinstance(m, ToolMessage) for m in messages
        )
        if not has_tool_results:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "rag_search",
                        "args": {"query": "EU AI Act"},
                    }
                ],
            )
        else:
            return AIMessage(content="Based on search results EU AI Act affects...")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model

    yield _apply


class TestPipelineToolEvents:
    """run_pipeline() yields TOOL_CALL_* events alongside text."""

    async def test_emits_tool_call_events(
        self, corpora_config, mock_tool_calls, mock_model
    ):
        """Each of the 3 agents produces TOOL_CALL_START + 2×ARGS."""
        mock_tool_calls(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        tool_starts = [e for e in events if isinstance(e, ToolCallStartEvent)]
        assert len(tool_starts) == 3
        assert all(e.tool_call_id == "call-1" for e in tool_starts)
        assert all(e.tool_call_name == "rag_search" for e in tool_starts)

        tool_args = [e for e in events if isinstance(e, ToolCallArgsEvent)]
        assert len(tool_args) == 6  # 3 agents × 2 args chunks each
        assert all(a.tool_call_id == "call-1" for a in tool_args)

    async def test_emits_tool_result_events(
        self, corpora_config, mock_tool_calls, mock_model
    ):
        """Each agent produces TOOL_CALL_END + TOOL_CALL_RESULT."""
        mock_tool_calls(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        ends = [e for e in events if isinstance(e, ToolCallEndEvent)]
        assert len(ends) == 3  # 3 agents

        results = [e for e in events if isinstance(e, ToolCallResultEvent)]
        assert len(results) == 3
        assert all(r.tool_call_id == "call-1" for r in results)
        # Tool result content comes from the real tool execution (which
        # uses the fake sessionmaker); just verify it's non-empty.
        assert all(len(r.content) > 0 for r in results)

    async def test_full_tool_sequence(
        self, corpora_config, mock_tool_calls, mock_model
    ):
        """Verify complete event sequence for tool-using agent across 3 agents."""
        mock_tool_calls(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        types = [type(e).__name__ for e in events]
        # TEXT_MESSAGE_START is emitted before tool calls so the frontend
        # has a UIMessage to route everything to.
        # Per agent:
        #   TextMessageStart + ToolCallStart + ToolCallArgs×2 +
        #   ToolCallEnd + ToolCallResult + TextMessageContent×2 +
        #   TextMessageEnd
        assert types == [
            "RunStartedEvent",
            # Researcher
            "TextMessageStartEvent",
            "ToolCallStartEvent",
            "ToolCallArgsEvent",
            "ToolCallArgsEvent",
            "ToolCallEndEvent",
            "ToolCallResultEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            # Critic
            "TextMessageStartEvent",
            "ToolCallStartEvent",
            "ToolCallArgsEvent",
            "ToolCallArgsEvent",
            "ToolCallEndEvent",
            "ToolCallResultEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            # Synthesizer
            "TextMessageStartEvent",
            "ToolCallStartEvent",
            "ToolCallArgsEvent",
            "ToolCallArgsEvent",
            "ToolCallEndEvent",
            "ToolCallResultEvent",
            "TextMessageContentEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]


# ── Tracer bullet 3: reasoning content streaming ────────────────────────────


@pytest.fixture
def mock_reasoning():
    """Set up model for reasoning + text agent calls."""
    call_count: list[int] = [0]

    async def _astream_impl(messages, **kwargs):
        yield AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "Let me think about "},
        )
        yield AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "the EU AI Act"},
        )
        yield AIMessageChunk(content="Here is my analysis")

    async def _ainvoke_impl(messages):
        call_count[0] += 1
        return AIMessage(content="Here is my analysis")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model

    yield _apply


class TestPipelineReasoningEvents:
    """run_pipeline() yields REASONING_MESSAGE_* events."""

    async def test_emits_reasoning_events(
        self, corpora_config, mock_reasoning, mock_model
    ):
        """Each of the 3 agents produces reasoning START/CONTENT×2/END."""
        mock_reasoning(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        starts = [e for e in events if isinstance(e, ReasoningMessageStartEvent)]
        assert len(starts) == 3  # 3 agents each reason

        contents = [e for e in events if isinstance(e, ReasoningMessageContentEvent)]
        assert len(contents) == 6  # 3 agents × 2 chunks each
        assert contents[0].delta == "Let me think about "
        assert contents[1].delta == "the EU AI Act"

        ends = [e for e in events if isinstance(e, ReasoningMessageEndEvent)]
        assert len(ends) == 3

    async def test_full_reasoning_sequence(
        self, corpora_config, mock_reasoning, mock_model
    ):
        """Verify complete event sequence for reasoning + answer."""
        mock_reasoning(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        types = [type(e).__name__ for e in events]
        # Each of the 3 agents produces:
        #   TextMessageStartEvent (before StepStartedEvent so the frontend
        #     has a UIMessage to route all content to),
        #   StepStartedEvent, ReasoningMessageStartEvent,
        #   ReasoningMessageContentEvent×2, ReasoningMessageEndEvent,
        #   TextMessageContentEvent×1, TextMessageEndEvent
        assert types == [
            "RunStartedEvent",
            # Researcher
            "TextMessageStartEvent",
            "StepStartedEvent",
            "ReasoningMessageStartEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageEndEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            # Critic
            "TextMessageStartEvent",
            "StepStartedEvent",
            "ReasoningMessageStartEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageEndEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            # Synthesizer
            "TextMessageStartEvent",
            "StepStartedEvent",
            "ReasoningMessageStartEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageContentEvent",
            "ReasoningMessageEndEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]


# ── Tracer bullet 4: error handling ────────────────────────────────────────


@pytest.fixture
def mock_crash():
    """Set up model so the first agent crashes mid-stream."""
    call_count: list[int] = [0]

    async def _astream_impl(messages, **kwargs):
        idx = call_count[0]
        # First call: crash
        if idx == 0:
            yield AIMessageChunk(content="Before crash")
            raise RuntimeError("API failure")
        # Subsequent calls should not be reached
        yield AIMessageChunk(content="Should not reach")

    async def _ainvoke_impl(messages):
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            return AIMessage(content="Before crash")
        return AIMessage(content="Should not reach")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model

    yield _apply


class TestPipelineErrors:
    """run_pipeline() handles errors gracefully."""

    async def test_emits_run_error_on_crash(
        self, corpora_config, mock_crash, mock_model
    ):
        """When agent crashes, pipeline yields RUN_ERROR (not RUN_FINISHED)."""
        mock_crash(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        errors = [e for e in events if isinstance(e, RunErrorEvent)]
        assert len(errors) == 1
        assert "API failure" in errors[0].message

    async def test_crash_does_not_emit_run_finished(
        self, corpora_config, mock_crash, mock_model
    ):
        """When agent crashes, no RUN_FINISHED event."""
        mock_crash(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        finished = [e for e in events if isinstance(e, RunFinishedEvent)]
        assert len(finished) == 0

    async def test_text_block_closed_before_error(
        self, corpora_config, mock_crash, mock_model
    ):
        """Open text block is closed before RUN_ERROR."""
        mock_crash(mock_model)
        events = await collect_pipeline_events(corpora_config, model=mock_model)

        ends = [e for e in events if isinstance(e, TextMessageEndEvent)]
        assert len(ends) == 1

        error_idx = next(
            i for i, e in enumerate(events) if isinstance(e, RunErrorEvent)
        )
        end_idx = next(
            i for i, e in enumerate(events) if isinstance(e, TextMessageEndEvent)
        )
        assert end_idx < error_idx


# ── Helper ───────────────────────────────────────────────────────────────────


async def collect_pipeline_events(
    corpora_config: CorporaConfig,
    slug: str = "eu-ai-act",
    model=None,
) -> list[object]:
    """Collect pipeline events into a list."""
    from backend.agents.graph_orchestrator import run_orchestrator
    from backend.config import Settings

    settings = Settings(demo_disable_budget=True)  # no /data/ needed

    corpus = corpora_config.get(slug)
    if corpus is None:
        return []

    events: list[object] = []
    async for event in run_orchestrator(
        messages=[{"role": "user", "content": "test"}],
        corpus_id=corpus.id,
        corpus_name=corpus.name,
        settings=settings,
        thread_id="th-default",
        run_id="run-default",
        model=model,
    ):
        events.append(event)
    return events
