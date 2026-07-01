# Data-Driven Agent Node Construction

## Files involved

`backend/agents/graph_orchestrator.py`

## Problem

Three near-identical node functions (`_researcher_node`, `_critic_node`, `_synthesizer_node`) differ only in which index of `AGENT_CONFIGS` they reference. The error-checking boilerplate (`if state.get("_error"): return ...`) is repeated three times. Adding a fourth agent requires writing a fourth identical function body.

## Topology (before)

```
graph_orchestrator.py:
  _researcher_node()   → 5 lines, calls AGENT_CONFIGS[0]
  _critic_node()       → 5 lines, calls AGENT_CONFIGS[1]
  _synthesizer_node()  → 5 lines, calls AGENT_CONFIGS[2]

  builder.add_node("researcher", _researcher_node)
  builder.add_node("critic", _critic_node)
  builder.add_node("synthesizer", _synthesizer_node)
```

## Solution

Build the graph dynamically: iterate over `AGENT_CONFIGS`, create node functions in a loop, and register them with auto-generated names. The error-checking logic lives once in the generated function.

## Topology (after)

```
AGENT_CONFIGS = [
  ("researcher",   _make_researcher_tools,   RESEARCHER_SYSTEM_PROMPT),
  ("critic",       _make_critic_tools,        CRITIC_SYSTEM_PROMPT),
  ("synthesizer",  _make_synthesizer_tools,   SYNTHESIZER_SYSTEM_PROMPT),
]

for name, tools_factory, prompt_template in AGENT_CONFIGS:
    builder.add_node(name, _make_node_fn(name, tools_factory, prompt_template))

edge_sequence = [START] + [c[0] for c in AGENT_CONFIGS] + [END]
for src, dst in zip(edge_sequence, edge_sequence[1:]):
    builder.add_edge(src, dst)
```

## Interface design options

### Option A: Factory function that returns a closure

```python
def _make_node_fn(config: _AgentConfig) -> Callable:
    async def _node(state: MultiAgentState) -> dict[str, Any]:
        if state.get("_error"):
            return {"messages": [], "_error": state["_error"]}
        return await _run_agent_node(
            config, state, model_instance, thread_id, run_id,
            event_queue=event_queue,
        )
    return _node
```

Used in a loop over `AGENT_CONFIGS`.

**Trade-offs**:
- Leverage: one factory, N agents. Adding an agent = one config entry.
- Locality: error handling and node construction in one place.
- Thin spot: `model_instance`, `thread_id`, `run_id`, `event_queue` are still closed over from the outer scope (`run_orchestrator`). If they were parameters to `_run_agent_node`, the closure captures them — fine because they don't change between nodes.

### Option B: Single dispatcher node with a name parameter

LangGraph's `add_node` passes state — not the node name — so the dispatcher can't distinguish which agent it is without a separate mechanism. A closure (Option A) is the natural LangGraph pattern.

**Trade-offs**: Option A is the idiomatic LangGraph approach. Option B would require encoding the agent name in the state (adding a field like `_current_agent`) — unnecessary indirection.

**Recommendation**: Option A.

## Deepening strategy

- **Dependency category**: in-process.
- **Seam placement**: `AGENT_CONFIGS` list becomes the single configuration surface — add an entry to add an agent. The node registration loop is the only place that creates LangGraph nodes.
- **Adapters**: none. The three nodes are already the same shape — this surfaces the pattern rather than changing it.
- **Testing**: No test changes needed. Test fixtures in `test_graph_orchestrator.py` and `test_pipeline_events.py` mock `model.astream`/`model.ainvoke` and don't care about node function names. The event sequences remain identical.

## Benefits

- *Locality*: node construction logic lives in one factory instead of three functions.
- *Leverage*: adding a fourth agent = one entry in `AGENT_CONFIGS` + one edge. No new function.
- *Win*: delete 15 lines of repetitive error-checking.
- *Win*: agent count is data, not code.

## Recommendation strength

**Worth exploring** — the repetition is small (three 5-line functions) and the current code is readable. The win comes when a fourth agent is added; before that, the refactor is optional polish.
