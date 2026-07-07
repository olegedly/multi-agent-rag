import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createRoot } from "solid-js";
import {
  type Conversation,
  type ConversationPersistence,
  type ConversationStore,
  createConversationStore,
  localStoragePersistence,
} from "../store";

// ── FakePersistence: Map-backed, no real localStorage ──

class FakePersistence implements ConversationPersistence {
  private store = new Map<string, Conversation>();
  private lastOpened: string | undefined;

  loadAll(): Conversation[] {
    return Array.from(this.store.values());
  }

  save(conv: Conversation): void {
    this.store.set(conv.id, { ...conv });
  }

  remove(id: string): void {
    this.store.delete(id);
  }

  loadLastOpened(): string | undefined {
    return this.lastOpened;
  }

  saveLastOpened(id: string): void {
    this.lastOpened = id;
  }
}

const TEST_CORPUS_ID = "315e41aa-8657-46c0-ac4b-ea4355babf0a";

function makeStore(persistence?: ConversationPersistence) {
  let store!: ConversationStore;
  let dispose: (() => void) | undefined;
  createRoot((rd) => {
    store = createConversationStore({ persistence, defaultCorpusId: TEST_CORPUS_ID });
    dispose = rd;
  });
  return { store, dispose };
}

describe("ConversationPersistence injection", () => {
  it("injects a FakePersistence and never touches real localStorage", () => {
    const persistence = new FakePersistence();

    const { store, dispose } = makeStore(persistence);

    expect(store.conversations().length).toBe(1);
    expect(store.currentId()).toBeTruthy();

    // Real localStorage must be untouched
    let lsCount = 0;
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("conversation:")) lsCount++;
    }
    expect(lsCount).toBe(0);

    // The fake should hold the conversation
    const loaded = persistence.loadAll();
    expect(loaded.length).toBe(1);
    expect(loaded[0].id).toBe(store.currentId());

    dispose?.();
  });
});

describe("ConversationStore", () => {
  let persistence: FakePersistence;
  let store: ConversationStore;
  let dispose: (() => void) | undefined;

  beforeEach(() => {
    persistence = new FakePersistence();
    const result = makeStore(persistence);
    store = result.store;
    dispose = result.dispose;
  });

  afterEach(() => {
    dispose?.();
  });

  it("auto-creates one empty conversation on first use and selects it", () => {
    const list = store.conversations();
    expect(list.length).toBe(1);
    expect(store.currentId()).toBe(list[0].id);
    expect(list[0].messages).toEqual([]);
    expect(list[0].title).toBe("New conversation");
  });

  it("creates a conversation with a corpusId", () => {
    const conv = store.conversations()[0];
    expect(conv.corpusId).toBe(TEST_CORPUS_ID);
  });

  it("creates a conversation with an updatedAt equal to createdAt", () => {
    const conv = store.conversations()[0];
    expect(conv.updatedAt).toBe(conv.createdAt);
  });

  it("sets updatedAt when saving messages", () => {
    const before = Date.now();
    store.saveCurrentMessages([
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Hello" }] },
    ]);
    const conv = store.conversations().find((c) => c.id === store.currentId())!;
    expect(conv.updatedAt).toBeGreaterThanOrEqual(before);
  });

  it("creates a new conversation with the default corpusId", () => {
    store.createNew();
    const conv = store.conversations().find((c) => c.id === store.currentId())!;
    expect(conv.corpusId).toBe(TEST_CORPUS_ID);
  });

  it("creates a new conversation with a given corpusId", () => {
    store.createNew("other-corpus-uuid");
    const conv = store.conversations().find((c) => c.id === store.currentId())!;
    expect(conv.corpusId).toBe("other-corpus-uuid");
  });

  it("sorts conversations by updatedAt descending", () => {
    store.updateCurrentTitle("Older");
    const firstId = store.currentId();
    // Wait a tick so timestamps differ
    store.saveCurrentMessages([
      { id: "m1", role: "user" as const, parts: [{ type: "text" as const, content: "Msg" }] },
    ]);

    store.createNew();
    store.updateCurrentTitle("Newer");
    const secondId = store.currentId();

    const list = store.conversations();
    expect(list.length).toBe(2);
    // Newer (with updatedAt from message) should come first
    const firstConv = list[0];
    const secondConv = list[1];
    expect(firstConv.updatedAt).toBeGreaterThanOrEqual(secondConv.updatedAt);
  });

  it("creates a new empty conversation and selects it", () => {
    store.updateCurrentTitle("Existing convo");
    const firstId = store.currentId();

    store.createNew();

    expect(store.conversations().length).toBe(2);
    expect(store.currentId()).not.toBe(firstId);
    const current = store.conversations().find((c) => c.id === store.currentId());
    expect(current!.title).toBe("New conversation");
    expect(current!.messages).toEqual([]);
  });

  it("switches to another conversation by id", () => {
    const firstId = store.currentId();
    store.createNew();
    const secondId = store.currentId();

    store.switchTo(firstId);
    expect(store.currentId()).toBe(firstId);

    store.switchTo(secondId);
    expect(store.currentId()).toBe(secondId);
  });

  it("saves and retrieves messages for the current conversation", () => {
    const messages = [
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Hello" }] },
    ];
    store.saveCurrentMessages(messages);

    const retrieved = store.getCurrentMessages();
    expect(retrieved).toEqual(messages);
  });

  it("preserves messages after unmount+remount (data survives)", () => {
    const messages = [
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Persist me" }] },
    ];
    store.saveCurrentMessages(messages);
    const convId = store.currentId();

    // Simulate unmount/remount — dispose store, create new one with same persistence
    dispose?.();
    createRoot((rd) => {
      store = createConversationStore({ persistence, defaultCorpusId: TEST_CORPUS_ID });
      dispose = rd;
    });

    expect(store.currentId()).toBe(convId);
    expect(store.getCurrentMessages()).toEqual(messages);
  });

  it("removes a conversation and switches to next", () => {
    store.updateCurrentTitle("First");
    store.createNew();
    store.updateCurrentTitle("Second");
    const secondId = store.currentId();
    store.createNew();
    store.updateCurrentTitle("Third");

    store.switchTo(secondId);
    store.removeCurrent();

    expect(store.conversations().length).toBe(2);
    expect(store.currentId()).not.toBe(secondId);
  });

  it("handles deleting the last conversation gracefully", () => {
    expect(store.conversations().length).toBe(1);
    const lastId = store.currentId();
    store.removeCurrent();

    expect(store.conversations().length).toBe(1);
    expect(store.currentId()).not.toBe(lastId);
  });

  it("updates the current conversation's title", () => {
    store.updateCurrentTitle("My new title");
    const current = store.conversations().find((c) => c.id === store.currentId())!;
    expect(current.title).toBe("My new title");
  });

  it("does not create a second 'New conversation' when one already exists", () => {
    expect(store.conversations().length).toBe(1);
    const existingId = store.currentId();

    store.createNew();

    expect(store.conversations().length).toBe(1);
    expect(store.currentId()).toBe(existingId);
  });

  it("does not de-duplicate 'New conversation' across different corpusIds", () => {
    // Create one empty convo in corpus A
    const firstId = store.currentId();
    // Create an empty convo in corpus B — should create new, not de-dup
    store.createNew("corpus-b");
    expect(store.conversations().length).toBe(2);
  });

  it("does create a second 'New conversation' when the first has messages", () => {
    store.saveCurrentMessages([
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Hello" }] },
    ]);
    const firstId = store.currentId();

    store.createNew();

    expect(store.conversations().length).toBe(2);
    expect(store.currentId()).not.toBe(firstId);
    const current = store.conversations().find((c) => c.id === store.currentId());
    expect(current!.title).toBe("New conversation");
    expect(current!.messages).toEqual([]);
  });

  it("does create a second 'New conversation' when the first has a custom title", () => {
    store.updateCurrentTitle("My query about AI");
    const firstId = store.currentId();

    store.createNew();

    expect(store.conversations().length).toBe(2);
    expect(store.currentId()).not.toBe(firstId);
  });

  it("loads pre-existing conversations from persistence on init", () => {
    dispose?.();

    // Pre-seed a fresh fake persistence
    const freshPersistence = new FakePersistence();
    const id1 = crypto.randomUUID();
    const id2 = crypto.randomUUID();
    const conv1: Conversation = {
      id: id1,
      corpusId: TEST_CORPUS_ID,
      title: "Conversation 1",
      createdAt: Date.now() - 1000,
      updatedAt: Date.now() - 1000,
      messages: [{ id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "A" }] }],
      mode: "single",
    };
    const conv2: Conversation = {
      id: id2,
      corpusId: TEST_CORPUS_ID,
      title: "Conversation 2",
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
      mode: "single",
    };
    freshPersistence.save(conv1);
    freshPersistence.save(conv2);
    freshPersistence.saveLastOpened(id2);

    createRoot((rd) => {
      store = createConversationStore({ persistence: freshPersistence, defaultCorpusId: TEST_CORPUS_ID });
      dispose = rd;
    });

    expect(store.conversations().length).toBe(2);
    expect(store.currentId()).toBe(id2);
  });

  it("migrates legacy conversations without corpusId to the default", () => {
    dispose?.();

    const freshPersistence = new FakePersistence();
    const id1 = crypto.randomUUID();
    // Legacy conversation — no corpusId field
    const legacy: Conversation = {
      id: id1,
      corpusId: "" as any,
      title: "Legacy",
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
      mode: "single",
    };
    // Strip corpusId to simulate old data
    const raw = { ...legacy, corpusId: undefined } as any;
    delete raw.corpusId;
    freshPersistence.save(raw);

    createRoot((rd) => {
      store = createConversationStore({ persistence: freshPersistence, defaultCorpusId: TEST_CORPUS_ID });
      dispose = rd;
    });

    const migrated = store.conversations()[0];
    expect(migrated.corpusId).toBe(TEST_CORPUS_ID);

    // Also verify it was persisted
    const saved = freshPersistence.loadAll();
    expect(saved[0].corpusId).toBe(TEST_CORPUS_ID);
  });
});

describe("localStoragePersistence (integration)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("loads existing conversations from localStorage on init (default persistence)", () => {
    const id1 = crypto.randomUUID();
    const id2 = crypto.randomUUID();
    const conv1: Conversation = {
      id: id1,
      corpusId: TEST_CORPUS_ID,
      title: "Conversation 1",
      createdAt: Date.now() - 1000,
      updatedAt: Date.now() - 1000,
      messages: [{ id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "A" }] }],
      mode: "single",
    };
    const conv2: Conversation = {
      id: id2,
      corpusId: TEST_CORPUS_ID,
      title: "Conversation 2",
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
      mode: "single",
    };
    localStorage.setItem(`conversation:${id1}`, JSON.stringify(conv1));
    localStorage.setItem(`conversation:${id2}`, JSON.stringify(conv2));
    localStorage.setItem("conversation:lastOpened", id2);

    let store!: ConversationStore;
    createRoot((rd) => {
      store = createConversationStore({ defaultCorpusId: TEST_CORPUS_ID });
      return rd;
    });

    expect(store!.conversations().length).toBe(2);
    expect(store!.currentId()).toBe(id2);
  });

  it("tolerates corrupt localStorage gracefully", () => {
    const origWarn = console.warn;
    console.warn = () => {};
    localStorage.setItem("conversation:bad", "not valid json");

    let store!: ConversationStore;
    createRoot((rd) => {
      store = createConversationStore({ defaultCorpusId: TEST_CORPUS_ID });
      return rd;
    });
    console.warn = origWarn;

    expect(store!.conversations().length).toBeGreaterThanOrEqual(1);
  });
});
