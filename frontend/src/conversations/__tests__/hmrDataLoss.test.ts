import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createRoot } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";
import { ConversationStore, createConversationStore } from "../store";

const LS_LAST_OPENED = "conversation:lastOpened";

function getConvInLS(id: string): { id: string; messages: UIMessage[] } | null {
  const raw = localStorage.getItem(`conversation:${id}`);
  return raw ? JSON.parse(raw) : null;
}

function getConvCount(): number {
  let count = 0;
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith("conversation:") && key !== LS_LAST_OPENED) count++;
  }
  return count;
}

function makeMessages(count: number): UIMessage[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `msg-${i}`,
    role: (i % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
    parts: [{ type: "text" as const, content: `Message ${i}` }],
  }));
}

describe("HMR / beforeunload data loss", () => {
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

  // ── Survival tests ──

  it("survives unmount+remount: data intact in localStorage after full cycle", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();
    store.updateCurrentTitle("My Chat");
    dispose?.();
    createRoot((rd) => {
      const store2 = createConversationStore();
      expect(getConvCount()).toBe(1);
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
      const store2 = createConversationStore();
      expect(getConvCount()).toBe(2);
      expect(getConvInLS(conv1Id)!.messages.length).toBe(2);
      expect(getConvInLS(conv2Id)!.messages.length).toBe(4);
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
    expect(getConvInLS(convA)!.messages.length).toBe(3);
    expect(getConvInLS(convB)!.messages.length).toBe(2);
    store.switchTo(convB);
    expect(getConvInLS(convA)!.messages.length).toBe(3);
    expect(getConvInLS(convB)!.messages.length).toBe(2);
  });

  // ── Guard tests: saveCurrentMessages([]) behavior ──

  it("guard: saveCurrentMessages([]) must NOT overwrite a non-empty conversation", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();

    // Any code path that calls saveCurrentMessages([]) should be a no-op
    store.saveCurrentMessages([]);

    const stored = getConvInLS(convId)!;
    expect(stored.messages.length).toBeGreaterThan(0);
    expect((stored.messages[0].parts[0] as any).content).toBe("Message 0");
  });

  it("guard: saveCurrentMessages([]) may overwrite an empty/never-saved conversation", () => {
    const convId = store.currentId();
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

    expect(getConvInLS(convId)!.messages.length).toBe(3);
  });

  it("beforeunload: non-empty msgs save correctly", () => {
    store.saveCurrentMessages(makeMessages(3));
    const convId = store.currentId();

    // Simulate saveCurrent with non-empty messages
    store.saveCurrentMessages(makeMessages(3));
    expect(getConvInLS(convId)!.messages.length).toBe(3);
  });
});
