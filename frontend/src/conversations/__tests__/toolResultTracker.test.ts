import { describe, it, expect } from "vitest";
import { createRoot, createSignal } from "solid-js";
import { createToolResultTracker } from "../toolResultTracker";
import type { UIMessage } from "@tanstack/ai-client";

function toolCallMsg(id: string): UIMessage {
  return {
    id: `${id}-msg`,
    role: "assistant",
    parts: [
      {
        type: "tool-call" as const,
        id: id,
        name: "test_tool",
        arguments: "{}",
        state: "complete" as const,
      },
    ],
  };
}

function pairedMsg(id: string): UIMessage {
  return {
    id: `${id}-msg`,
    role: "assistant",
    parts: [
      {
        type: "tool-call" as const,
        id: id,
        name: "test_tool",
        arguments: "{}",
        state: "complete" as const,
      },
      {
        type: "tool-result" as const,
        toolCallId: id,
        content: "result",
        state: "complete" as const,
      },
    ],
  };
}

/** Helper: flush microtasks so Solid effects run. */
function tick(): Promise<void> {
  return new Promise((resolve) => queueMicrotask(resolve));
}

describe("createToolResultTracker", () => {
  it("returns isNew=true for unseen keys, false for seen", () => {
    createRoot(() => {
      const [msgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => true);

      expect(tracker.isNew("msg-1", "call-1")).toBe(true);
      expect(tracker.isNew("msg-1", "call-1")).toBe(false);
      expect(tracker.isNew("msg-1", "call-2")).toBe(true);
    });
  });

  it("returns false for isNew when loading is false (skip tracking)", () => {
    createRoot(() => {
      const [msgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => false);

      expect(tracker.isNew("msg-1", "call-1")).toBe(false);
      expect(tracker.isNew("msg-1", "call-1")).toBe(false);
    });
  });

  it("tracks isNew when loading is true", () => {
    createRoot(() => {
      const [msgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => true);

      expect(tracker.isNew("msg-1", "call-1")).toBe(true);
      expect(tracker.isNew("msg-1", "call-1")).toBe(false);
    });
  });

  it("increments nextToolCallTick when a new unpaired tool-call appears during loading", async () => {
    await createRoot(async () => {
      const [msgs, setMsgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => true);
      const initialTick = tracker.nextToolCallTick();

      // Add a paired call+result — no new unpaired call
      setMsgs([pairedMsg("call-1")]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(initialTick);

      // Add an unpaired tool-call
      setMsgs([pairedMsg("call-1"), toolCallMsg("call-2")]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(initialTick + 1);
    });
  });

  it("does not increment tick when all calls are paired", async () => {
    await createRoot(async () => {
      const [msgs, setMsgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => true);
      const initialTick = tracker.nextToolCallTick();

      setMsgs([pairedMsg("call-1")]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(initialTick);

      // Add another paired call
      setMsgs([pairedMsg("call-1"), pairedMsg("call-2")]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(initialTick);
    });
  });

  it("does not double-tick for the same unpaired call on re-render", async () => {
    await createRoot(async () => {
      const [msgs, setMsgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => true);

      setMsgs([toolCallMsg("call-1")]);
      await tick();
      const afterFirst = tracker.nextToolCallTick();

      // Trigger a re-render with same data — should NOT tick again
      setMsgs([toolCallMsg("call-1")]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(afterFirst);
    });
  });

  it("ticks once per new unpaired call even when multiple appear at once", async () => {
    await createRoot(async () => {
      const [msgs, setMsgs] = createSignal<UIMessage[]>([]);
      const tracker = createToolResultTracker(msgs, () => true);
      const initialTick = tracker.nextToolCallTick();

      // Two new unpaired calls at once — should tick once
      setMsgs([toolCallMsg("call-1"), toolCallMsg("call-2")]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(initialTick + 1);

      // Add a third — tick again
      setMsgs([
        toolCallMsg("call-1"),
        toolCallMsg("call-2"),
        toolCallMsg("call-3"),
      ]);
      await tick();
      expect(tracker.nextToolCallTick()).toBe(initialTick + 2);
    });
  });
});
