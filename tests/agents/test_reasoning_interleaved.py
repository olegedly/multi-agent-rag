"""Tests for interleaved reasoning blocks across tool call boundaries.

When the agent reasons, calls a tool, receives the result, then reasons
again, each reasoning phase should produce a separate REASONING_MESSAGE
block — not all accumulate into one.

The frontend's StreamProcessor ignores REASONING_MESSAGE_START/END
(both no-ops). Separate thinking steps are keyed by stepId, which
must be set via STEP_STARTED events.
"""

from __future__ import annotations

import pytest
from ag_ui.core.events import (
    ReasoningMessageContentEvent,
    StepStartedEvent,
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

    # ── Tracer bullet 1: STEP_STARTED emitted per reasoning block ─────

    def test_each_reasoning_block_emits_step_started(self, handler):
        """STEP_STARTED with a unique step_id is emitted before each
        reasoning block, so the frontend creates separate ThinkingPart
        components."""
        # Phase 1: first reasoning block
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Think 1"}),
            {"langgraph_node": "agent"},
        )
        phase1 = handler.drain()

        step_starts = [e for e in phase1 if isinstance(e, StepStartedEvent)]
        assert len(step_starts) == 1
        sid1 = getattr(step_starts[0], "stepId", "")
        assert sid1, "STEP_STARTED must carry a stepId"

        # Phase 2: tool call + result
        handler.observe(
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"id": "c1", "name": "t", "args": "{}", "index": 0}],
            ),
            {"langgraph_node": "agent"},
        )
        handler.drain()
        handler.observe(ToolMessage(content="ok", tool_call_id="c1"), {"langgraph_node": "tools"})
        handler.drain()  # end events

        # Phase 3: second reasoning block
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Think 2"}),
            {"langgraph_node": "agent"},
        )
        phase3 = handler.drain()

        step_starts2 = [e for e in phase3 if isinstance(e, StepStartedEvent)]
        assert len(step_starts2) == 1
        sid2 = getattr(step_starts2[0], "stepId", "")
        assert sid2, "Second STEP_STARTED must carry a stepId"
        assert sid2 != sid1, "Each STEP_STARTED must have a unique stepId"

    # ── Tracer bullet 2: content events carry step_id ─────────────────

    def test_reasoning_content_carries_step_id(self, handler):
        """REASONING_MESSAGE_CONTENT events carry a step_id distinct
        from message_id, set by the STEP_STARTED emitted before them."""
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Hello"}),
            {"langgraph_node": "agent"},
        )
        events = handler.drain()

        contents = [e for e in events if isinstance(e, ReasoningMessageContentEvent)]
        assert len(contents) == 1
        step_id = getattr(contents[0], "stepId", "")
        assert step_id, "Content event must carry stepId"
        assert step_id != "msg-1", "stepId must differ from messageId"

    # ── Tracer bullet 3: stepId changes across blocks ─────────────────

    def test_step_id_changes_across_reasoning_blocks(self, handler):
        """stepId on content events changes when a new reasoning block
        opens after a tool result, ensuring the frontend creates a
        second ThinkingPart."""
        # Block 1
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "A"}),
            {"langgraph_node": "agent"},
        )
        phase1 = handler.drain()
        step_id_1 = getattr(
            [e for e in phase1 if isinstance(e, ReasoningMessageContentEvent)][0],
            "stepId", "",
        )

        # Tool call + result
        handler.observe(
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"id": "c1", "name": "t", "args": "{}", "index": 0}],
            ),
            {"langgraph_node": "agent"},
        )
        handler.drain()
        handler.observe(ToolMessage(content="ok", tool_call_id="c1"), {"langgraph_node": "tools"})
        handler.drain()

        # Block 2
        handler.observe(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "B"}),
            {"langgraph_node": "agent"},
        )
        phase2 = handler.drain()
        step_id_2 = getattr(
            [e for e in phase2 if isinstance(e, ReasoningMessageContentEvent)][0],
            "stepId", "",
        )

        assert step_id_1 != "", "First stepId must be present"
        assert step_id_2 != "", "Second stepId must be present"
        assert step_id_2 != step_id_1, "stepId must change across reasoning blocks"
