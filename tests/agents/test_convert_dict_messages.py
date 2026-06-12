"""Tests for _convert_dict_messages — AG-UI wire format → LangChain messages.

The key invariant: an assistant message with `tool_calls` must either be
followed by corresponding `ToolMessage`s, or the orphaned tool-calls
must be stripped to avoid a 400 from the LLM provider.
"""

from langchain_core.messages import AIMessage

from backend.agents.pipeline import _convert_dict_messages


def _as_ai(msg: object) -> AIMessage:
    """Cast a BaseMessage to AIMessage so pyright permits .tool_calls."""
    assert isinstance(msg, AIMessage), f"Expected AIMessage, got {type(msg)}"
    return msg


def _tool_call_agent_msg(tool_call_id: str, name: str = "rag_search") -> dict:
    """Build an AG-UI wire-format assistant message with one tool-call."""
    return {
        "role": "assistant",
        "content": None,
        "toolCalls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": '{"query": "test"}',
                },
            },
        ],
    }


def _tool_result_msg(tool_call_id: str, content: str = "result") -> dict:
    """Build an AG-UI wire-format tool result message."""
    return {
        "role": "tool",
        "toolCallId": tool_call_id,
        "content": content,
    }


class TestConvertDictMessages:
    """One tracer bullet at a time."""

    # ── Tracer bullet #1 ───────────────────────────────────────────────

    def test_orphaned_tool_calls_are_stripped(self) -> None:
        """When an assistant message has tool_calls with no matching
        tool result, those tool_calls are stripped from the message
        so the LLM provider doesn't reject the conversation.
        """
        messages = [
            {"role": "user", "content": "Search something"},
            _tool_call_agent_msg("call-orphan-1"),
            {"role": "user", "content": "Follow up"},
        ]

        result = _convert_dict_messages(messages)

        # Three messages: user, assistant (stripped), user
        assert len(result) == 3

        # The assistant message should have NO tool_calls
        assistant = _as_ai(result[1])
        assert assistant.tool_calls == []

    # ── Tracer bullet #2 ───────────────────────────────────────────────

    def test_paired_tool_calls_are_preserved(self) -> None:
        """When an assistant message's tool_calls ARE followed by
        corresponding tool results, they pass through unchanged.
        """
        messages = [
            {"role": "user", "content": "Search something"},
            _tool_call_agent_msg("call-paired-1"),
            _tool_result_msg("call-paired-1"),
            {"role": "user", "content": "Follow up"},
        ]

        result = _convert_dict_messages(messages)

        # Four messages: user, assistant (with tool_calls), tool, user
        assert len(result) == 4
        assistant = _as_ai(result[1])
        assert len(assistant.tool_calls) == 1
        assert assistant.tool_calls[0]["id"] == "call-paired-1"

    # ── Tracer bullet #3 ───────────────────────────────────────────────

    def test_tool_calls_at_end_of_sequence_are_stripped(self) -> None:
        """When the LAST message in the sequence is an assistant with
        tool_calls and no tool result follows (e.g., the user clicked
        Stop and the conversation hasn't been continued yet), the
        orphaned tool_calls are stripped.
        """
        messages = [
            {"role": "user", "content": "Search something"},
            _tool_call_agent_msg("call-trailing-1"),
        ]

        result = _convert_dict_messages(messages)

        assert len(result) == 2
        assistant = _as_ai(result[1])
        assert assistant.tool_calls == []

    # ── Tracer bullet #4 ───────────────────────────────────────────────

    def test_some_orphaned_some_paired(self) -> None:
        """When an assistant message has multiple tool_calls but only
        some are followed by results, the orphaned ones are stripped
        while the paired ones remain.
        """
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": None,
                "toolCalls": [
                    {
                        "id": "call-paired",
                        "type": "function",
                        "function": {
                            "name": "rag_search",
                            "arguments": '{"query": "matched"}',
                        },
                    },
                    {
                        "id": "call-orphan",
                        "type": "function",
                        "function": {
                            "name": "rag_read_document",
                            "arguments": '{"chunk_ids": [1]}',
                        },
                    },
                ],
            },
            _tool_result_msg("call-paired"),
            {"role": "user", "content": "More"},
        ]

        result = _convert_dict_messages(messages)

        assert len(result) == 4
        assistant = _as_ai(result[1])
        # Only the paired tool-call should survive
        assert len(assistant.tool_calls) == 1
        assert assistant.tool_calls[0]["id"] == "call-paired"

    # ── Tracer bullet #5 ───────────────────────────────────────────────

    def test_orphaned_but_content_preserved(self) -> None:
        """When tool_calls are stripped but the assistant message also
        has text content, the text content is preserved."""
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": "I'll look that up...",
                "toolCalls": [
                    {
                        "id": "call-orphan-2",
                        "type": "function",
                        "function": {
                            "name": "rag_search",
                            "arguments": '{"query": "test"}',
                        },
                    },
                ],
            },
            {"role": "user", "content": "Follow up"},
        ]

        result = _convert_dict_messages(messages)

        assert len(result) == 3
        assistant = _as_ai(result[1])
        assert assistant.tool_calls == []
        # Text content survives
        assert assistant.content == "I'll look that up..."
