# ADR-0009: Tool Result Collapse Strategy — Collapse Memory + Passive Expanded Signal

Tool result "Result" collapsible sections will be managed by a **module-level collapse memory map** (`Map<sectionKey, bool>`), a **passive `createSignal`** that only captures the initial `expanded` prop and never syncs with it again, and a **composite `collapseOnTick`** that combines the existing `nextToolCallTick` (unpaired call arrives) with `endedSet.has(msgId)` (agent finishes).

**Status:** accepted, implemented.

## Problem

Tool result collapsibles need to:

1. **Expand** when a result first appears during streaming ✅ (always worked)
2. **Collapse immediately** when the next unpaired tool-call appears in the same message (so only one result is visible at a time)
3. **Collapse 1.5s after streaming stops** (lazy collapse of the final result)
4. **Collapse immediately** when the agent sends `TEXT_MESSAGE_END`
5. **Stay collapsed when loaded from storage** ✅ (always worked)
6. **Stay collapsed across `<For>` re-creations** — SolidJS `<For>` destroys and re-mounts `ToolResultPartRenderer` on every streaming update because `UIMessage` references change; `createSignal` state is lost.

Previous approaches failed because they relied on component-lifecycle state (`createSignal`, `wasLoading` closures) which `<For>` resets on re-creation.

## Considered options

- **Reactive `expanded` prop sync** (`createEffect` that calls `setExpanded(props.expanded)`) — rejected. When `isLoading` transitions to `false`, the sync runs and sets `expanded()` to `false` immediately, BEFORE the 1.5s auto-collapse timer can start. The timer effect checks `expanded()` → `false` → skips timer creation. Also doesn't solve the re-expand-on-re-creation problem.

- **Component reference stabilization** (`<Index>` instead of `<For>`) — rejected. `<Index>` in SolidJS doesn't synchronously propagate element changes to child components in the test environment, causing structural rendering failures. Also requires a larger refactor of `MessageList`.

- **Store-based approach** (SolidJS store, context-based map) — rejected as over-engineered. A plain `Map<string, bool>` at module scope is simpler, testable, and trivially cleared on loading transitions.

## Decision

Three changes, two files:

### 1. Collapse memory (`toolResultTracker.ts`)

A module-level `Map<sectionKey, bool>` that persists across component re-creations:

```ts
const collapseMemory = new Map<string, boolean>();

export function markCollapsed(msgId: string, toolCallId: string): void {
  collapseMemory.set(`${msgId}:${toolCallId}`, true);
}

export function isCollapsedInSession(msgId: string, toolCallId: string): boolean {
  return collapseMemory.get(`${msgId}:${toolCallId}`) ?? false;
}
```

Cleared when a new loading session starts (same `createEffect` that clears `seenKeys`):

```ts
if (now && !wasLoading) {
  seenKeys.clear();
  clearCollapseMemory();
  prevUnpairedCount = 0;
}
```

### 2. Passive `createSignal` (`CollapsibleSection.tsx`)

Reverted to `createSignal(props.expanded ?? true)` — no reactive effect. The signal captures the correct initial value at mount time and NEVER syncs with the prop afterward. State only changes via:

- `collapseOnTick` deferred effect (tick > 0 → collapse)
- `autoCollapseMs` timer (1.5s → collapse)
- User toggle

This prevents the timer race: `expanded()` stays true after `isLoading` transitions, so `setupAutoCollapse()` creates the timer correctly.

### 3. Composite expand/collapse logic (`ToolResultPartRenderer.tsx`)

```ts
// The initial signal value: expand on first appearance, or during loading
// IF this section has never been collapsed this session.
const stuckExpanded = props.isNew || (props.isLoading && !wasCollapsed);

// Collapse triggers: next unpaired call, OR message ended
const collapseTick = props.nextToolCallTick + (getEndedSet().has(props.msgId) ? 1 : 0);
```

Key insight: `stuckExpanded` is a **static expression** evaluated once at render time. It does NOT track signal changes dynamically. The `createSignal` captures its initial value, and after that, collapse state is managed entirely by the timer/tick/toggle mechanisms inside `CollapsibleSection`.

## Collapse lifecycle

| Phase | What happens |
|---|---|
| **First mount during loading** | `isNew=true` → `stuckExpanded=true` → expanded |
| **Next unpaired call arrives** | `nextToolCallTick` increments → `collapseOnTick` fires → collapses. `onToggle(false)` → `markCollapsed()`. |
| **Streaming update (re-created by `<For>`)** | `wasCollapsed=true` → `stuckExpanded = isNew \|\| (true && !true) = false` → stays collapsed |
| **Streaming ends, waiting** | `resetTimerOn` changes → timer starts → 1.5s → collapses → `markCollapsed()` |
| **Agent finishes** | `endedSet.has(msgId)` becomes true → `collapseTick` increments → collapses |
| **Loaded from storage** | `isNew=false`, `isLoading=false` → `stuckExpanded=false` → collapsed |
| **New streaming session** | `clearCollapseMemory()` in tracker → fresh slate |

## Consequences

- **No reactive prop sync in CollapsibleSection** — the `expanded` prop is a "hint" used only at mount. This is a semantic shift: the prop no longer controls state reactively. It's correct because the timer/tick/toggle are the only legitimate state transitions after mount.
- **Module-level Map is manual cleanup** — must be cleared when loading transitions `false→true`. Currently done in `createToolResultTracker`'s loading-detection effect. If loading transitions are missed (e.g., direct storage load without setting loading), the map retains stale entries (harmless — they're looked up by msgId+toolCallId which are unique per session).
- **`sectionKey` uses `msgId:toolCallId`** — stable across message mutations because both IDs are assigned server-side and don't change during streaming.
- **Tests**: all 143 pass. No test changes needed.
