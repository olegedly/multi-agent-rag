"""Tests for interleaved reasoning blocks across tool call boundaries.

When the agent reasons, calls a tool, receives the result, then reasons
again, each reasoning phase should produce a separate REASONING_MESSAGE
block — not all accumulate into one.
"""

from __future__ import annotations

import pytest
from ag_ui.core.events import (
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
)
from langchain_core.messages import AIMessageChunk, ToolMessage

from backend.agents.stream_handler import StreamEventHandler


class TestInterleavedReasoning:
    """Reasoning blocks should open/close across tool call boundaries."""

    @pytest.fixture
    def handler(self):
        h = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        h.drain()  # discard RUN_STARTED
        return h

    # ── Tracer bullet 1 ───────────────────────────────────────────────

    def test_new_reasoning_block_after_tool_result(self, handler):
        """When reasoning is open, then a tool call and its result arrive,
        then new reasoning arrives, the new reasoning starts a fresh block
        instead of appending to the old one.
        """
        # Phase 1: first reasoning block
        chunk1 = AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "Let me search for that..."},
        )
        handler.observe(chunk1, {"langgraph_node": "agent"})
        phase1 = handler.drain()

        starts1 = [e for e in phase1 if isinstance(e, ReasoningMessageStartEvent)]
        assert len(starts1) == 1, "First reasoning should open a block"

        # Phase 2: tool call
        chunk2 = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"id": "call-1", "name": "rag_search", "args": '{"query":"test"}', "index": 0},
            ],
        )
        handler.observe(chunk2, {"langgraph_node": "agent"})
        handler.drain()  # tool call events, irrelevant for this test

        # Phase 3: tool result arrives
        result = ToolMessage(content="Found 3 documents", tool_call_id="call-1")
        handler.observe(result, {"langgraph_node": "tools"})
        phase3 = handler.drain()

        # The tool result should close the reasoning block
        end_events = [e for e in phase3 if isinstance(e, ReasoningMessageEndEvent)]
        assert len(end_events) == 1, (
            "Tool result should close the open reasoning block"
        )

        # Phase 4: second reasoning block
        chunk4 = AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "Now I can answer..."},
        )
        handler.observe(chunk4, {"langgraph_node": "agent"})
        phase4 = handler.drain()

        # Second reasoning should open a NEW block (separate from the first)
        starts2 = [e for e in phase4 if isinstance(e, ReasoningMessageStartEvent)]
        assert len(starts2) == 1, "Second reasoning should open a new block"

        contents2 = [e for e in phase4 if isinstance(e, ReasoningMessageContentEvent)]
        assert len(contents2) == 1
        assert contents2[0].delta == "Now I can answer..."

    # ── Tracer bullet 2 ───────────────────────────────────────────────

    def test_multiple_reasoning_blocks_have_separate_end_events(self, handler):
        """Each reasoning block gets its own END before the next START."""
        # Block 1: reasoning
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Think 1"}),
            {"langgraph_node": "agent"},
        )
        handler.drain()  # START + CONTENT

        # Tool call + result (closes reasoning)
        handler.observe(
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"id": "c1", "name": "t", "args": "{}", "index": 0}],
            ),
            {"langgraph_node": "agent"},
        )
        handler.drain()
        handler.observe(ToolMessage(content="ok", tool_call_id="c1"), {"langgraph_node": "tools"})
        phase1_end = handler.drain()

        ends_after_result = [e for e in phase1_end if isinstance(e, ReasoningMessageEndEvent)]
        assert len(ends_after_result) == 1

        # Block 2: reasoning
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Think 2"}),
            {"langgraph_node": "agent"},
        )
        phase2 = handler.drain()

        starts2 = [e for e in phase2 if isinstance(e, ReasoningMessageStartEvent)]
        assert len(starts2) == 1

        # Block 2 gets its own end via close reasoning later
        handler.observe(AIMessageChunk(content="Final answer"), {"langgraph_node": "agent"})
        final_events = handler.drain()

        ends2 = [e for e in final_events if isinstance(e, ReasoningMessageEndEvent)]
        assert len(ends2) == 1, "Second reasoning block should also get an END"
