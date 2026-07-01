# Consolidate Budget Instantiation

## Files involved

`backend/main.py`, `backend/agents/graph_orchestrator.py`

## Problem

`JsonFileBudget` is instantiated twice — once in `create_app()` (`main.py`) and again in `_build_model()` (`graph_orchestrator.py`). Both use the same settings. They create independent file handles for the same `/data/demo-budget.json`, risking double-counting if both paths fire for the same request.

## Topology (before)

```
main.py:create_app()
  └─ budget_file = JsonFileBudget(...)           ← instance A
      └─ passed to ChatGuard

graph_orchestrator:_build_model()
  └─ budget_file = JsonFileBudget(...)           ← instance B (same settings)
      └─ passed to TokenBudgetCallback
```

Both read/write the same file path, but have separate in-memory state. On concurrent requests — even with a single uvicorn worker — the OS file buffer + Python's GIL mean the two instances can overwrite each other's reads. The `ChatGuard` checks exhaustion before routing; the `TokenBudgetCallback` deducts after LLM output. If instance A decrements and instance B hasn't refreshed, the exhaustion check is stale.

## Solution

`create_app()` injects the single `JsonFileBudget` instance into both `ChatGuard` and the orchestrator. `_build_model()` receives the budget as a parameter instead of constructing its own.

## Topology (after)

```
main.py:create_app()
  └─ budget_file = JsonFileBudget(...)           ← one instance
      ├─ passed to ChatGuard
      └─ passed through to run_orchestrator
          → _build_model(budget_file=budget_file)
              → TokenBudgetCallback(budget_file)
```

## Interface design options

### Option A: Pass budget_file through the call chain

`run_orchestrator` and `_build_model` accept an optional `budget_file` parameter.

```python
def _build_model(settings, model=None, budget_file=None):
    if budget_file is None:
        # only when called standalone / test without one
        budget_file = JsonFileBudget(...)
    return ChatOpenAI(..., callbacks=[TokenBudgetCallback(budget_file)])
```

**Trade-offs**:
- Leverage: `create_app()` owns one instance, routes it to both consumers.
- Locality: budget lifecycle lives in one place (`create_app`).
- Seam: tests can inject `None` budget (no file IO) by passing `budget_file=None` — same as `demo_disable_budget=True`.
- Thin spot: `_build_model` still has the fallback construction. The deletion test asks: "could a future caller forget to pass `budget_file` and silently write to a second instance?" — yes, the fallback is a trap. Make it required for production paths.

### Option B: Build models from a configured factory

```python
class ModelFactory:
    def __init__(self, settings, budget_file=None):
        self._settings = settings
        self._budget_file = budget_file
    def build(self, tools=None):
        return ChatOpenAI(..., callbacks=[...])
```

**Trade-offs**:
- Adds a class for what a function parameter handles.
- Deletion test: "move the budget_file default into the caller" — yes, that's Option A. The factory is not yet justified (one production caller, one instantiation per request).

### Option C: Lift budget to the Settings object

```python
@property
def budget_store(self) -> BudgetStore | None:
    if self.demo_disable_budget:
        return None
    return JsonFileBudget(self.demo_budget_file, self.demo_daily_budget_tokens)
```

Singleton per Settings instance (and `get_settings()` is cached via `@lru_cache`). Both consumers call `settings.budget_store` and get the same object.

**Trade-offs**:
- Leverage: zero-parameter access everywhere. Any module can say `settings.budget_store` and get the canonical instance.
- Locality: budget logic lives in one method instead of in two constructors.
- Risk: `Settings` now owns a file handle / side-effect. Currently `Settings` is pure config. This blurs the seam. But `Settings` already has `@property database_url` — same pattern, same level of impurity.
- Winner for leverage: one `Settings` method serves N consumers with zero wiring overhead.

**Recommendation**: Option C (lift to `Settings`) with Option A's parameter as a safety valve. `_build_model` checks `settings.budget_store` as default, callers can override. This gives one truth, zero duplication, and no wiring.

## Deepening strategy

- **Dependency category**: in-process. `BudgetStore` is a `Protocol` — substitutable.
- **Seam placement**: at the `BudgetStore` protocol boundary. Both `ChatGuard` and `TokenBudgetCallback` already accept `BudgetStore | None`. The seam is already correct — the bug is that two instances are created.
- **Adapters**: `JsonFileBudget` is the only production adapter. Tests use `FakeSessionMaker` / monkeypatch. One adapter = hypothetical seam (the Protocol exists for test injection). Two adapters would arrive if a Redis-backed budget appears.
- **Testing**: No test changes needed. Tests already inject settings or monkeypatch the call chain.

## Benefits

- *Locality*: budget state lives in one `Settings` property.
- *Leverage*: one budget instance, both consumers.
- *Win*: eliminate double-counting race.
- *Win*: delete second `JsonFileBudget` construction.
- *Win*: `_build_model` becomes stateless w.r.t. filesystem.

## Recommendation strength

**Strong**
