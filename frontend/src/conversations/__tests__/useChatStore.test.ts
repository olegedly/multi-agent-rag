import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createRoot } from "solid-js";
import { ConversationStore, createConversationStore } from "../store";

// Helper to count localStorage keys with a prefix
function countConversationKeys(): number {
  let count = 0;
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith("conversation:") && key !== LS_LAST_OPENED) count++;
  }
  return count;
}

const LS_LAST_OPENED = "conversation:lastOpened";

function getConversationKeys(): string[] {
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith("conversation:") && key !== LS_LAST_OPENED) keys.push(key);
  }
  return keys;
}

describe("ConversationStore", () => {
  let store: ConversationStore;
  let dispose: (() => void) | undefined;

  beforeEach(() => {
    localStorage.clear();
    dispose = createRoot((rootDispose) => {
      store = createConversationStore();
      return rootDispose;
    });
  });

  afterEach(() => {
    dispose?.();
  });

  it("auto-creates one empty conversation on first use and selects it", () => {
    // After init with empty localStorage, should have one conversation
    const list = store.conversations();
    expect(list.length).toBe(1);
    expect(store.currentId()).toBe(list[0].id);
    expect(list[0].messages).toEqual([]);
    expect(list[0].title).toBe("New conversation");
  });

  it("creates a new empty conversation and selects it", () => {
    // Start with 1 auto-created
    const firstId = store.currentId();
    store.createNew();

    expect(store.conversations().length).toBe(2);
    // New conversation becomes current
    expect(store.currentId()).not.toBe(firstId);
  });

  it("switches to another conversation by id", () => {
    const firstId = store.currentId();
    store.createNew();
    const secondId = store.currentId();

    // Switch back to first
    store.switchTo(firstId);
    expect(store.currentId()).toBe(firstId);

    // Switch to second
    store.switchTo(secondId);
    expect(store.currentId()).toBe(secondId);
  });

  it("saves messages to the current conversation", () => {
    const messages = [
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Hello" }] },
    ];
    store.saveCurrentMessages(messages);

    const current = store.conversations().find((c) => c.id === store.currentId())!;
    expect(current.messages).toEqual(messages);
  });

  it("persists conversation to localStorage on save", () => {
    const messages = [
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Hello" }] },
    ];
    store.saveCurrentMessages(messages);

    // Should be in localStorage
    const keys = getConversationKeys();
    expect(keys.length).toBe(1);
    const stored = JSON.parse(localStorage.getItem(keys[0])!);
    expect(stored.messages).toEqual(messages);
  });

  it("removes a conversation and switches to next", () => {
    store.createNew(); // conversation 2
    const secondId = store.currentId();
    store.createNew(); // conversation 3
    const thirdId = store.currentId();

    // Switch to second and delete it
    store.switchTo(secondId);
    const result = store.removeCurrent();

    // Should have switched to either first or third
    expect(store.conversations().length).toBe(2);
    expect(store.currentId()).not.toBe(secondId);
    // localStorage should have 2 keys
    expect(countConversationKeys()).toBe(2);
  });

  it("returns messages for the current conversation", () => {
    const messages = [
      { id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "Hi" }] },
    ];
    store.saveCurrentMessages(messages);

    const retrieved = store.getCurrentMessages();
    expect(retrieved).toEqual(messages);
  });

  it("loads existing conversations from localStorage on init", () => {
    localStorage.clear();
    // Manually seed localStorage
    const id1 = crypto.randomUUID();
    const id2 = crypto.randomUUID();
    const conv1 = {
      id: id1,
      title: "Conversation 1",
      createdAt: Date.now() - 1000,
      messages: [{ id: "1", role: "user" as const, parts: [{ type: "text" as const, content: "A" }] }],
    };
    const conv2 = {
      id: id2,
      title: "Conversation 2",
      createdAt: Date.now(),
      messages: [],
    };
    localStorage.setItem(`conversation:${id1}`, JSON.stringify(conv1));
    localStorage.setItem(`conversation:${id2}`, JSON.stringify(conv2));
    localStorage.setItem("conversation:lastOpened", id2);

    createRoot((rootDispose) => {
      store = createConversationStore();
      return rootDispose;
    });

    expect(store.conversations().length).toBe(2);
    // Should restore lastOpened
    expect(store.currentId()).toBe(id2);
    // Sorted newest first
    expect(store.conversations()[0].id).toBe(id2);
  });

  it("handles deleting the last conversation gracefully", () => {
    // Should have 1 auto-created conversation
    expect(store.conversations().length).toBe(1);

    const lastId = store.currentId();
    store.removeCurrent();

    // Should auto-create a new one
    expect(store.conversations().length).toBe(1);
    expect(store.currentId()).not.toBe(lastId);
  });

  it("updates the current conversation's title", () => {
    store.updateCurrentTitle("My new title");
    const current = store.conversations().find((c) => c.id === store.currentId())!;
    expect(current.title).toBe("My new title");

    // Also persists to localStorage
    const keys = getConversationKeys();
    const stored = JSON.parse(localStorage.getItem(keys[0])!);
    expect(stored.title).toBe("My new title");
  });

  it("tolerates corrupt localStorage gracefully", () => {
    const origWarn = console.warn;
    console.warn = () => {};
    localStorage.setItem("conversation:bad", "not valid json");
    let store2: ConversationStore;
    createRoot((rootDispose) => {
      store2 = createConversationStore();
      return rootDispose;
    });
    console.warn = origWarn;
    // Should still have at least the auto-created one
    expect(store2!.conversations().length).toBeGreaterThanOrEqual(1);
  });
});
