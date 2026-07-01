# Consolidate collapse orchestration behind one module

## Files involved

`frontend/src/conversations/CollapsibleSection.tsx`, `frontend/src/conversations/toolResultTracker.ts`,
`frontend/src/conversations/ChatView.tsx`, `frontend/src/conversations/MessagePartRenderer.tsx`

## Problem

Understanding *when a tool result collapses* requires tracing through 4 modules and 2 contexts — no **locality**.

## Topology (before)

```
ChatView (provides StopCollapseContext, MessageEndedContext)
  │
  └─ MessagePartRenderer
       └─ ToolResultPartRenderer
            └─ CollapsibleSection
                 ├── autoCollapseMs         ← toolResultTracker.ts
                 ├── collapseOnTick         ← stopTick + endedSet.size
                 ├── disableStopCollapse    ← opted out
                 └── stopTick (context)     ← ChatView
```

The collapse contract is implicit: each sub-renderer computes its own `stuckExpanded`, `collapseTick`, `autoCollapseMs`, and `resetTimerOn` ad-hoc. The `StopCollapseContext` from `ChatView` reaches through `CollapsibleSection` into every tool result and thinking block — but `ToolResultPartRenderer` explicitly disables it with `disableStopCollapse=true` and uses its own `autoCollapseMs`+`collapseOnTick` instead. A reader must hold all 4 files in their head to know which one fires when.

## Solution

Extract the collapse state machine into a single `CollapseController` module that owns timing, tick aggregation, and user-interaction memory.

## Topology (after)

```
CollapseController (one seam: CollapseConfig → CollapseState)
  │
  └─ called by: ToolResultPartRenderer, ThinkingPartRenderer
  └─ reads: stopTick, endedSet, unpairedCallTick
  └─ provides: shouldBeExpanded(), onToggle()

ChatView (provides nothing collapse-related — consumed via imports)
```

## Interface design options

### Option A: Hook-based `createCollapseState`

```typescript
// One module, one hook, one interface
export type CollapseTrigger =
  | { type: "always-expanded" }           // new result just arrived
  | { type: "auto-collapse"; ms: number } // streaming content timer
  | { type: "collapse-on-tick" }          // unpaired call or stream end
  | { type: "never-collapse" }            // user has toggled manually

export interface CollapseState {
  expanded(): boolean;
  toggle(): void;
  /** Call when streaming content updates (resets auto-collapse timer) */
  onContentUpdate(): void;
}
```

**Usage example:**

```typescript
// In ToolResultPartRenderer:
const collapse = createCollapseState({
  initiallyExpanded: isNew || (isLoading && !wasCollapsed),
  trigger: { type: "auto-collapse", ms: 1500 },
  resetOnUnpairedCall: true,
});

// In ThinkingPartRenderer:
const collapse = createCollapseState({
  initiallyExpanded: isLoading && !endedSet.has(msgId),
  trigger: { type: "collapse-on-tick" },
});
```

**What's hidden:** All timer management, user-interaction gating, stopTick from ChatView, endedSet tracking, unpaired-call tick monitoring, `collapseMemory` module-level map, `hasLoadedSinceMount` flag.

**Trade-offs:** The hook encapsulates complexity well, but still needs access to `stopTick` and `endedSet` from above. These can be provided via Solid's context or passed explicitly — either way the dependency is clearer than the current context-crossing-4-files arrangement.

### Option B: Pure function + reactive stream

```typescript
// All inputs as signals, outputs as a signal
export interface CollapseInputs {
  expandedOverride: Accessor<boolean>;    // usually false
  isLoading: Accessor<boolean>;
  stopTick: Accessor<number>;
  endedSet: Accessor<Set<string>>;
  unpairedTick: Accessor<number>;
  autoCollapseMs?: number;
  resetTrigger?: Accessor<unknown>;       // content changes reset timer
}

export function useCollapse(inputs: CollapseInputs): {
  expanded: Accessor<boolean>;
  toggle: () => void;
}
```

**Usage:** All inputs are wired at the call site — `CollapsibleSection` becomes a pure view with no logic.

**Trade-offs:** Pushes complexity back to the caller. Every caller must wire up `stopTick`, `endedSet`, etc. But the module controls the state machine, eliminating the 4-file chase.

### Recommendation

**Option A** — the hook. It reduces the interface each caller provides from 5-6 scattered props to 2-3 named arguments. The `CollapsibleSection` component can then drop all collapse-trigger props and accept only `label`, `children`, and a `collapseState`. That makes the component "dumb" and the hook testable in isolation.

## Deepening strategy

- **Dependency category:** In-process. All callers are in the same Solid component tree.
- **Seam placement:** `createCollapseState` is the seam. Everything collapse-related — auto-timer, stop-tick, user-interaction flag, memory map — lives behind it.
- **Adapters:** None needed. One port (config → state), all in Solid's reactive graph.
- **Testing:** Delete `CollapsibleSection.test.tsx`'s auto-collapse and collapse-on-tick tests — those move to the hook. `CollapsibleSection` becomes a pure presentational component testable with a simple `expanded: boolean` prop. The 4 most complex test scenarios in `ChatView.test.tsx` (key stability, sequential calls, paired results, unpaired calls) simplify because the collapse state machine is tested once in the hook, not implicitly across 15+ integration scenarios.

## Benefits

- **Locality:** one module owns all collapse timing; bugs concentrate there
- **Leverage:** delete 3 collapse-trigger props from CollapsibleSection, remove 2 contexts from ChatView
- **Test surface shrinks:** replace 6+ implicit timing tests with one hook test suite
- **Delete 4-file trace:** understand collapse with one `import`

## Recommendation strength

**Strong**
