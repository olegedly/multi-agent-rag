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

describe("ConversationPersistence injection", () => {
  it("injects a FakePersistence and never touches real localStorage", () => {
    const persistence = new FakePersistence();

    let store!: ConversationStore;
    let dispose: (() => void) | undefined;

    createRoot((rd) => {
      store = createConversationStore({ persistence });
      dispose = rd;
    });

    // The store should have auto-created one conversation through the fake
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

describe("localStoragePersistence adapter", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("saves and loads a conversation", () => {
    const conv: Conversation = {
      id: crypto.randomUUID(),
      title: "Test",
      createdAt: Date.now(),
      messages: [],
      agentNames: {},
    };

    localStoragePersistence.save(conv);
    const loaded = localStoragePersistence.loadAll();
    expect(loaded.length).toBe(1);
    expect(loaded[0].id).toBe(conv.id);
    expect(loaded[0].title).toBe("Test");
  });

  it("removes a conversation", () => {
    const conv: Conversation = {
      id: crypto.randomUUID(),
      title: "Test",
      createdAt: Date.now(),
      messages: [],
      agentNames: {},
    };

    localStoragePersistence.save(conv);
    expect(localStoragePersistence.loadAll().length).toBe(1);

    localStoragePersistence.remove(conv.id);
    expect(localStoragePersistence.loadAll().length).toBe(0);
  });

  it("round-trips lastOpened", () => {
    const id = crypto.randomUUID();
    localStoragePersistence.saveLastOpened(id);
    expect(localStoragePersistence.loadLastOpened()).toBe(id);

    localStoragePersistence.saveLastOpened("other-id");
    expect(localStoragePersistence.loadLastOpened()).toBe("other-id");
  });

  it("returns undefined when no lastOpened stored", () => {
    expect(localStoragePersistence.loadLastOpened()).toBeUndefined();
  });
});
