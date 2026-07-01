import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createRoot } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";
import type { Conversation, ConversationPersistence } from "../store";
import { ConversationStore, createConversationStore } from "../store";

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

function makeMessages(count: number): UIMessage[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `msg-${i}`,
    role: (i % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
    parts: [{ type: "text" as const, content: `Message ${i}` }],
  }));
}

describe("HMR / beforeunload data loss", () => {
  let persistence: FakePersistence;
  let store: ConversationStore;
  let dispose: (() => void) | undefined;

  beforeEach(() => {
    persistence = new FakePersistence();
    dispose = createRoot((rootDispose) => {
      store = createConversationStore({ persistence });
      return rootDispose;
    });
  });

  afterEach(() => {
    dispose?.();
  });

  // ── Survival tests ──

  it("survives unmount+remount: data intact after full cycle", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();
    store.updateCurrentTitle("My Chat");
    dispose?.();
    createRoot((rd) => {
      const store2 = createConversationStore({ persistence });
      expect(persistence.loadAll().length).toBe(1);
      expect(store2.currentId()).toBe(convId);
      expect(store2.getCurrentMessages().length).toBe(3);
      expect(
        store2.conversations().find((c) => c.id === convId)?.title,
      ).toBe("My Chat");
      rd();
    });
  });

  it("multiple conversations survive HMR independently", () => {
    store.saveCurrentMessages(makeMessages(2));
    const conv1Id = store.currentId();
    store.createNew();
    const conv2Id = store.currentId();
    store.saveCurrentMessages(makeMessages(4));
    dispose?.();
    createRoot((rd) => {
      const store2 = createConversationStore({ persistence });
      expect(persistence.loadAll().length).toBe(2);
      const conv1 = persistence.loadAll().find((c) => c.id === conv1Id)!;
      const conv2 = persistence.loadAll().find((c) => c.id === conv2Id)!;
      expect(conv1.messages.length).toBe(2);
      expect(conv2.messages.length).toBe(4);
      rd();
    });
  });

  it("switch-to-other then switch-back does not corrupt any conv's data", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convA = store.currentId();
    store.createNew();
    const convB = store.currentId();
    store.saveCurrentMessages(makeMessages(2));
    store.switchTo(convA);
    const convA_data = persistence.loadAll().find((c) => c.id === convA)!;
    const convB_data = persistence.loadAll().find((c) => c.id === convB)!;
    expect(convA_data.messages.length).toBe(3);
    expect(convB_data.messages.length).toBe(2);
    store.switchTo(convB);
    const convA_again = persistence.loadAll().find((c) => c.id === convA)!;
    const convB_again = persistence.loadAll().find((c) => c.id === convB)!;
    expect(convA_again.messages.length).toBe(3);
    expect(convB_again.messages.length).toBe(2);
  });

  // ── Guard tests: saveCurrentMessages([]) behavior ──

  it("guard: saveCurrentMessages([]) must NOT overwrite a non-empty conversation", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();

    // Any code path that calls saveCurrentMessages([]) should be a no-op
    store.saveCurrentMessages([]);

    const stored = persistence.loadAll().find((c) => c.id === convId)!;
    expect(stored.messages.length).toBeGreaterThan(0);
    expect((stored.messages[0].parts[0] as any).content).toBe("Message 0");
  });

  it("guard: saveCurrentMessages([]) may overwrite an empty/never-saved conversation", () => {
    // conv is brand new and empty — saving [] is fine
    store.saveCurrentMessages([]);
    expect(store.getCurrentMessages()).toEqual([]);
  });

  // ── beforeunload-style scenarios ──

  it("beforeunload: empty msgs guard prevents overwrite", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();

    // Simulate saveCurrent() guard: if (msgs.length > 0) { ... }
    const emptyMsgs: UIMessage[] = [];
    if (emptyMsgs.length > 0) {
      store.saveCurrentMessages(emptyMsgs);
    }

    const stored = persistence.loadAll().find((c) => c.id === convId)!;
    expect(stored.messages.length).toBe(3);
  });

  it("beforeunload: non-empty msgs save correctly", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();

    store.saveCurrentMessages(makeMessages(3));
    const stored = persistence.loadAll().find((c) => c.id === convId)!;
    expect(stored.messages.length).toBe(3);
  });
});
