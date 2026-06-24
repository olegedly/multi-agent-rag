"""Multi-agent LangGraph orchestrator — Researcher → Critic → Synthesizer.

Three specialist agents orchestrated via ``StateGraph(MultiAgentState)``.
Each agent wraps its own ``create_agent()`` with role-specific tools and
system prompt.  Token-level AG-UI events are emitted per agent, with
distinct ``TEXT_MESSAGE_START.name`` values for frontend agent labels.
"""

from __future__ import annotations

import operator
import time
from typing import Annotated, Any
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from backend.agents.langchain_tools import create_rag_tools
from backend.agents.stream_handler import StreamEventHandler
from backend.config import Settings
from backend.corpus_config import CorporaConfig
from backend.middleware import JsonFileBudget, TokenBudgetCallback


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
3. Cite your sources (corpus name + content excerpts + chunk IDs).
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
- Verified claims (with citations)
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
- Key findings with citations
- Confidence assessment (high / medium / low)
- Address any concerns raised by the Critic
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

    budget_file = None
    if not settings.demo_disable_budget:
        budget_file = JsonFileBudget(
            path=settings.demo_budget_file,
            daily_limit=settings.demo_daily_budget_tokens,
        )

    return ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.llm_api_key,  # type: ignore[call-arg]
        openai_api_base=settings.llm_base_url,  # type: ignore[call-arg]
        max_tokens=settings.llm_max_tokens,  # type: ignore[call-arg]
        temperature=0,
        callbacks=[TokenBudgetCallback(budget_file)] if budget_file else [],
    )


async def _run_agent_node(
    agent_config: _AgentConfig,
    state: MultiAgentState,
    model_instance: BaseChatModel,
    thread_id: str,
    run_id: str,
) -> tuple[dict[str, Any], list[Any]]:
    """Run one agent node, returning (state_update, ag_ui_events).

    The state_update dict contains the fields to merge back into the graph
    state.  The events list holds AG-UI protocol events for the orchestrator
    to yield.
    """
    tools = agent_config.tools_factory(state["corpus_id"])
    system_prompt = agent_config.system_prompt_template.format(
        corpus_name=state["corpus_name"],
    )

    agent = create_agent(
        model=model_instance,
        tools=tools,
        system_prompt=system_prompt,
    )

    message_id = str(uuid4())
    handler = StreamEventHandler(
        thread_id=thread_id,
        run_id=run_id,
        message_id=message_id,
        agent_name=agent_config.name,
        suppress_run_started=True,
    )
    events: list[Any] = []
    error_text: str | None = None

    try:
        async for chunk, metadata in agent.astream(
            {"messages": state["messages"]},  # type: ignore[arg-type]
            config={"recursion_limit": 25},
            stream_mode="messages",
        ):
            if isinstance(chunk, BaseMessage):
                handler.observe(chunk, metadata)  # type: ignore[arg-type]
            for event in handler.drain():
                events.append(event)

        for event in handler.finalize():
            if not _is_run_finished(event):
                events.append(event)

    except Exception as exc:
        error_text = str(exc)
        for event in handler.error(error_text):
            events.append(event)

    state_update: dict[str, Any] = {
        "messages": [],
        "_error": error_text,
    }

    if error_text:
        return state_update, events

    # Reconstruct the agent's final output message via invoke
    result = await agent.ainvoke(
        {"messages": state["messages"]},  # type: ignore[arg-type]
        config={"recursion_limit": 25},
    )
    final_messages = result["messages"] if isinstance(result, dict) else result.messages
    final_message = final_messages[-1]
    output_text: str = getattr(final_message, "content", str(final_message)) or ""

    state_update["messages"] = [final_message]

    if agent_config.name == "Researcher":
        state_update["researcher_output"] = output_text
    elif agent_config.name == "Critic":
        state_update["critic_output"] = output_text

    return state_update, events


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

    # ── Node event buffer (shared via closure) ────────────────────────────
    node_events_buffer: list[Any] = []

    # ── Build the StateGraph ──────────────────────────────────────────────
    builder = StateGraph(MultiAgentState)

    async def _researcher_node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        update, node_events = await _run_agent_node(
            AGENT_CONFIGS[0], state, model_instance, thread_id, run_id,
        )
        node_events_buffer.extend(node_events)
        return dict(update)

    async def _critic_node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        update, node_events = await _run_agent_node(
            AGENT_CONFIGS[1], state, model_instance, thread_id, run_id,
        )
        node_events_buffer.extend(node_events)
        return dict(update)

    async def _synthesizer_node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        update, node_events = await _run_agent_node(
            AGENT_CONFIGS[2], state, model_instance, thread_id, run_id,
        )
        node_events_buffer.extend(node_events)
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

    # ── Drive the graph, yielding per-node events ─────────────────────────
    has_error: bool = False

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
            for event in node_events_buffer:
                yield event
            node_events_buffer.clear()

            # Check for error signal in state update
            if isinstance(_state, dict):
                for node_updates in _state.values():
                    if isinstance(node_updates, dict) and node_updates.get("_error"):
                        has_error = True

        # Drain any remaining events
        for event in node_events_buffer:
            yield event

    except Exception as exc:
        yield _run_error_event(str(exc))
        return

    if has_error:
        yield _run_error_event("One or more agents failed")
        return

    # ── Emit RUN_FINISHED ────────────────────────────────────────────────
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
