# Delete Shallow Pipeline Module

## Files involved

`backend/agents/pipeline.py`, `backend/main.py`, `backend/agents/graph_orchestrator.py`

## Problem

`pipeline.py` is a pure pass-through — its entire public surface (`run_pipeline`) delegates directly to `graph_orchestrator.run_orchestrator()` with no transformation. It also carries a duplicate `_convert_dict_messages` (matched by a second copy in `graph_orchestrator.py`) and a dead `_strip_orphaned_tool_calls`.

## Topology (before)

```
main.py:chat()
  → pipeline.run_pipeline()
      → graph_orchestrator.run_orchestrator()
          → _run_agent_node() × 3

pipeline.py holds:
  _convert_dict_messages()  ← duplicated
  _strip_orphaned_tool_calls()  ← unused
```

## Solution

Delete `pipeline.py`. `main.py` imports `run_orchestrator` directly. The duplicate message-conversion code lives in one place.

## Topology (after)

```
main.py:chat()
  → graph_orchestrator.run_orchestrator()
      → _run_agent_node() × 3
```

## Interface design options

The interface between `main.py` and the orchestrator is already defined by `run_orchestrator()` — the pass-through added nothing. The options are about the new direct import.

### Option A: Direct import — no wrapping

`main.py` calls `graph_orchestrator.run_orchestrator(...)` directly.

```python
from backend.agents.graph_orchestrator import run_orchestrator

async for event in run_orchestrator(
    messages, corpus_slug, corpora_config, settings,
    thread_id=thread_id, run_id=run_id,
):
    yield event
```

Trade-offs:
- **Leverage**: high — 1 call site in `main.py`, N test sites that already import orchestrator directly.
- **Locality**: bugs in routing live in `main.py` alongside the endpoint definition, not in a dead-end indirection.
- **Zero new surface**: no new interface to learn, no constructor, no config.

### Option B: Thin, named router function in graph_orchestrator (rename `run_orchestrator` → the public name)

Same as Option A but exported with a clearer name (already done — `run_orchestrator` is descriptive). No change needed.

### Option C: Adapter class for testability

Wrap `run_orchestrator` in a class so `main.py` depends on an interface.

```python
class Orchestrator(Protocol):
    async def run(self, ...) -> AsyncIterator[Event]: ...
```

Trade-offs:
- Adds a seam that has exactly one implementation and one caller — the **deletion test** says this is premature. The function signature is already injected via `monkeypatch` in tests (see `test_chat_endpoint.py`'s `_fake_pipeline`). No real adapter needed.

**Recommendation**: Option A. The function-level seam already supports test injection (`monkeypatch`). A class adapter adds a shallow wrapper for no gain — the deletion test would flag it immediately.

## Deepening strategy

- **Dependency category**: in-process.
- **Seam placement**: at the module boundary — `main.py` imports from `graph_orchestrator` instead of via `pipeline`. The existing `monkeypatch` seam in `test_chat_endpoint.py` already works this way.
- **Adapters**: none justified. The function signature is the seam.
- **Testing**:
  - Delete: test imports from `pipeline`, test helper `collect_pipeline_events`. The function-level tests in `test_pipeline_events.py` all import `run_pipeline` — these become imports of `run_orchestrator`. The structure is identical.
  - Keep: all tests. Just change the import.
  - What layers: the `test_chat_endpoint.py` already monkeypatches `backend.main.run_pipeline` — that patch point stays as long as `main.py` has a callable; name it whatever you want.

## Benefits

- *Locality*: routing + orchestrator in same dependency chain, not three hops.
- *Leverage*: one import path for all callers.
- *Win*: delete duplicate message conversion.
- *Win*: delete dead `_strip_orphaned_tool_calls`.
- *Win*: 73-line file gone.

## Recommendation strength

**Strong**
