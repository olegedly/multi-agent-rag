"""LangChain agent pipeline: delegates to multi-agent orchestrator.

This module is now a thin wrapper around
``graph_orchestrator.run_orchestrator()``, which runs the three-agent
(Researcher → Critic → Synthesizer) pipeline.  The function signature
and ``_convert_dict_messages`` are kept for backward compatibility.
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

# The monkey-patch for reasoning_content is in ``backend/agents/__init__.py``
# and runs automatically when this module is imported (agents is a parent pkg).


def _convert_dict_messages(messages: list[dict]) -> list[BaseMessage]:
    """Convert AG-UI chat-format dicts to LangChain BaseMessage objects.

    The AG-UI wire format (``uiMessagesToWire``) sends assistant tool_calls
    under the key ``toolCalls`` as::

        toolCalls = [
            {
                "id": "call-...",
                "type": "function",
                "function": {
                    "name": "rag_search",
                    "arguments": '{"query":"..."}',
                },
            },
        ]

    LangChain ``AIMessage`` expects ``tool_calls`` as::

        tool_calls = [
            {
                "id": "call-...",
                "name": "rag_search",
                "args": {"query": "..."},
            },
        ]

    This function converts between the two formats so that follow-up
    queries preserve the tool-call/result pairings.
    """
    import json

    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            # Convert AG-UI wire-format toolCalls to LangChain tool_calls
            tool_calls_data = msg.get("toolCalls", [])
            lc_tool_calls = []
            for tc in tool_calls_data:
                func = tc.get("function", {})
                raw_args = func.get("arguments", "{}")
                try:
                    parsed_args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    parsed_args = {}
                lc_tool_calls.append(
                    {
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "args": parsed_args,
                    }
                )
            lc_messages.append(
                AIMessage(content=content or "", tool_calls=lc_tool_calls)
            )
        elif role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "tool":
            # AG-UI wire format sends `toolCallId` (camelCase), not `tool_call_id`
            tool_call_id = msg.get("toolCallId") or msg.get("tool_call_id", "")
            lc_messages.append(
                ToolMessage(content=content, tool_call_id=tool_call_id)
            )
        else:
            lc_messages.append(HumanMessage(content=content))

    # ── Sanitise orphaned tool-calls ────────────────────────────────
    # After the user clicks Stop, the frontend may re-send a conversation
    # where an assistant message has tool_calls with no matching tool
    # result (the Stop interrupted the stream before the result arrived).
    # The OpenAI API rejects such sequences with a 400 error, so we strip
    # any tool_call whose id lacks a corresponding ToolMessage.
    lc_messages = _strip_orphaned_tool_calls(lc_messages)
    return lc_messages


def _strip_orphaned_tool_calls(
    lc_messages: list[BaseMessage],
) -> list[BaseMessage]:
    """Remove tool_calls from AIMessages that lack matching ToolMessages.

    The LLM provider (OpenAI / OpenRouter) rejects conversations where
    an ``AIMessage`` has ``tool_calls`` without corresponding
    ``ToolMessage`` results. This occurs naturally when the user clicks
    Stop mid-stream and the client re-sends the conversation on the
    next query.

    The pass is global-then-local: collect all tool_call_ids that appear
    in any ``ToolMessage``, then strip any ``AIMessage.tool_call`` whose
    id is not in that set.
    """
    resolved_ids: set[str] = set()
    for msg in lc_messages:
        if isinstance(msg, ToolMessage):
            resolved_ids.add(msg.tool_call_id)

    result: list[BaseMessage] = []
    for msg in lc_messages:
        if isinstance(msg, AIMessage):
            surviving = [
                tc for tc in msg.tool_calls if tc["id"] in resolved_ids
            ]
            # Preserve the AIMessage even when all tool_calls are
            # stripped — the text content (if any) still carries forward.
            result.append(
                AIMessage(content=msg.content or "", tool_calls=surviving)
            )
        else:
            result.append(msg)
    return result


async def run_pipeline(
    messages: list[dict],
    corpus_slug: str,
    corpora_config,
    settings,
    thread_id: str = "th-default",
    run_id: str = "run-default",
    model=None,
):
    """Run the multi-agent pipeline.  Yields token-level AG-UI protocol events.

    Delegates to ``graph_orchestrator.run_orchestrator()`` for the
    three-agent (Researcher → Critic → Synthesizer) flow.

    Parameters
    ----------
    messages : list[dict]
        The conversation history from the frontend (OpenAI chat format).
    corpus_slug : str
        URL slug for the corpus (e.g. ``"eu-ai-act"``).
    corpora_config : CorporaConfig
        Resolves the slug to a corpus UUID and metadata.
    settings : Settings
        App settings for LLM config.
    thread_id : str
        Thread identifier from the frontend.
    run_id : str
        Run identifier from the frontend.
    model : BaseChatModel, optional
        Pre-configured model instance.

    Yields
    ------
    Pydantic AG-UI event models (serializable via ``EventEncoder.encode``):
        RunStartedEvent, TextMessageStartEvent/ContentEvent/EndEvent,
        ReasoningMessageStartEvent/ContentEvent/EndEvent,
        ToolCallStartEvent/ArgsEvent/EndEvent/ResultEvent,
        RunFinishedEvent, or RunErrorEvent.
    """
    from backend.agents.graph_orchestrator import run_orchestrator

    async for event in run_orchestrator(
        messages=messages,
        corpus_slug=corpus_slug,
        corpora_config=corpora_config,
        settings=settings,
        thread_id=thread_id,
        run_id=run_id,
        model=model,
    ):
        yield event
