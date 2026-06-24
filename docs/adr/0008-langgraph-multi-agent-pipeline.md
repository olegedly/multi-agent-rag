# ADR-0008: Multi-Agent Pipeline Shape — LangGraph with Researcher → Critic → Synthesizer

The multi-agent pipeline (Researcher → Critic → Synthesizer) is implemented as a **LangGraph `StateGraph`** with three sequential nodes and an explicit tool-calling loop inside each node. No iterative loop between Researcher and Critic — the Critic can be upgraded to one in a future iteration.

**Status:** accepted, implemented.

## Considered options

- **Single-agent with structured output** (one agent emitting `{findings, critique, synthesis}` in one pass via `response_format`): rejected — loses the iterative back-and-forth refinement that distinguishes the multi-agent architecture. A critic that sees the researcher's raw output is meaningfully different from one that co-generates.
- **Deep Agents harness** (`create_deep_agent` with subagent delegation): rejected — adds the entire Deep Agents dependency and its harness lifecycle for what is a simple three-node graph. The LangGraph pattern gives precise control over the iteration budget and termination condition with less framework overhead.
- **Three independent `create_agent` calls in sequence**: rejected — would require manual state plumbing and lacks the loop capability for researcher-critic iterations.

## Shape (as implemented)

```
MultiAgentState { messages, corpus_id, corpus_name, researcher_output, critic_output, _error }

Researcher node  →  Critic node  →  Synthesizer node
```

- All three nodes share the same `ChatOpenAI` model instance with different system prompts and tool sets.
- The Critic has search tools (same as Researcher) for independent verification — it is not limited to reading only.
- No iterative loop — linear single-pass. The `_error` field short-circuits subsequent nodes on failure.
- Each agent uses an explicit tool-calling loop (not `create_agent()`) that drives the model in iterations: stream → execute tools → feed results back → repeat until final answer. This guarantees proper `REASONING_MESSAGE_START/END` boundaries around each tool-call iteration.
- The existing `create_rag_tools(corpus_id=...)` closure pattern is reused — tools are scoped per-request and passed to whichever node needs them.

## Consequences

- `backend/agents/pipeline.py` delegates to `backend/agents/graph_orchestrator.run_orchestrator()`, which compiles and runs the LangGraph app.
- The SSE streaming signature stays the same — the frontend sees no difference.
- `backend/agents/pipeline.py` message conversion and routing code was kept as-is for backward compatibility — `_convert_dict_messages` and the function signature are shared between the old single-agent runner and the new `run_orchestrator()`.
