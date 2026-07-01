# Handoff: Issue #26 — Conversation Switching Bug

## What Was Built

Implementation of GitHub issue #26 (frontend routing, landing page, corpus-aware conversations).

### Infrastructure (done)
- `@solidjs/router` v0.16.1 installed, `@/` Vite alias configured
- Domain-based directory structure: `app/`, `theme/`, `layout/`, `corpora/`, `chat/`, `conversations/`
- Existing files migrated into new structure, all imports updated

### Data Layer (done, tested)
- `Conversation` model: added `corpusId: string` (required) + `updatedAt: number`
- `createConversation(corpusId)` parameterized, `createNew(corpusId?)` with per-corpus dedup
- `saveCurrentMessages` sets `updatedAt`, sorting by `updatedAt` descending
- Legacy migration: conversations without `corpusId` get assigned the first corpus UUID
- `ConversationStoreProvider` + `useConversationStore()` context

### Corpus Layer (done, tested)
- `CorporaContext` / `CorporaProvider` — fetches `GET /api/corpora` once, exposes `resolveSlug`, `resolveId`, `retry`
- `LandingPage` — corpus cards grid with loading/error/empty states

### Routing & Layout (done, built)
- `<Router root={RootLayout}>` with `/` (LandingPage) and `/corpora/:slug` (CorpusChatPage)
- `RootLayout` — header + sidebar (conditional on corpus route)
- `Header` — dynamic title, home link on corpus routes
- `Sidebar` — filters conversations by `activeCorpusId`

### Tests
199 tests passing (19 files), including 10 new tests for CorporaContext, LandingPage, CorpusChatPage, and store migration.

---

## 🚨 Critical Bug: Conversation Switching Doesn't Work

### Symptoms
1. **Clicking a different conversation in the sidebar does NOT update the chat view** — the messages shown stay the same as the initially loaded conversation.
2. **The sidebar highlight does update** — the clicked item becomes visually selected (checked via logs: `store.switchTo(id)` runs, `store.currentId()` changes).
3. **There is a memory leak** — every conversation switch creates a new `useChat` instance that is not properly cleaned up.

### Root Cause Analysis

The trigger chain:
```
Sidebar click → props.onSelect(id) → store.switchTo(id) → store.currentId() updates
```

The core problem is how `CorpusChatPage` reacts to `store.currentId()` changes to swap the chat content.

**Attempt 1 — `createEffect` + `chat.setMessages(msgs)`:** The effect fires and calls `chat.setMessages()`, but TanStack's `setMessages` (which maps to `setMessagesManually` → `ChatClient.processor.setMessages()`) does **not** fire the `onMessagesChange` callback. So the SolidJS `messages` signal inside `useChat` never updates, and the UI stays frozen on the old messages.

Evidence from TanStack source (`use-chat.js` line 106-108, 143):
```js
const setMessagesManually = (newMessages) => {
    client().setMessagesManually(newMessages);  // no onMessagesChange call
};
return { setMessages: setMessagesManually };
```

**Attempt 2 — Module-level switch handler + `triggerConversationSwitch()`:** Same issue — calling `chat.setMessages()` from outside a reactive effect still goes through the same `setMessagesManually` path that doesn't propagate to the SolidJS signal.

**Attempt 3 — Toggle `visible` signal + `<Show>` to force remount:** Worked (chat changed) but caused a white flash (off-frame) and broke sidebar state tracking.

**Attempt 4 — `<For>` with single-element array to key by `convId` (current):** Still doesn't update the chat content.

### Memory Leak

Every call to `store.switchTo(id)` creates a new `ConversationChat` component mount (via `For` remount), which creates a new `useChat` instance with its own SSE connection and `ChatClient`. If old instances aren't properly disposed, connections accumulate.

The `useChat` hook has:
```js
onCleanup(() => {
    client().unsubscribe();
    client().stop();
    client().dispose();
});
```

But it's unclear whether this actually fires reliably on `For` item removal in SolidJS.

### Where the Bug Likely Lives

`/home/morket/build/code/projects/multi-agent-rag/frontend/src/corpora/CorpusChatPage.tsx`

The `ConversationChat` component + `<For>` pattern. The fix should ensure either:
1. `chat.setMessages()` propagates to the SolidJS signal (need to understand TanStack's internal state management better), or
2. The component remount actually works (check if `<For>` properly unmounts old and mounts new), or
3. A completely different approach: don't fight TanStack's reactivity — instead keep ONE `useChat` instance at the `CorpusChatPage` level and manually manage the messages signal (e.g., wrap `chat.messages` in our own signal that we can replace directly).

### The `deriveTitle` Effect Loop (Potential Additional Bug)

In `ConversationChat`, there's a `createEffect` that saves messages on every change:
```ts
createEffect(() => {
    const msgs = chat.messages();
    if (msgs.length > 0) {
        store.saveCurrentMessages(msgs);
        const title = deriveTitle(msgs);
        if (title) store.updateCurrentTitle(title);
    }
});
```

`store.saveCurrentMessages` sets `updatedAt` which triggers `store.conversations()` to re-sort, which may cause the sidebar to re-render. This is likely fine but worth verifying it doesn't create a loop.

---

## Design Decisions (from GRILL-ME-26.md)

Full decision log at `/home/morket/build/code/projects/multi-agent-rag/GRILL-ME-26.md`.

Key architecture:
- `ConversationStore` (persistence) lives at App level via context
- Chat session (SSE, streaming) lives inside `CorpusChatPage` route component
- `Sidebar` self-filters conversations by `activeCorpusId`
- History-based routing with `@solidjs/router`
- Domain-based directory structure

---

## Next Steps for Fresh Agent

1. **Fix the conversation switching bug.** The core issue is that TanStack's `chat.setMessages()` doesn't update the SolidJS `messages` signal. Options:
   - Use `onMessagesChange` callback in `useChat` options to catch external message sets
   - Expose a direct signal setter from the chat instance
   - Abandon `useChat` from TanStack entirely and manage SSE + messages manually
   - Find the right API to force TanStack to sync its internal state to SolidJS

2. **Fix the memory leak.** Ensure `ConversationChat` teardown (SSE disconnect, ChatClient dispose) runs reliably. Verify with DevTools or memory profiling.

3. **Fix the persist-on-switch issue.** When switching conversations, current chat messages must be saved to the old conversation *before* loading the new one's messages.

4. **Verify sidebar selection highlighting** works consistently alongside the chat content swap.

All test infrastructure is in place — TDD at each step.
