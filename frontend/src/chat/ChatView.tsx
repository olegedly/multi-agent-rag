import { Show, createEffect, createSignal } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { createToolResultTracker } from "./toolResultTracker";

interface ChatViewProps {
  messages: () => UIMessage[];
  isLoading: boolean;
  error: string | null;
  storageError: string | null;
  agentNameMap?: Record<string, string>;
  /** Set of message IDs whose TEXT_MESSAGE_END has been received. */
  endedMessageIds?: Set<string>;
  onSend: (text: string) => void;
  onStop: () => void;
  onDismissStorageError: () => void;
  /** Incrementing value that causes ChatInput to re-focus */
  focusTick?: number;
}

export function ChatView(props: ChatViewProps) {
  const tracker = createToolResultTracker(props.messages, () => props.isLoading);
  // Reactive signal for ended message IDs — synced from prop via effect.
  const [endedSet, setEndedSet] = createSignal<Set<string>>(new Set());
  createEffect(() => {
    const next = props.endedMessageIds ?? new Set<string>();
    // Avoid no-op signal updates (which can cause unnecessary re-renders).
    if (next.size !== endedSet().size || !isSubset(endedSet(), next)) {
      setEndedSet(next);
    }
  });

  function isSubset(a: Set<string>, b: Set<string>): boolean {
    for (const v of a) { if (!b.has(v)) return false; }
    return true;
  }

  // Tick when loading ends (stream complete or Stop button)
  let prevIsLoading: boolean | undefined;
  const [stopTick, setStopTick] = createSignal(0);
  createEffect(() => {
    const now = props.isLoading;
    if (prevIsLoading !== undefined && prevIsLoading && !now) {
      setStopTick((t) => t + 1);
    }
    prevIsLoading = now;
  });

  return (
    <div class="flex flex-col h-full bg-(--bg-primary)">
      <Show when={props.storageError}>
        <div class="flex items-center justify-between px-4 py-2 bg-red-900/80 text-red-100 text-sm">
          <span>{props.storageError}</span>
          <button
            onClick={props.onDismissStorageError}
            class="ml-2 p-1 hover:bg-red-800 rounded transition-colors cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
      </Show>

      <MessageList
        messages={props.messages}
        isLoading={props.isLoading}
        error={props.error}
        nextToolCallTick={tracker.nextToolCallTick() + stopTick()}
        isNewToolResult={tracker.isNew}
        agentNameMap={props.agentNameMap}
        endedMessageIds={props.endedMessageIds}
        endedSet={endedSet}
        stopTick={stopTick}
      />

      <ChatInput
        isLoading={props.isLoading}
        onSend={props.onSend}
        onStop={props.onStop}
        focusTick={props.focusTick}
      />
    </div>
  );
}
