import { createEffect, createSignal } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";

// ── Collapse memory ─────────────────────────────────────────────────────
// Module-level map that persists collapse state across <For> re-creations.
// Cleared when a new loading session starts (same time as seenKeys).

const collapseMemory = new Map<string, boolean>();

/** Mark a section as collapsed so it won't re-expand on re-creation. */
export function markCollapsed(msgId: string, toolCallId: string): void {
  collapseMemory.set(`${msgId}:${toolCallId}`, true);
}

/**
 * Check whether a section was collapsed during the current session.
 * Returns true only if markCollapsed was called this session AND
 * the memory hasn't been cleared by a new loading transition.
 */
export function isCollapsedInSession(msgId: string, toolCallId: string): boolean {
  return collapseMemory.get(`${msgId}:${toolCallId}`) ?? false;
}

/** Clear collapse memory (called when a new loading session begins). */
function clearCollapseMemory(): void {
  collapseMemory.clear();
}

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
      clearCollapseMemory();
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
