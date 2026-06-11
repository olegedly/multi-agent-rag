"""LangChain agent pipeline: token-level streaming with AG-UI events.

Switched from ``agent.ainvoke()`` (one-shot) to
``agent.astream(stream_mode="messages")`` for smooth token-level
streaming.  ``StreamEventHandler`` handles event classification.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from backend.agents.stream_handler import StreamEventHandler
from backend.corpus_config import CorporaConfig


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
                AIMessage(content=content, tool_calls=lc_tool_calls)
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
    return lc_messages


async def run_pipeline(
    messages: list[dict],
    corpus_slug: str,
    corpora_config: CorporaConfig,
    settings,
    thread_id: str = "th-default",
    run_id: str = "run-default",
    model=None,
):
    """Run the agent pipeline.  Yields token-level AG-UI protocol events.

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
        Pre-configured model instance.  When provided, ``ChatOpenAI``
        construction is skipped — useful for tests and for callers that
        want to wire their own model instance.

    Yields
    ------
    Pydantic AG-UI event models (serializable via ``EventEncoder.encode``):
        RunStartedEvent, TextMessageStartEvent/ContentEvent/EndEvent,
        ReasoningMessageStartEvent/ContentEvent/EndEvent,
        ToolCallStartEvent/ArgsEvent/EndEvent/ResultEvent,
        RunFinishedEvent, or RunErrorEvent.
    """
    corpus = corpora_config.get(corpus_slug)
    if corpus is None:
        return

    from langchain.agents import create_agent

    from backend.agents.langchain_tools import create_rag_tools
    from backend.middleware import JsonFileBudget, TokenBudgetCallback

    tools = create_rag_tools(corpus_id=corpus.id)

    # Wire daily token budget
    budget_file = None
    if not settings.demo_disable_budget:
        budget_file = JsonFileBudget(
            path=settings.demo_budget_file,
            daily_limit=settings.demo_daily_budget_tokens,
        )

    if model is None:
        from langchain_openai import ChatOpenAI

        # fmt: off
        model = ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.llm_api_key,  # type: ignore[call-arg]
            openai_api_base=settings.llm_base_url,  # type: ignore[call-arg]
            max_tokens=settings.llm_max_tokens,  # type: ignore[call-arg]
            temperature=0,
            callbacks=[TokenBudgetCallback(budget_file)],
        )
        # fmt: on

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=(
            "You are a research assistant that answers questions exclusively from "
            "a curated knowledge base (the active corpus).\n\n"
            "Rules:\n"
            f"1. Use the `rag_search` tool to find relevant chunks in the corpus '{corpus.name}'.\n"
            "2. Use `rag_read_document` to retrieve full document context around promising chunks.\n"
            "3. Always cite your sources (corpus name + content excerpts + chunk IDs).\n"
            "4. If a search returns no results, say so — do not invent facts.\n"
            "5. Never answer from your own pre-training knowledge — base every claim on a retrieved chunk."
            "6. Do no more than 4 tools calls per query. Stop when you have enough, and produce the response."
        ),
    )

    lc_messages = _convert_dict_messages(messages)

    message_id = str(uuid4())
    handler = StreamEventHandler(
        thread_id=thread_id,
        run_id=run_id,
        message_id=message_id,
    )

    # Emit RUN_STARTED immediately
    for event in handler.drain():
        yield event

    try:
        # ------------------------------------------------------------------
        # Token-level streaming via astream(stream_mode="messages")
        # ------------------------------------------------------------------
        async for chunk, metadata in agent.astream(
            {"messages": lc_messages},  # type: ignore[arg-type]
            config={"recursion_limit": 25},
            stream_mode="messages",
        ):
            if isinstance(chunk, BaseMessage):
                handler.observe(chunk, metadata)  # type: ignore[arg-type]
            for event in handler.drain():
                yield event

        # Stream exhausted — close any open blocks and emit RUN_FINISHED
        for event in handler.finalize():
            yield event

    except Exception as exc:
        # Close open blocks and emit RUN_ERROR
        for event in handler.error(str(exc)):
            yield event
