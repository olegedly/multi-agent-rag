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
 * - `isNew` returns true the first time each (msgId, toolCallId) is seen
 *   during a loading session.  Unlike the old implementation it does NOT
 *   gate on `loading()` at call time — that caused a race where tool
 *   results appearing in the same reactive batch as `isLoading=false`
 *   would skip the "new" flag and start collapsed.
 *
 * - A "loading session" begins when `loading` transitions from false to
 *   true.  `seenKeys` is cleared at the start of each session so that
 *   only keys encountered during the *current* streaming run are tracked.
 *
 * - `nextToolCallTick()` increments each time a tool-call without a
 *   matching result appears in `messages` while loading.
 */
export function createToolResultTracker(
  messages: () => UIMessage[],
  loading: () => boolean,
): ToolResultTracker {
  const seenKeys = new Set<string>();
  const [nextToolCallTick, setNextToolCallTick] = createSignal(0);
  let prevUnpairedCount = 0;
  // Start as true if already loading at mount, so synchronous
  // isNew calls (before the effect fires) work correctly.
  let hasLoadedSinceMount = loading();
  let wasLoading = loading();

  // Reset seen keys at the start of each loading session so that
  // previously-seen results from an older stream don't block new results.
  // Track `hasLoadedSinceMount` so storage-loaded results (no loading
  // session ever) are correctly reported as "not new".
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

    // Eagerly read messages() so tracking participates in the reactive graph
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

  /**
   * Returns true if (msgId, toolCallId) has never been seen during the
   * current loading session.  Does NOT check `loading()` at call time —
   * that check is replaced by the `hasLoadedSinceMount` flag which
   * persists through the entire batch.  Storage-loaded results (no
   * loading session) correctly return false.
   */
  const isNew = (msgId: string, toolCallId: string): boolean => {
    if (!hasLoadedSinceMount) return false;
    const key = `${msgId}:${toolCallId}`;
    if (seenKeys.has(key)) return false;
    seenKeys.add(key);
    return true;
  };

  return { isNew, nextToolCallTick };
}
