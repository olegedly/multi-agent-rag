"""Prove that reasoning_content survives from OpenAI streaming chunks to AIMessageChunk.

When the OpenAI-compatible API returns streaming chunks with ``reasoning_content``
at the **choice** level (not inside delta), LangChain's
``_convert_chunk_to_generation_chunk`` only passes ``choice["delta"]`` to
``_convert_delta_to_message_chunk`` — so reasoning_content is silently dropped.

The monkey-patch in ``backend/agents/__init__.py`` patches both:
1. ``_convert_delta_to_message_chunk`` — defense in depth.
2. ``BaseChatOpenAI._convert_chunk_to_generation_chunk`` — the real fix that
   extracts reasoning_content from the choice dict.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest  # pyright: ignore[reportUnusedImport]
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

# Import agents package first to trigger the monkey-patch
import backend.agents  # pyright: ignore[reportUnusedImport]

from langchain_openai.chat_models.base import (  # noqa: E402
    BaseChatOpenAI,
    _convert_delta_to_message_chunk,
)


class TestDeltaPatches:
    """_convert_delta_to_message_chunk defense-in-depth patch."""

    def test_reasoning_content_in_delta(self):
        """Delta-level patch preserves reasoning_content from delta dict."""
        delta_dict = {
            "content": "",
            "role": "assistant",
            "reasoning_content": "Let me think...",
        }
        result = _convert_delta_to_message_chunk(delta_dict, AIMessageChunk)
        reasoning = result.additional_kwargs.get("reasoning_content", "")
        assert reasoning == "Let me think..."

    def test_no_reasoning_content_is_fine(self):
        """Chunks without reasoning_content should work normally."""
        delta_dict = {"content": "Hello world", "role": "assistant"}
        result = _convert_delta_to_message_chunk(delta_dict, AIMessageChunk)
        assert "reasoning_content" not in result.additional_kwargs
        assert result.content == "Hello world"


class TestChunkPatches:
    """_convert_chunk_to_generation_chunk patch — reasoning at choice level."""

    @staticmethod
    def _call_convert_chunk(
        chunk: dict,
        default_chunk_class: type = AIMessageChunk,
    ) -> ChatGenerationChunk | None:
        """Call the patched _convert_chunk_to_generation_chunk directly.

        Uses a MagicMock as ``self`` so we don't need API keys.
        """
        mock_self = MagicMock(spec=BaseChatOpenAI)
        return BaseChatOpenAI._convert_chunk_to_generation_chunk(  # type: ignore[arg-type]
            mock_self,
            chunk,
            default_chunk_class,
            None,
        )

    def test_reasoning_content_at_choice_level(self):
        """The chunk-level patch extracts reasoning_content from the choice dict."""
        chunk = {
            "choices": [{
                "delta": {"content": "", "role": "assistant"},
                "finish_reason": None,
                "index": 0,
                "reasoning_content": "Thinking step one...",
            }],
        }
        result = self._call_convert_chunk(chunk)
        assert result is not None
        msg = result.message
        assert msg.additional_kwargs.get("reasoning_content") == "Thinking step one..."

    def test_no_reasoning_content_at_choice_level(self):
        """Chunks without reasoning_content at choice level work normally."""
        chunk = {
            "choices": [{
                "delta": {"content": "Hello world", "role": "assistant"},
                "finish_reason": None,
                "index": 0,
            }],
        }
        result = self._call_convert_chunk(chunk)
        assert result is not None
        assert "reasoning_content" not in result.message.additional_kwargs
        assert result.message.content == "Hello world"

    def test_empty_choices_is_fine(self):
        """Chunks with empty choices list don't crash."""
        chunk = {"choices": []}
        mock_self = MagicMock(spec=BaseChatOpenAI)
        mock_self.output_version = None
        result = BaseChatOpenAI._convert_chunk_to_generation_chunk(  # type: ignore[arg-type]
            mock_self, chunk, AIMessageChunk, None,
        )
        assert result is not None

    def test_reasoning_content_with_tool_calls(self):
        """reasoning_content coexists with tool calls."""
        chunk = {
            "choices": [{
                "delta": {
                    "content": "",
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {"name": "rag_search", "arguments": '{"q":"test"}'},
                        },
                    ],
                },
                "finish_reason": None,
                "index": 0,
                "reasoning_content": "Should I search?",
            }],
        }
        result = self._call_convert_chunk(chunk)
        assert result is not None
        msg = result.message
        assert msg.additional_kwargs.get("reasoning_content") == "Should I search?"
        assert len(cast("AIMessageChunk", msg).tool_call_chunks) == 1

    def test_end_to_end_stream_handler_sees_reasoning(self):
        """StreamEventHandler picks up reasoning from the patched chunk."""
        from backend.agents.stream_handler import StreamEventHandler
        from ag_ui.core.events import ReasoningMessageStartEvent, ReasoningMessageContentEvent

        handler = StreamEventHandler(
            thread_id="th-1", run_id="run-1", message_id="msg-1",
        )
        handler.drain()  # discard RUN_STARTED

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
