# Add corpus config seam between App and chat connection

## Files involved

`frontend/src/conversations/useChatStore.ts`, `frontend/src/App.tsx`

## Problem

The corpus slug `eu-ai-act` is hard-coded in the chat connection string, blocking multi-corpus selection with no adapter seam.

## Topology (before)

```
App.tsx
  └─ useChatStore() ──────────────────────┐
                                          │
  useChat({                                │
    connection:                            │
      fetchServerSentEvents(              │
        "/api/chat/eu-ai-act",  ← HARD-CODED
        { fetchClient: resilientFetch }
      )
  })
```

The backend already supports `/api/chat/<slug>`. The frontend passes no corpus configuration through the pipeline — adding corpus selection means patching the connection string inside the store factory, which is the only place the slug lives.

## Solution

Accept an optional `corpusSlug` parameter in `useChatStore()` with a default of `"eu-ai-act"`, exposing the config seam without breaking existing callers.

## Topology (after)

```
App.tsx
  └─ useChatStore({ corpusSlug: "eu-ai-act" })  ← explicit config
       │
       └─ useChat({ connection: fetchServerSentEvents("/api/chat/<slug>", ...) })

Separate corpus picker component (future):
  └─ onSelect → useChatStore({ corpusSlug: selected })
    → re-creates connection
```

## Interface design options

### Option A: Factory param with default

```typescript
export interface UseChatStoreOptions {
  corpusSlug?: string;         // default "eu-ai-act"
}

export function useChatStore(options?: UseChatStoreOptions) {
  const slug = options?.corpusSlug ?? "eu-ai-act";
  // ... useChat({ connection: fetchServerSentEvents(`/api/chat/${slug}`, ...) })
}
```

Minimal change. One caller (`App.tsx`) adds the param. The slug is reactive — but changing it mid-session means tearing down the old `useChat` connection. That requires handling in the store (stop current session, clear messages, create new connection). The default keeps current behavior.

### Option B: Reactive slug + connection lifecycle

```typescript
export function useChatStore(options?: () => UseChatStoreOptions) {
  // options is a signal so it reacts to corpus selection
  const slug = () => options?.().corpusSlug ?? "eu-ai-act";

  // Re-create useChat when slug changes
  const [chatKey, setChatKey] = createSignal(0);
  createEffect(() => {
    void slug(); // track slug changes
    setChatKey((k) => k + 1);
  });
  // ... conditional useChat creation
}
```

**Trade-offs:** Adding a new `useChat` instance on slug change means preserving the old conversation state. This is non-trivial — `useChat` owns its own message array. You'd need to save current messages, clear, and connect with the new slug. The complexity might not be justified until a corpus picker UI exists.

### Recommendation

**Option A** for now. Expose the param, default to the existing slug, and let a future corpus picker component deal with the lifecycle. The seam is ready without over-engineering the reactive re-wiring.

## Deepening strategy

- **Dependency category:** In-process. The slug is a string config value.
- **Seam placement:** The `UseChatStoreOptions` interface is the seam. Any future corpus picker writes to this config.
- **Adapters:** Zero now (hypothetical). When a second corpus selection mechanism appears (URL param, settings panel, AI-recommended corpus), the config seam is proven — *one = hypothetical, two = real*.
- **Testing:** No test changes needed — existing tests use the default slug. When a corpus picker is added, tests provide a non-default slug and assert the connection URL differs.

## Benefits

- **Seam ready:** corpus slug config exists at the App boundary
- **Zero regression:** default value preserves current behavior
- **Locality:** corpus selection logic concentrates behind one param
- **Leverage:** one config param enables N corpus picker UIs
- **No interface leak:** the connection string stays inside the store

## Recommendation strength

**Worth exploring**
