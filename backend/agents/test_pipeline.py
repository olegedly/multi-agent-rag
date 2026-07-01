"""Tests for the pipeline message conversion."""

from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from backend.agents.graph_orchestrator import _convert_dict_messages


def _as_lc(msgs: list[dict]) -> list[BaseMessage]:
    return _convert_dict_messages(msgs)


def _to_ai(msg: BaseMessage) -> AIMessage:
    return cast(AIMessage, msg)


def _to_tool(msg: BaseMessage) -> ToolMessage:
    return cast(ToolMessage, msg)


class TestConvertDictMessages:
    """`_convert_dict_messages` must preserve tool_calls on assistant messages."""

    def test_roundtrip_simple(self):
        """A simple user->assistant round trip."""
        msgs = [
            {"role": "user", "content": "Hello", "id": "u1"},
            {"role": "assistant", "content": "Hi there!", "id": "a1"},
        ]
        lc = _as_lc(msgs)
        assert len(lc) == 2
        assert lc[0].type == "human"
        assert lc[1].type == "ai"

    def test_follow_up_with_tool_calls(self):
        """A second query includes history with tool_calls from the first round.

        A follow-up query must preserve the assistant's toolCalls so that
        the LLM sees the tool-result with a matching tool_call_id.
        """
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "What is the EU AI Act?", "id": "u1"},
            {
                "role": "assistant",
                "content": "The EU AI Act is a regulation...",
                "id": "a1",
                "toolCalls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "rag_search",
                            "arguments": '{"query":"EU AI Act","top_k":5}',
                        },
                    },
                ],
            },
            {
                "role": "tool",
                "toolCallId": "call-1",
                "content": '{"results": [], "error": null}',
                "id": "tool-call-1",
            },
            {"role": "user", "content": "Tell me more", "id": "u2"},
        ]

        lc = _as_lc(msgs)
        assert len(lc) == 4

        # Assistant message must carry tool_calls
        ai_msg = _to_ai(lc[1])
        assert len(ai_msg.tool_calls) == 1
        assert ai_msg.tool_calls[0]["id"] == "call-1"
        assert ai_msg.tool_calls[0]["name"] == "rag_search"

        # Tool message must have tool_call_id
        tool_msg = _to_tool(lc[2])
        assert tool_msg.tool_call_id == "call-1"

    def test_multiple_tool_calls_in_one_message(self):
        """Assistant with multiple tool calls."""
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "Research", "id": "u1"},
            {
                "role": "assistant",
                "content": "Let me look that up",
                "id": "a1",
                "toolCalls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "rag_search", "arguments": "{}"},
                    },
                    {
                        "id": "call-2",
                        "type": "function",
                        "function": {"name": "rag_read_document", "arguments": "{}"},
                    },
                ],
            },
        ]
        lc = _as_lc(msgs)
        ai_msg = _to_ai(lc[1])
        assert len(ai_msg.tool_calls) == 2
        assert ai_msg.tool_calls[0]["id"] == "call-1"
        assert ai_msg.tool_calls[1]["id"] == "call-2"

    def test_assistant_without_tool_calls(self):
        """Assistant message without toolCalls should still work."""
        msgs = [
            {"role": "user", "content": "Hi", "id": "u1"},
            {"role": "assistant", "content": "Hello!", "id": "a1"},
        ]
        lc = _as_lc(msgs)
        ai_msg = _to_ai(lc[1])
        assert len(ai_msg.tool_calls) == 0

    def test_tool_message_has_tool_call_id(self):
        """A tool message preserves its tool_call_id."""
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "Hi", "id": "u1"},
            {
                "role": "assistant",
                "content": "Let me check",
                "id": "a1",
                "toolCalls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "rag_search", "arguments": "{}"},
                    },
                ],
            },
            {
                "role": "tool",
                "toolCallId": "call-1",
                "content": "results",
                "id": "tool-call-1",
            },
        ]
        lc = _as_lc(msgs)
        tool_msg = _to_tool(lc[2])
        assert tool_msg.tool_call_id == "call-1"
        assert tool_msg.content == "results"
