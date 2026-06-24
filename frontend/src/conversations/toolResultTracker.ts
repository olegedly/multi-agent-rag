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
  // Lazy-init: checked on the FIRST isNew() call.  This avoids the
  // race where `loading` flips in the same batch as a tool result
  // appearing — we read the *current* loading state once at call time,
  // then cache it for the session.  Storage-loaded results correctly
  // get false; streaming results correctly get true.
  let hasLoadedSinceMount: boolean | undefined;
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
   *
   * Lazy-init: only caches `true`.  If `loading()` is false on the
   * first call, leaves `hasLoadedSinceMount` as `undefined` so the
   * next call (e.g. during streaming) can re-evaluate.
   */
  const isNew = (msgId: string, toolCallId: string): boolean => {
    if (hasLoadedSinceMount === undefined) {
      const loadingNow = loading();
      if (loadingNow) hasLoadedSinceMount = true;
    }
    if (!hasLoadedSinceMount) {
      console.log("isNew:f", msgId.slice(-6), toolCallId, "ld=", loading(), "hlsm=", hasLoadedSinceMount, "sk=", seenKeys.has(`${msgId}:${toolCallId}`));
      return false;
    }
    const key = `${msgId}:${toolCallId}`;
    if (seenKeys.has(key)) {
      console.log("isNew:s", msgId.slice(-6), toolCallId, "ld=", loading(), "hlsm=", hasLoadedSinceMount, "sk=y");
      return false;
    }
    seenKeys.add(key);
    console.log("isNew:T", msgId.slice(-6), toolCallId, "ld=", loading(), "hlsm=", hasLoadedSinceMount);
    return true;
  };

  return { isNew, nextToolCallTick };
}
