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
 */
export function createToolResultTracker(
  messages: () => UIMessage[],
  loading: () => boolean,
): ToolResultTracker {
  const seenKeys = new Set<string>();
  const [nextToolCallTick, setNextToolCallTick] = createSignal(0);
  let prevUnpairedCount = 0;
  let hasLoadedSinceMount: boolean | undefined;
  let wasLoading = loading();

  createEffect(() => {
    const now = loading();
    if (now && !wasLoading) {
      hasLoadedSinceMount = true;
      seenKeys.clear();
      prevUnpairedCount = 0;
    }
    wasLoading = now;

    if (!now) {
      prevUnpairedCount = 0;
      return;
    }

    const msgs = messages();

    const unpairedCount = msgs.reduce((count, msg) => {
      return (
        count +
        msg.parts.filter((p) => {
          if (p.type !== "tool-call") return false;
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

  const isNew = (msgId: string, toolCallId: string): boolean => {
    if (hasLoadedSinceMount === undefined) {
      const loadingNow = loading();
      if (loadingNow) hasLoadedSinceMount = true;
    }
    if (!hasLoadedSinceMount) return false;
    const key = `${msgId}:${toolCallId}`;
    if (seenKeys.has(key)) return false;
    seenKeys.add(key);
    return true;
  };

  return { isNew, nextToolCallTick };
}
