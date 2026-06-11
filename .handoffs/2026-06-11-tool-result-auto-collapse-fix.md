# Handoff: Tool Result Auto-Collapse, Scroll Lock, Error Clearing, Part Grouping

**Date:** 2026-06-11
**Focus:** Three interrelated bugs in the ChatView `ToolResultPartRenderer` and ChatStore

---

## State Summary

All tests (59) pass. `tsc --noEmit` passes. `vite build` passes. But **runtime behavior is broken** — user reports that after this session's changes:

1. **Tool results never expand at all** — they stay collapsed permanently (no auto-expand on new results)
2. **Scroll lock still forces viewport to bottom** — user can't resist
3. **Error still visible after conversation switch** — stale error banner remains
4. **Part grouping** (tool-call + result paired visually) — this feature may actually be working, unclear

---

## What We're Working With

- **`frontend/src/conversations/ChatView.tsx`** — 670 lines, component exports `ChatView`
- **`frontend/src/conversations/useChatStore.ts`** — wraps `useChat` from `@tanstack/ai-solid`, provides `isLoading()`, `error()`, `messages` etc.
- `@tanstack/ai-client` types defined in `node_modules/@tanstack/ai-client/dist/esm/types.ts`
- `@tanstack/ai-solid` types in `node_modules/@tanstack/ai-solid/dist/types.d.ts`
- Tests: `frontend/src/conversations/__tests__/ChatView.test.tsx`

---

## Current Architecture (what's in ChatView.tsx now)

### Part Grouping (`groupParts`)
A pure function at the top of the file that walks `MessagePart[]` and pairs each `tool-call` with the immediately following `tool-result` matching by `toolCallId === part.id`. Produces `GroupItem[]` where items are either `{type:"solo", part}` or `{type:"pair", toolCall, toolResult|null}`.

### Component tree for paired items
```
ChatView
  └─ For each message
       └─ For each groupParts(msg.parts)
            ├─ PairItem → ToolCallPairRenderer
            │              ├─ ToolCallPartRenderer (tool name, badge, args)
            │              └─ ToolResultPartRenderer (checkmark, "Result" chevron, body)
            └─ SoloItem → PartRenderer (text, thinking, orphan tool-result)
```

### Auto-collapse system
Uses three mechanisms:

1. **`isNewToolResult(msgId, toolCallId)`** — checks `seenToolPartKeys` set. Returns `true` if the part wasn't seen before loading started. Used to set initial `expanded` signal state in `ToolResultPartRenderer`.

2. **`seenToolPartKeys`** — a `Set<string>` of `"${msgId}:${toolCallId}"` snapshotted on mount and at each `loading` state transition. The effect uses `didInitialSnapshot` and `wasLoadingForKeys` guards.

3. **`nextToolCallTick` signal** — a counter that increments every time the tool-call count goes up during loading. `ToolResultPartRenderer` watches it and collapses immediately on change (before the 1.5s timer fires).

4. **`ToolResultPartRenderer`** gets `isNew: boolean` (from parent) and `nextToolCallTick?: number`. If `isNew`, starts expanded with 1.5s auto-collapse timer. The createEffect on `nextToolCallTick` collapses immediately if a new tool call appears.

### Scroll lock
Added `scrollContainerRef` + `onScroll` handler tracking `isUserAtBottom`. Auto-scroll effect checks `isUserAtBottom` before scrolling.

### Error clear
Added `chat.setMessages([])` before loading saved messages in `useChatStore.switchTo()`.

---

## The Actual Bugs (Diagnosis Needed)

### Bug 1: Results never expand (highest priority)
**Symptoms:** `isNewToolResult` always returns `false`, so `ToolResultPartRenderer` gets `props.isNew = false`, which means `createSignal(false)` → result stays collapsed. The 1.5s timer never fires because `if (!props.isNew) return;`.

**Suspected root cause:** The data flow is:
```
ChatView → groupParts(msg.parts) → PairItem
                                  → `isNewToolResult(msg.id, item.toolResult.toolCallId)`
```

With the new `ToolCallPairRenderer` wrapper, `ToolResultPartRenderer` receives `isNew={props.isNewToolResult}`. But `ToolCallPairRenderer` is passed `isNewToolResult` from the `For` loop, and passes it as `isNew` to `ToolResultPartRenderer`. 

Check the `For` loop — it passes `isNewToolResult={item.toolResult ? isNewToolResult(msg.id, item.toolResult.toolCallId) : false}` to `ToolCallPairRenderer`. But `ToolCallPairRenderer` passes it as `nextToolCallTick={props.nextToolCallTick}` and `isNew={props.isNewToolResult}`. This looks correct at a glance, so the real issue might be in `isNewToolResult()` itself:

- `isNewToolResult()` checks `props.isLoading` — if loading is `false`, returns `false` always
- The snapshot effect may be capturing keys and marking everything as "seen" before loading starts
- The `seenToolPartKeys` set is populated on mount. If the component re-renders and results appear while `loading` transitions, the keys captured at the `loading→true` transition still include every key that existed at that moment. New results *after* that point would be genuinely new. But if results appear after loading but `isLoading` is `true`, the check `!seenToolPartKeys.has(key)` should pass.

**Debugging strategy:** Add `console.log` in `isNewToolResult()` showing the key, the set contents, and the return value. Also log `props.isNew` inside `ToolResultPartRenderer`. Watch the network panel to see when results arrive vs when `isLoading` toggles.

### Bug 2: Scroll lock doesn't work
The `handleScroll` function fires and sets `isUserAtBottom`. But the auto-scroll `createEffect` tracks `props.messages()`. On every message change (including streaming text parts), it checks `isUserAtBottom`. If the user scrolled up and messages change, it respects the flag. **But** maybe the flag resets improperly — when messages change and the container height grows, `scrollHeight` increases but `scrollTop` stays where it was (from user scroll), so the calculation `scrollHeight - scrollTop - clientHeight < threshold` should work. Need to verify `handleScroll` is actually attached and firing.

### Bug 3: Error not clearing
The `chat.setMessages([])` call in `switchTo()` should clear the internal error state since the chat client resets on `setMessages`. But maybe the `error()` accessor still returns the old error until the chat client processes the reset. Could try calling `chat.clear()` instead, or check if there's a `chat.setError(null)` method.

---

## Current File State

Key files (all at root of project):

| File | What's In It |
|---|---|
| `frontend/src/conversations/ChatView.tsx` | Main component — all renderers, grouping, scroll logic, auto-collapse |
| `frontend/src/conversations/useChatStore.ts` | Chat store — wraps `useChat`, `switchTo`, error handling |
| `frontend/src/conversations/store.ts` | Conversation persistence in localStorage |
| `frontend/src/theme.css` | CSS variables for light/dark themes |
| `frontend/src/index.css` | Tailwind imports + global styles |
| `frontend/src/conversations/__tests__/ChatView.test.tsx` | 59 tests for ChatView |

No ADRs exist. `CONTEXT.md` at root has domain glossary.

---

## Recommended Next Steps

1. **Fix Bug 1 (never expands):** Add console.log debugging, trace the data flow. Simplest fix might be to remove the `isNew` gating entirely and always start expanded for results that appear while `isLoading` is true (regardless of snapshot).

2. **Fix Bug 2 (scroll lock):** Verify `handleScroll` fires by logging. The `onScroll` attribute uses `handleScroll` which accesses `scrollContainerRef` — make sure the ref is attached properly.

3. **Fix Bug 3 (error clear):** Try `chat.clear()` instead of `chat.setMessages([])` in `switchTo`, or reset `error()` via a direct method.

4. **Add tests:** Add tests for the auto-expand/auto-collapse behavior, scroll lock behavior, and error clearing on switch.
