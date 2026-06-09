"""Tests for StreamEventHandler — streaming AG-UI event builder.

Exercises the observe()/drain()/finalize()/error() lifecycle with
real ``AIMessageChunk`` and ``ToolMessage`` instances.
"""

from __future__ import annotations

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

from backend.agents.stream_handler import StreamEventHandler


# ── Tracer bullet 1: construction gates RUN_STARTED ─────────────────────────


class TestConstruction:
    """StreamEventHandler buffers RUN_STARTED on construction."""

    def test_drain_returns_run_started(self):
        """First drain yields exactly one RunStartedEvent."""
        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        events = handler.drain()
        assert len(events) == 1
        first = events[0]
        assert isinstance(first, RunStartedEvent)
        assert first.thread_id == "th-1"
        assert first.run_id == "run-1"

    def test_second_drain_is_empty(self):
        """Second drain (without observe) returns nothing."""
        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        handler.drain()  # RUN_STARTED
        assert handler.drain() == []


# ── Tracer bullet 2: text message chunks ──────────────────────────────────


class TestTextMessages:
    """AIMessageChunk with content yields TEXT_MESSAGE_* events."""

    @pytest.fixture
    def handler(self):
        h = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        h.drain()  # discard RUN_STARTED
        return h

    def test_first_chunk_emits_start_and_content(self, handler):
        """First text chunk opens a text message block."""
        chunk = AIMessageChunk(content="Hello")
        handler.observe(chunk, {"langgraph_node": "agent"})
        events = handler.drain()

        # START + CONTENT
        assert len(events) >= 2
        assert isinstance(events[0], TextMessageStartEvent)
        assert events[0].message_id == "msg-1"
        assert events[0].role == "assistant"

        assert isinstance(events[1], TextMessageContentEvent)
        assert events[1].delta == "Hello"

    def test_subsequent_chunks_emits_only_content(self, handler):
        """Subsequent text chunks only emit CONTENT events."""
        handler.observe(AIMessageChunk(content="Hello "), {"langgraph_node": "agent"})
        handler.drain()  # START + first CONTENT

        handler.observe(AIMessageChunk(content="world"), {"langgraph_node": "agent"})
        events = handler.drain()

        assert len(events) == 1
        assert isinstance(events[0], TextMessageContentEvent)
        assert events[0].delta == "world"

    def test_text_events_have_message_id(self, handler):
        """All text events carry the same message_id."""
        handler.observe(AIMessageChunk(content="Hello"), {"langgraph_node": "agent"})
        handler.observe(AIMessageChunk(content=" world"), {"langgraph_node": "agent"})
        events = handler.drain()

        for e in events:
            if hasattr(e, "message_id"):
                assert e.message_id == "msg-1"

    def test_empty_content_emits_no_text_events(self, handler):
        """AIMessageChunk with empty content yields nothing."""
        chunk = AIMessageChunk(content="")
        handler.observe(chunk, {"langgraph_node": "agent"})
        assert handler.drain() == []


# ── Tracer bullet 3: tool call chunks ─────────────────────────────────────


class TestToolCalls:
    """AIMessageChunk with tool_call_chunks yields TOOL_CALL_* events."""

    @pytest.fixture
    def handler(self):
        h = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        h.drain()
        return h

    def test_new_tool_call_emits_start_and_args(self, handler):
        """First tool call chunk for a new id emits START + ARGS."""
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": '{"query":', "id": "call-1", "index": 0},
            ],
        )
        handler.observe(chunk, {"langgraph_node": "agent"})
        events = handler.drain()

        assert len(events) >= 2
        start = events[0]
        assert isinstance(start, ToolCallStartEvent)
        assert start.tool_call_id == "call-1"
        assert start.tool_call_name == "rag_search"

        args = events[1]
        assert isinstance(args, ToolCallArgsEvent)
        assert args.tool_call_id == "call-1"
        assert args.delta == '{"query":'

    def test_subsequent_tool_call_emits_only_args(self, handler):
        """Subsequent chunk for same id emits only ARGS."""
        chunk1 = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": '{"query":', "id": "call-1", "index": 0},
            ],
        )
        handler.observe(chunk1, {"langgraph_node": "agent"})
        handler.drain()  # START + first ARGS

        chunk2 = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": None, "args": '"EU AI Act"}', "id": "call-1", "index": 0},
            ],
        )
        handler.observe(chunk2, {"langgraph_node": "agent"})
        events = handler.drain()

        assert len(events) == 1
        assert isinstance(events[0], ToolCallArgsEvent)
        assert events[0].tool_call_id == "call-1"
        assert events[0].delta == '"EU AI Act"}'

    def test_tool_result_emits_end_and_result(self, handler):
        """ToolMessage for tracked id emits END + RESULT."""
        # Simulate tool call that was started
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": "{}", "id": "call-1", "index": 0},
            ],
        )
        handler.observe(chunk, {"langgraph_node": "agent"})
        handler.drain()  # START + ARGS

        result = ToolMessage(
            content="Found 3 results",
            tool_call_id="call-1",
        )
        handler.observe(result, {"langgraph_node": "tools"})
        events = handler.drain()

        assert len(events) >= 2
        end = events[0]
        assert isinstance(end, ToolCallEndEvent)
        assert end.tool_call_id == "call-1"

        res = events[1]
        assert isinstance(res, ToolCallResultEvent)
        assert res.tool_call_id == "call-1"
        assert res.content == "Found 3 results"

    def test_multiple_concurrent_tool_calls(self, handler):
        """Multiple tool call ids are tracked independently."""
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": '{"query":', "id": "call-1", "index": 0},
                {"name": "rag_read_document", "args": '{"chunk', "id": "call-2", "index": 1},
            ],
        )
        handler.observe(chunk, {"langgraph_node": "agent"})
        events = handler.drain()

        starts = [e for e in events if isinstance(e, ToolCallStartEvent)]
        assert len(starts) == 2
        assert starts[0].tool_call_id == "call-1"
        assert starts[1].tool_call_id == "call-2"

    def test_merged_chunk_without_id_resolves_via_index(self, handler):
        """Chunks with id=None but index+args resolve via last known id."""
        # First chunk establishes id for index 0
        chunk1 = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": "", "id": "call-m1", "index": 0},
            ],
        )
        handler.observe(chunk1, {"langgraph_node": "agent"})
        handler.drain()  # START + (empty) ARGS

        # LangGraph merges by index — subsequent chunk has id=None
        chunk2 = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": None, "args": '{"query":"test"}', "id": None, "index": 0},
            ],
        )
        handler.observe(chunk2, {"langgraph_node": "agent"})
        events = handler.drain()

        # Should emit ARGS with the resolved id, not empty string
        assert len(events) == 1
        assert isinstance(events[0], ToolCallArgsEvent)
        assert events[0].tool_call_id == "call-m1"
        assert events[0].delta == '{"query":"test"}'


# ── Tracer bullet 4: reasoning content ────────────────────────────────────


class TestReasoning:
    """AIMessageChunk with reasoning_content yields REASONING_MESSAGE_* events."""

    @pytest.fixture
    def handler(self):
        h = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        h.drain()
        return h

    def test_reasoning_opens_block(self, handler):
        """Chunks with reasoning_content emit REASONING_MESSAGE_START + CONTENT."""
        chunk = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Let me think"})
        handler.observe(chunk, {"langgraph_node": "agent"})
        events = handler.drain()

        assert len(events) >= 2
        start = events[0]
        assert isinstance(start, ReasoningMessageStartEvent)
        assert start.message_id is not None

        content = events[1]
        assert isinstance(content, ReasoningMessageContentEvent)
        assert content.delta == "Let me think"

    def test_reasoning_without_reasoning_content_does_nothing(self, handler):
        """Chunk without reasoning_content attribute emits nothing."""
        chunk = AIMessageChunk(content="Hello")
        handler.observe(chunk, {"langgraph_node": "agent"})
        # Should emit text events, not reasoning
        events = handler.drain()
        assert all(not isinstance(e, ReasoningMessageStartEvent) for e in events)
        assert all(not isinstance(e, ReasoningMessageContentEvent) for e in events)

    def test_subsequent_reasoning_only_content(self, handler):
        """Second reasoning chunk emits only CONTENT."""
        chunk1 = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Let me "})
        handler.observe(chunk1, {"langgraph_node": "agent"})
        handler.drain()

        chunk2 = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "think"})
        handler.observe(chunk2, {"langgraph_node": "agent"})
        events = handler.drain()

        assert len(events) == 1
        assert isinstance(events[0], ReasoningMessageContentEvent)
        assert events[0].delta == "think"

    def test_reasoning_then_text(self, handler):
        """Reasoning block closes when text starts."""
        chunk1 = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Hmm"})
        handler.observe(chunk1, {"langgraph_node": "agent"})
        handler.drain()  # START + CONTENT

        chunk2 = AIMessageChunk(content="Answer here")
        handler.observe(chunk2, {"langgraph_node": "agent"})
        events = handler.drain()

        # Should see REASONING_MESSAGE_END + TEXT_MESSAGE_START + CONTENT
        end_events = [e for e in events if isinstance(e, ReasoningMessageEndEvent)]
        assert len(end_events) == 1
        text_starts = [e for e in events if isinstance(e, TextMessageStartEvent)]
        assert len(text_starts) == 1


# ── Tracer bullet 5: finalize() ───────────────────────────────────────────


class TestFinalize:
    """finalize() closes any open blocks and emits RUN_FINISHED."""

    def test_finalize_on_empty(self):
        """finalize with no activity emits RUN_FINISHED."""
        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        handler.drain()  # RUN_STARTED
        events = handler.finalize()

        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.thread_id == "th-1"
        assert last.run_id == "run-1"

    def test_finalize_closes_text_block(self, handler):
        """Open text block gets TEXT_MESSAGE_END before RUN_FINISHED."""
        handler.observe(AIMessageChunk(content="Hi"), {"langgraph_node": "agent"})
        handler.drain()  # START + CONTENT
        events = handler.finalize()

        ends = [e for e in events if isinstance(e, TextMessageEndEvent)]
        assert len(ends) == 1
        assert events[-1] is not ends[0]  # RUN_FINISHED is last

    def test_finalize_closes_reasoning_block(self, handler):
        """Open reasoning block gets REASONING_MESSAGE_END before RUN_FINISHED."""
        chunk = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Hmm"})
        handler.observe(chunk, {"langgraph_node": "agent"})
        handler.drain()
        events = handler.finalize()

        ends = [e for e in events if isinstance(e, ReasoningMessageEndEvent)]
        assert len(ends) == 1

    def test_finalize_closes_tool_calls(self, handler):
        """Open tool call gets TOOL_CALL_END before RUN_FINISHED."""
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "rag_search", "args": "{}", "id": "call-1", "index": 0},
            ],
        )
        handler.observe(chunk, {"langgraph_node": "agent"})
        handler.drain()
        events = handler.finalize()

        ends = [e for e in events if isinstance(e, ToolCallEndEvent)]
        assert len(ends) == 1

    @pytest.fixture
    def handler(self):
        h = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        h.drain()
        return h


# ── Tracer bullet 6: error() ──────────────────────────────────────────────


class TestError:
    """error() closes blocks and emits RUN_ERROR."""

    def test_error_emits_run_error(self):
        """error() yields RUN_ERROR as last event."""
        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        handler.drain()
        events = handler.error("Something broke")
        last = events[-1]
        assert isinstance(last, RunErrorEvent)
        assert last.message == "Something broke"

    def test_error_closes_open_text_block(self):
        """Open text block closes before RUN_ERROR."""
        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        handler.drain()
        handler.observe(AIMessageChunk(content="Hi"), {"langgraph_node": "agent"})
        handler.drain()
        events = handler.error("Boom")

        ends = [e for e in events if isinstance(e, TextMessageEndEvent)]
        assert len(ends) == 1
        assert isinstance(events[-1], RunErrorEvent)
