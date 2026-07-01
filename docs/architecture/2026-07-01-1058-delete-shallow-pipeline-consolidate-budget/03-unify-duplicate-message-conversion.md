# Unify Duplicate Message Conversion Across Graph Modules

## Files involved

`backend/agents/pipeline.py`, `backend/agents/graph_orchestrator.py`

## Problem

`_convert_dict_messages` is defined twice — once in `pipeline.py` (lines 23–100) and once in `graph_orchestrator.py` (lines 156–204). Both are byte-for-byte identical, including the orphaned-tool-call stripping that lives inside the `graph_orchestrator` copy instead of being a separate helper. The `pipeline.py` copy also carries `_strip_orphaned_tool_calls` as a separate top-level function that is never called — the stripping logic is inlined in `graph_orchestrator.py`'s copy.

## Topology (before)

```
pipeline.py: _convert_dict_messages()    ← copy A + dead _strip_orphaned_tool_calls()
graph_orchestrator.py: _convert_dict_messages()    ← copy B (stripping inlined)
  → called from run_orchestrator()
```

A fix to one copy (e.g., a new message role or a change to the AG-UI wire format) silently leaves the other copy stale.

## Solution

Define `_convert_dict_messages` in exactly one place — `graph_orchestrator.py`, since that's where it's actually called. Export it as the canonical converter. Delete the `pipeline.py` copy and the dead `_strip_orphaned_tool_calls`.

## Topology (after)

```
graph_orchestrator.py: _convert_dict_messages()    ← one copy, one caller

(or, if another consumer appears)
backend/.../message_converter.py: convert_dict_messages()    ← extracted module
  → imported by graph_orchestrator
```

## Interface design options

### Option A: One copy in graph_orchestrator, delete the other

Trivial — delete `pipeline.py` (already the subject of suggestion 01) and its dead code. The surviving copy in `graph_orchestrator.py` becomes the sole definition.

**Trade-offs**:
- Leverage: already at maximum — one definition, one caller, zero dead branches.
- No new seam needed.

### Option B: Extract to a shared module

Pull the converter into a dedicated module like `backend/agents/message_converter.py`.

```python
# backend/agents/message_converter.py — single source of truth
def convert_dict_messages(messages: list[dict]) -> list[BaseMessage]:
    ...

def strip_orphaned_tool_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    ...
```

**Trade-offs**:
- Leverage: N future consumers import one function.
- Locality: message-format knowledge lives in one module, isolatable from agent orchestration.
- Added seam: a whole module for two functions that have one caller. The deletion test asks: "if the orchestrator is the only caller, does extracting help?" — not until a second consumer appears.
- **Not justified yet.** One caller, one definition.

**Recommendation**: Option A, as a side-effect of deleting `pipeline.py` (suggestion 01). If and when a second consumer appears (e.g., a batch-processing pipeline that converts messages independently), extract to a shared module then.

## Deepening strategy

- **Dependency category**: in-process.
- **Seam placement**: not applicable — this is deleting duplication, not introducing a seam.
- **Adapters**: none.
- **Testing**: The tests in `test_pipeline_events.py` and `test_graph_orchestrator.py` both exercise message conversion implicitly through `run_pipeline` / `run_orchestrator`. No test changes needed.

## Benefits

- *Locality*: one definition, one module — fixes converge, not drift.
- *Leverage*: zero extra work; the duplication goes away as a side-effect of deleting the pass-through module.
- *Win*: dead `_strip_orphaned_tool_calls` gone.
- *Win*: no more "fix in one, forget the other."

## Recommendation strength

**Strong** — but it's a side-effect of suggestion 01. Don't sequence this independently; it costs nothing when the pipeline module is deleted.
