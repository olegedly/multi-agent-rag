"""Multi-agent LangGraph orchestrator — Researcher → Critic → Synthesizer.

Three specialist agents orchestrated via ``StateGraph(MultiAgentState)``.
Each agent wraps its own ``create_agent()`` with role-specific tools and
system prompt.  Token-level AG-UI events are emitted per agent, with
distinct ``TEXT_MESSAGE_START.name`` values for frontend agent labels.
"""

from __future__ import annotations

import asyncio
import operator
import time
from typing import Annotated, Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from backend.agents.langchain_tools import create_rag_tools
from backend.agents.stream_handler import StreamEventHandler
from backend.config import Settings
from backend.corpus_config import CorporaConfig
from backend.middleware import TokenBudgetCallback


# ── Shared state ────────────────────────────────────────────────────────────


class MultiAgentState(TypedDict):
    """LangGraph shared state for the three-agent pipeline.

    ``messages`` uses ``operator.add`` as reducer so each node's output
    appends to the accumulating conversation history.

    ``_error`` is a private signal field — set to a non-None string when
    a node fails, causing ``run_orchestrator`` to emit ``RunErrorEvent``
    instead of ``RunFinishedEvent``.
    """

    messages: Annotated[list[BaseMessage], operator.add]
    corpus_id: str
    corpus_name: str
    researcher_output: str | None
    critic_output: str | None
    _error: str | None

# ── System prompts ──────────────────────────────────────────────────────────


RESEARCHER_SYSTEM_PROMPT = """\
You are a **Corpus Researcher**.  Your job is to search the active knowledge \
base (corpus "{corpus_name}") for facts, dates, definitions, and \
specifications relevant to the user's question.

Rules:
1. Use `rag_search` to find relevant chunks in the corpus.
2. Use `rag_read_document` to retrieve full document context around \
promising chunks.
3. Cite sources using natural plain text — never construct URLs or \
hyperlink markdown.  Mention the source document title naturally \
(e.g., "under Article 79" or "(Article 79, §2)").  Do NOT use \
`[text](url)` syntax; the search results do not contain web URLs.
4. If a search returns no results, say so — do not invent facts.
5. Never answer from your own pre-training knowledge — base every claim \
on a retrieved chunk.
6. Do no more than 4 tool calls per query. Stop when you have enough, \
and produce a structured summary of your findings.
"""

CRITIC_SYSTEM_PROMPT = """\
You are a **Corpus Critic**.  Your job is to review the Researcher's \
findings against the active corpus "{corpus_name}".

You have the same search tools (`rag_search`, `rag_read_document`) for \
independent verification.  Identify gaps, contradictions, weak citations, \
or missing context.

Output a structured critique with:
- Verified claims (with plain-text citations — never construct URLs)
- Concerns or gaps found
- Suggested improvements for the final answer

Do no more than 4 tool calls.
"""

SYNTHESIZER_SYSTEM_PROMPT = """\
You are a **Corpus Synthesizer**.  Your job is to produce the final answer \
by synthesizing the Researcher's findings and the Critic's review.

You have no search tools — you read everything from the conversation context.

Output structure:
- Summary
- Key findings with plain-text citations (never construct URLs)
"""


# ── Agent configs ────────────────────────────────────────────────────────────


class _AgentConfig:
    """Configuration for one agent in the pipeline."""

    __slots__ = ("name", "tools_factory", "system_prompt_template")

    def __init__(
        self,
        name: str,
        tools_factory: Any,
        system_prompt_template: str,
    ) -> None:
        self.name = name
        self.tools_factory = tools_factory
        self.system_prompt_template = system_prompt_template


def _make_researcher_tools(corpus_id: str) -> list[BaseTool]:
    return create_rag_tools(corpus_id=corpus_id)


def _make_critic_tools(corpus_id: str) -> list[BaseTool]:
    return create_rag_tools(corpus_id=corpus_id)


def _make_synthesizer_tools(corpus_id: str) -> list[BaseTool]:
    return []


AGENT_CONFIGS: list[_AgentConfig] = [
    _AgentConfig(
        name="Researcher",
        tools_factory=_make_researcher_tools,
        system_prompt_template=RESEARCHER_SYSTEM_PROMPT,
    ),
    _AgentConfig(
        name="Critic",
        tools_factory=_make_critic_tools,
        system_prompt_template=CRITIC_SYSTEM_PROMPT,
    ),
    _AgentConfig(
        name="Synthesizer",
        tools_factory=_make_synthesizer_tools,
        system_prompt_template=SYNTHESIZER_SYSTEM_PROMPT,
    ),
]


# ── Orchestrator ────────────────────────────────────────────────────────────


def _convert_dict_messages(messages: list[dict]) -> list[BaseMessage]:
    """Convert AG-UI chat-format dicts to LangChain BaseMessage objects."""
    import json

    from langchain_core.messages import HumanMessage, SystemMessage

    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
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
                    {"id": tc.get("id", ""), "name": func.get("name", ""), "args": parsed_args}
                )
            lc_messages.append(AIMessage(content=content or "", tool_calls=lc_tool_calls))
        elif role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "tool":
            tool_call_id = msg.get("toolCallId") or msg.get("tool_call_id", "")
            lc_messages.append(
                ToolMessage(content=content, tool_call_id=tool_call_id)
            )
        else:
            lc_messages.append(HumanMessage(content=content))

    # Strip orphaned tool calls
    resolved_ids: set[str] = set()
    for msg in lc_messages:
        if isinstance(msg, ToolMessage):
            resolved_ids.add(msg.tool_call_id)
    result: list[BaseMessage] = []
    for msg in lc_messages:
        if isinstance(msg, AIMessage):
            surviving = [tc for tc in msg.tool_calls if tc["id"] in resolved_ids]
            result.append(AIMessage(content=msg.content or "", tool_calls=surviving))
        else:
            result.append(msg)
    return result


def _build_model(settings: Settings, model: BaseChatModel | None = None) -> BaseChatModel:
    """Build or return a model instance with budget callback."""
    if model is not None:
        return model

    budget_store = settings.budget_store
    callbacks = [TokenBudgetCallback(budget_store)] if budget_store else []

    return ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.llm_api_key,  # type: ignore[call-arg]
        openai_api_base=settings.llm_base_url,  # type: ignore[call-arg]
        max_tokens=settings.llm_max_tokens,  # type: ignore[call-arg]
        temperature=0,
        callbacks=callbacks,
    )


async def _run_agent_node(
    agent_config: _AgentConfig,
    state: MultiAgentState,
    model_instance: BaseChatModel,
    thread_id: str,
    run_id: str,
    event_queue: asyncio.Queue,
) -> dict[str, Any]:
    """Run one agent node via an explicit tool-calling loop.

    Instead of delegating to ``create_agent()`` (a LangGraph black box),
    this function drives the model directly in a loop:

      1. Stream model output through the handler (reasoning, tool calls, text)
      2. If the model returns tool calls, execute each tool
      3. Feed tool results back as ``ToolMessage`` objects via the handler
         (which causes ``_observe_tool_result`` to close the current
         reasoning block, enabling a fresh block on the next iteration)
      4. Repeat until the model produces a final answer with no tool calls

    This guarantees proper ``STEP_STARTED`` / ``REASONING_MESSAGE_END``
    boundaries around each tool-call iteration, producing multiple
    interleaved thinking blocks in the frontend.
    """
    import json

    from langchain_core.messages import SystemMessage

    tools = agent_config.tools_factory(state["corpus_id"])
    system_prompt = agent_config.system_prompt_template.format(
        corpus_name=state["corpus_name"],
    )

    handler = StreamEventHandler(
        thread_id=thread_id,
        run_id=run_id,
        message_id=str(uuid4()),
        agent_name=agent_config.name,
        suppress_run_started=True,
    )
    error_text: str | None = None

    # Build the full message list with system prompt
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    messages.extend(state["messages"])

    # Bind tools to the model so it knows what it can call (create_agent
    # does this internally; our explicit loop must do it too).
    from langchain_core.language_models.chat_models import BaseChatModel as _LCM

    model: _LCM = model_instance.bind_tools(tools) if tools else model_instance  # type: ignore[attr-defined]

    MAX_ITERATIONS = 6

    try:
        for _iteration in range(MAX_ITERATIONS):
            # ── Stream model output ────────────────────────────────────
            # Accumulate chunks so we can extract tool_calls with the SAME
            # tool call IDs the frontend saw during streaming, instead of
            # making a second non-streaming request (ainvoke) whose IDs
            # differ (causing orphaned tool calls in the frontend).
            accumulated: AIMessageChunk | None = None
            async for chunk in model.astream(  # type: ignore[attr-defined]
                messages,
            ):
                if isinstance(chunk, BaseMessage):
                    handler.observe(chunk, {"langgraph_node": "agent"})
                    accumulated = (
                        chunk if accumulated is None else accumulated + chunk  # type: ignore[operator]
                    )
                for event in handler.drain():
                    await event_queue.put(event)

            # The accumulated message carries the same tool call IDs that
            # were streamed to the frontend.
            result: BaseMessage = accumulated if accumulated is not None else AIMessage(content="")
            messages.append(result)

            tool_calls = getattr(result, "tool_calls", [])
            if not tool_calls:
                break  # Final answer — no more tools to call

            # ── Execute each tool and feed results back ────────────────
            for tc in tool_calls:
                tool_name: str = tc.get("name", "")  # type: ignore[union-attr]
                tool_args: dict = tc.get("args", {})  # type: ignore[union-attr]
                tool_call_id: str = tc.get("id", "")  # type: ignore[union-attr]

                matched_tool = next(
                    (t for t in tools if t.name == tool_name), None
                )
                if matched_tool is not None:
                    try:
                        tool_result = await matched_tool.ainvoke(tool_args)
                        if isinstance(tool_result, str):
                            result_content = tool_result
                        else:
                            result_content = json.dumps(tool_result)
                    except Exception as exc:
                        result_content = json.dumps({"error": str(exc)})
                else:
                    result_content = json.dumps({"error": f"Unknown tool: {tool_name}"})

                tool_msg = ToolMessage(
                    content=result_content, tool_call_id=tool_call_id
                )
                messages.append(tool_msg)

                # Emit tool result — this closes the current reasoning block
                # so the next model iteration starts a fresh one.
                handler.observe(tool_msg, {"langgraph_node": "tools"})
                for event in handler.drain():
                    await event_queue.put(event)

        # ── Close any open blocks ─────────────────────────────────────
        for event in handler.finalize():
            if not _is_run_finished(event):
                await event_queue.put(event)

    except Exception as exc:
        error_text = str(exc)
        for event in handler.error(error_text):
            await event_queue.put(event)

    # ── Extract final output for state ────────────────────────────────
    final_message = messages[-1] if messages else None
    output_text: str = (
        getattr(final_message, "content", str(final_message)) or ""
        if final_message
        else ""
    )

    state_update: dict[str, Any] = {
        "messages": [final_message] if final_message else [],
        "_error": error_text,
    }

    if not error_text:
        if agent_config.name == "Researcher":
            state_update["researcher_output"] = output_text
        elif agent_config.name == "Critic":
            state_update["critic_output"] = output_text

    return state_update


def _is_run_finished(event: Any) -> bool:
    """Check if an event is a RunFinishedEvent by duck-typing."""
    return type(event).__name__ == "RunFinishedEvent"


async def run_orchestrator(
    messages: list[dict],
    corpus_slug: str,
    corpora_config: CorporaConfig,
    settings: Settings,
    thread_id: str = "th-default",
    run_id: str = "run-default",
    model: BaseChatModel | None = None,
):
    """Run the three-agent pipeline.  Yields token-level AG-UI protocol events.

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
        TextMessageEndEvent, RunFinishedEvent, or RunErrorEvent.
    """
    corpus = corpora_config.get(corpus_slug)
    if corpus is None:
        return

    model_instance = _build_model(settings, model)
    lc_messages = _convert_dict_messages(messages)

    # ── Event queue for real-time streaming ────────────────────────────────
    # Events are pushed by agent nodes as soon as they're produced and
    # drained concurrently in the main coroutine.  A ``None`` sentinel
    # signals the drain loop to stop.
    event_queue: asyncio.Queue = asyncio.Queue()

    # ── Build the StateGraph ──────────────────────────────────────────────
    builder = StateGraph(MultiAgentState)

    async def _researcher_node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        update = await _run_agent_node(
            AGENT_CONFIGS[0], state, model_instance, thread_id, run_id,
            event_queue=event_queue,
        )
        return dict(update)

    async def _critic_node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        update = await _run_agent_node(
            AGENT_CONFIGS[1], state, model_instance, thread_id, run_id,
            event_queue=event_queue,
        )
        return dict(update)

    async def _synthesizer_node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        update = await _run_agent_node(
            AGENT_CONFIGS[2], state, model_instance, thread_id, run_id,
            event_queue=event_queue,
        )
        return dict(update)

    builder.add_node("researcher", _researcher_node)
    builder.add_node("critic", _critic_node)
    builder.add_node("synthesizer", _synthesizer_node)

    builder.add_edge(START, "researcher")
    builder.add_edge("researcher", "critic")
    builder.add_edge("critic", "synthesizer")
    builder.add_edge("synthesizer", END)

    graph = builder.compile()

    # ── Emit RUN_STARTED ──────────────────────────────────────────────────
    yield _run_started_event(thread_id, run_id)

    # ── Drive the graph (background) + drain events (foreground) ──────────
    has_error: bool = False
    graph_exception: Exception | None = None

    async def _drive_graph() -> None:
        nonlocal has_error, graph_exception
        try:
            async for _state in graph.astream(
                {
                    "messages": lc_messages,
                    "corpus_id": corpus.id,
                    "corpus_name": corpus.name,
                    "researcher_output": None,
                    "critic_output": None,
                    "_error": None,
                },
                stream_mode="updates",
            ):
                if isinstance(_state, dict):
                    for node_updates in _state.values():
                        if isinstance(node_updates, dict) and node_updates.get("_error"):
                            has_error = True
        except Exception as exc:
            graph_exception = exc
        finally:
            await event_queue.put(None)  # sentinel → drain loop stops

    graph_task = asyncio.create_task(_drive_graph())

    # Drain events from the queue as they arrive (real-time), stopping
    # when the sentinel is received.
    while True:
        event = await event_queue.get()
        event_queue.task_done()
        if event is None:
            break
        yield event

    await graph_task

    if graph_exception:
        yield _run_error_event(str(graph_exception))
        return

    if has_error:
        return  # handler.error() already emitted RunErrorEvent on the queue

    yield _run_finished_event(thread_id, run_id)


def _run_started_event(thread_id: str, run_id: str) -> Any:
    from ag_ui.core.events import RunStartedEvent

    return RunStartedEvent(thread_id=thread_id, run_id=run_id, timestamp=_now_ms())


def _run_finished_event(thread_id: str, run_id: str) -> Any:
    from ag_ui.core.events import RunFinishedEvent

    return RunFinishedEvent(thread_id=thread_id, run_id=run_id, timestamp=_now_ms())


def _run_error_event(message: str) -> Any:
    from ag_ui.core.events import RunErrorEvent

    return RunErrorEvent(message=message, timestamp=_now_ms())


def _now_ms() -> int:
    return int(time.time() * 1000)
