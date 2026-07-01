# Put localStorage persistence behind an adapter seam

## Files involved

`frontend/src/conversations/store.ts`

## Problem

`store.ts` bakes localStorage I/O into `saveConversation`, `loadAllConversations`, `removeConversation` as module-scoped functions — the persistence strategy cannot be swapped, tested independently, or even observed without clearing real localStorage.

## Topology (before)

```
createConversationStore()
  │
  ├─ loadAllConversations()      ← calls localStorage.getItem directly
  ├─ saveConversation(conv)      ← calls localStorage.setItem directly
  ├─ removeConversation(id)      ← calls localStorage.removeItem directly
  ├─ saveLastOpened(id)          ← localStorage.setItem
  ├─ loadLastOpened()            ← localStorage.getItem
  │
  └─ All return raw localStorage data — no seam, no adapter
```

Tests clear `localStorage` in every `beforeEach`, then rely on the store being the only consumer. Switching to IndexedDB or a remote backend means rewriting `createConversationStore` entirely — the persistence is not behind a seam.

## Solution

Define a `ConversationPersistence` interface and inject it into the store factory, defaulting to the existing localStorage implementation.

## Topology (after)

```
ConversationPersistence (interface: load → save → remove → loadLastOpened → saveLastOpened)
  │
  ├─ LocalStoragePersistence (default implementation, extracted as-is)
  │
  └─ injectable into createConversationStore({ persistence })

createConversationStore({ persistence })
  │
  └─ calls persistence.load(), persistence.save(), etc.
     → no direct localStorage access

Tests: supply FakePersistence backed by Map → no localStorage pollution
```

## Interface design options

### Option A: Minimal interface, one default export

```typescript
export interface ConversationPersistence {
  loadAll(): Conversation[];
  save(conv: Conversation): void;        // throws QuotaExceededError
  remove(id: string): void;
  loadLastOpened(): string | undefined;
  saveLastOpened(id: string): void;
}

export const localStoragePersistence: ConversationPersistence = {
  loadAll() { /* existing loadAllConversations body */ },
  save(conv) { /* existing saveConversation body */ },
  // ...
};

export function createConversationStore(opts?: {
  persistence?: ConversationPersistence;
}): ConversationStore {
  const p = opts?.persistence ?? localStoragePersistence;
  const loaded = p.loadAll();
  // ... rest uses `p` everywhere it now calls localStorage directly
}
```

**What's hidden:** All `localStorage` key prefix logic, JSON parse/stringify, error handling for corrupt keys, fallback on parse failure, quota-exceeded detection. The store never touches `localStorage` directly.

### Option B: Split load vs. save into two interfaces

```typescript
export interface ConversationLoader {
  loadAll(): Conversation[];
  loadLastOpened(): string | undefined;
}
export interface ConversationWriter {
  save(conv: Conversation): void;
  remove(id: string): void;
  saveLastOpened(id: string): void;
}
```

**Trade-offs:** Useful if you want to make persistence read-only (e.g., a demo mode). But adds an extra type to maintain. For now, one interface is simpler and nothing needs read-only persistence.

### Recommendation

**Option A.** The interface has 5 methods — the same surface area as the current module-scoped functions. Extracting them into an interface turns ad-hoc functions into a named contract without adding indirection.

## Deepening strategy

- **Dependency category:** In-process (local storage). But the interface is a **ports & adapters** seam — tests supply a `Map`-backed fake.
- **Seam placement:** The `ConversationPersistence` interface is the seam. The store talks only to the interface.
- **Adapters:** One adapter exists (`localStoragePersistence`). A second (IndexedDB, remote sync) makes the seam real. Currently: *one adapter = hypothetical seam*. When a second appears: *two = real*.
- **Testing:** The existing `store.test.ts` and `hmrDataLoss.test.ts` both clear `localStorage` in `beforeEach` — a side effect that prevents parallel test runs and pollutes the test environment. With a `FakePersistence(Map)`, tests run in complete isolation. The `localStoragePersistence` adapter is tested once in a separate file with a fresh localStorage mock.

## Benefits

- **Tests isolate:** no localStorage pollution between tests or parallel runs
- **Seam ready:** swap backend without touching store logic
- **Locality:** all persistence edge cases (corrupt keys, quota, prefix logic) concentrate in one adapter
- **Leverage:** 5-method interface supports N test fakes, M storage backends
- **Deletion test:** removing localStoragePersistence and keeping only the interface + FakePersistence still passes all store tests — the seam is proven

## Recommendation strength

**Worth exploring**

(Not *Strong* because the current localStorage approach is functional and not causing bugs. The win is test isolation and future-proofing.)
