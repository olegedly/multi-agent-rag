import { createEffect, createSignal } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";

export interface ToolResultTracker {
  /** Whether a tool result with these ids is new (first seen during loading) */
  isNew: (msgId: string, toolCallId: string) => boolean;
  /** Signal that ticks when a new unpaired tool-call appears during loading */
  nextToolCallTick: () => number;
}

/**
 * Creates a reactive tracker for tool result "newness" and auto-collapse ticks.
 *
 * - When `loading` is true, the first call to `isNew` for each (msgId, toolCallId)
 *   returns true and permanently records it as "seen".
 * - When `loading` is false, `isNew` always returns false.
 * - `nextToolCallTick()` increments each time a tool-call without a matching result
 *   appears in `messages` while loading.
 */
export function createToolResultTracker(
  messages: () => UIMessage[],
  loading: () => boolean,
): ToolResultTracker {
  const seenKeys = new Set<string>();
  const [nextToolCallTick, setNextToolCallTick] = createSignal(0);
  let prevUnpairedCount = 0;

  const isNew = (msgId: string, toolCallId: string): boolean => {
    if (!loading()) return false;
    const key = `${msgId}:${toolCallId}`;
    if (seenKeys.has(key)) return false;
    seenKeys.add(key);
    return true;
  };

  // Track unpaired tool-calls using a signal, not mutable state
  // load `loading()` inside the effect so it reruns when loading toggles
  createEffect(() => {
    if (!loading()) return;

    // We need to eagerly load messages() inside the effect so tracking
    // participates in the reactive graph
    const msgs = messages();

    const seenAtThisLoad = new Set<string>();
    for (const msg of msgs) {
      for (const part of msg.parts) {
        if (part.type === "tool-call") {
          seenAtThisLoad.add(`${msg.id}:${part.id}`);
        }
      }
    }

    const unpairedCount = msgs.reduce((count, msg) => {
      return (
        count +
        msg.parts.filter((p) => {
          if (p.type !== "tool-call") return false;
          // Check if this call has a result in the same message
          const hasResult = msg.parts.some(
            (rp) => rp.type === "tool-result" && rp.toolCallId === p.id,
          );
          return !hasResult;
        }).length
      );
    }, 0);

    if (unpairedCount > prevUnpairedCount) {
      setNextToolCallTick((t) => t + 1);
    }
    prevUnpairedCount = unpairedCount;
  });

  // When loading transitions to false (stream ended — either by normal
  // completion or by the Stop button), increment the tick to collapse
  // all expanded result blocks. This ensures that when the user clicks
  // Stop, any tool result that was expanded during streaming gets
  // collapsed immediately.
  let prevLoading: boolean | undefined;
  createEffect(() => {
    const nowLoading = loading();
    if (prevLoading !== undefined && prevLoading && !nowLoading) {
      // Loading just ended — tick once to collapse
      setNextToolCallTick((t) => t + 1);
    }
    prevLoading = nowLoading;
    if (!nowLoading) {
      prevUnpairedCount = 0;
    }
  });

  return { isNew, nextToolCallTick };
}
