import { Show, createEffect, createSignal, createContext, useContext } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { createToolResultTracker } from "./toolResultTracker";

/**
 * Reactive signal that ticks (increments) every time `isLoading`
 * transitions from true to false.  Consumed by CollapsibleSection
 * so that thinking blocks and tool-result panels collapse when
 * streaming stops — even across <Index>/<For> boundaries.
 */
const StopCollapseContext = createContext<() => number>(() => 0);
export { StopCollapseContext };

interface ChatViewProps {
  messages: () => UIMessage[];
  isLoading: boolean;
  error: string | null;
  storageError: string | null;
  agentNameMap?: Record<string, string>;
  onSend: (text: string) => void;
  onStop: () => void;
  onDismissStorageError: () => void;
  /** Incrementing value that causes ChatInput to re-focus */
  focusTick?: number;
}

export function ChatView(props: ChatViewProps) {
  const tracker = createToolResultTracker(props.messages, () => props.isLoading);

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
    <StopCollapseContext.Provider value={stopTick}>
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
        />

        <ChatInput
          isLoading={props.isLoading}
          onSend={props.onSend}
          onStop={props.onStop}
          focusTick={props.focusTick}
        />
      </div>
    </StopCollapseContext.Provider>
  );
}
