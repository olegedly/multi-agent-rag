"""Prove that reasoning_content survives from OpenAI delta to AIMessageChunk.

When the OpenAI-compatible API returns streaming chunks with ``reasoning_content``
in the delta, LangChain's ``_convert_delta_to_message_chunk`` silently drops it.
The monkey-patch in ``backend/agents/__init__.py`` preserves it in
``additional_kwargs`` so our stream handler can emit REASONING_MESSAGE_* events.
"""

from __future__ import annotations

import pytest  # pyright: ignore[reportUnusedImport]
from langchain_core.messages import AIMessageChunk

# Import agents package first to trigger the monkey-patch
import backend.agents  # pyright: ignore[reportUnusedImport]

from langchain_openai.chat_models.base import _convert_delta_to_message_chunk  # noqa: E402


class TestReasoningContentSurvival:
    """_convert_delta_to_message_chunk must preserve reasoning_content (post-patch)."""

    def test_reasoning_content_survives(self):
        """The patch preserves reasoning_content from the delta dict."""
        delta_dict = {
            "content": "",
            "role": "assistant",
            "reasoning_content": "Let me think about this carefully...",
        }
        result = _convert_delta_to_message_chunk(delta_dict, AIMessageChunk)
        reasoning = result.additional_kwargs.get("reasoning_content", "")
        assert reasoning == "Let me think about this carefully..."

    def test_reasoning_content_in_empty_chunk(self):
        """A chunk with only reasoning_content and empty content."""
        delta_dict = {
            "content": None,
            "role": "assistant",
            "reasoning_content": "Reasoning step one.",
        }
        result = _convert_delta_to_message_chunk(delta_dict, AIMessageChunk)
        reasoning = result.additional_kwargs.get("reasoning_content", "")
        assert reasoning == "Reasoning step one."

    def test_reasoning_content_alongside_function_call(self):
        """Both function_call and reasoning_content coexist."""
        delta_dict = {
            "content": "",
            "role": "assistant",
            "reasoning_content": "Should I search?",
            "function_call": {"name": "rag_search", "arguments": '{"query":"test"}'},
        }
        result = _convert_delta_to_message_chunk(delta_dict, AIMessageChunk)
        assert result.additional_kwargs.get("reasoning_content") == "Should I search?"
        assert result.additional_kwargs.get("function_call") is not None

    def test_no_reasoning_content_is_fine(self):
        """Chunks without reasoning_content should work normally."""
        delta_dict = {
            "content": "Hello world",
            "role": "assistant",
        }
        result = _convert_delta_to_message_chunk(delta_dict, AIMessageChunk)
        assert "reasoning_content" not in result.additional_kwargs
        assert result.content == "Hello world"

    def test_end_to_end_stream_handler_sees_reasoning(self):
        """StreamEventHandler picks up reasoning from the model's chunk."""
        from backend.agents.stream_handler import StreamEventHandler
        from ag_ui.core.events import ReasoningMessageStartEvent, ReasoningMessageContentEvent

        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        handler.drain()  # discard RUN_STARTED

        # Simulate what arrives from the patched LangChain — an AIMessageChunk
        # with reasoning_content in additional_kwargs
        chunk = AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "Let me reason..."},
        )
        handler.observe(chunk, {"langgraph_node": "agent"})
        events = handler.drain()

        starts = [e for e in events if isinstance(e, ReasoningMessageStartEvent)]
        assert len(starts) == 1

        contents = [e for e in events if isinstance(e, ReasoningMessageContentEvent)]
        assert len(contents) == 1
        assert contents[0].delta == "Let me reason..."
