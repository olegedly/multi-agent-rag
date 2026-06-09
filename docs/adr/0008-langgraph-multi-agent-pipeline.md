# ADR-0008: Multi-Agent Pipeline Shape — LangGraph with Researcher → Critic → Synthesizer

The full multi-agent pipeline (Researcher → Critic → Synthesizer) will be implemented as a **LangGraph `StateGraph`** with three explicit nodes and a conditional loop between Researcher and Critic.

**Status:** accepted (not yet implemented — the current pipeline is a single `create_agent` as a placeholder)

## Considered options

- **Single-agent with structured output** (one agent emitting `{findings, critique, synthesis}` in one pass via `response_format`): rejected — loses the iterative back-and-forth refinement that distinguishes the multi-agent architecture. A critic that sees the researcher's raw output is meaningfully different from one that co-generates.
- **Deep Agents harness** (`create_deep_agent` with subagent delegation): rejected — adds the entire Deep Agents dependency and its harness lifecycle for what is a simple three-node graph. The LangGraph pattern gives precise control over the iteration budget and termination condition with less framework overhead.
- **Three independent `create_agent` calls in sequence**: rejected — would require manual state plumbing and lacks the loop capability for researcher-critic iterations.

## Shape (when implemented)

```
State { findings, critique, synthesis, iteration_count }

Researcher node  →  Critic node  →  { accept → Synthesizer node
                                    { revise → Researcher node (cap at max_iterations)
```

- All three nodes call the same `ChatOpenAI` model with different system prompts.
- The Critic both evaluates and owns the accept/revise decision.
- A hard cap on iterations prevents runaway loops (configurable, default 3).
- The final state's `synthesis` field streams back as the TanStack SSE response.
- The existing `create_rag_tools(corpus_id=...)` closure pattern is reused — tools are scoped per-request and passed to whichever node needs them.

## Consequences

- When implemented, `backend/agents/pipeline.py` switches from `create_agent(...)` to a compiled LangGraph app.
- The SSE streaming signature stays the same — the frontend sees no difference.
- The current single-agent `pipeline.py` is a valid incremental step; no code from it is wasted (the system prompt, tool setup, and message routing all transfer directly into the Researcher node).
