import { For, Show, createEffect, createSignal } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";
import { MessagePartRenderer } from "./MessagePartRenderer";

export interface MessageListProps {
  messages: () => UIMessage[];
  isLoading: boolean;
  error: string | null;
  nextToolCallTick: number;
  isNewToolResult: (msgId: string, toolCallId: string) => boolean;
  agentNameMap?: Record<string, string>;
  /** Set of message IDs whose TEXT_MESSAGE_END has been received. */
  endedMessageIds?: Set<string>;
}

export function MessageList(props: MessageListProps) {
  let messagesEndRef: HTMLDivElement | undefined;
  let scrollContainerRef: HTMLDivElement | undefined;
  const [isUserAtBottom, setIsUserAtBottom] = createSignal(true);

  const handleScroll = () => {
    const el = scrollContainerRef;
    if (!el) return;
    // If content fits in the viewport, scrolling is a no-op.
    // Don't let it cancel future stick-to-bottom behavior once
    // content grows past the viewport.
    if (el.scrollHeight <= el.clientHeight) return;
    const threshold = 100;
    setIsUserAtBottom(
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold,
    );
  };

  // Re-engage stick-to-bottom whenever a new stream begins.
  // Without this, a cancelled session (user scrolled up) would stay
  // cancelled across queries.
  createEffect(() => {
    if (props.isLoading) {
      setIsUserAtBottom(true);
    }
  });

  // Auto-scroll when content grows. Dependencies:
  // - messages(): core content changes
  // - nextToolCallTick: tool result arrivals/collapses (even if messages()
  //   doesn't structurally dirty the signal Solid tracks)
  // - isLoading: pagination boundary for large responses
  createEffect(() => {
    void props.messages();
    void props.nextToolCallTick;
    void props.isLoading;
    if (isUserAtBottom()) {
      // Use requestAnimationFrame so the scroll targets the post-layout
      // position, not whatever the DOM looked like mid-microtask.
      requestAnimationFrame(() => {
        messagesEndRef?.scrollIntoView({ block: "end" });
      });
    }
  });

  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      class="flex-1 overflow-y-auto px-4 py-4 space-y-4"
    >
      <For each={props.messages()}>
        {(msg) => (
          <div
            class={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              class={`max-w-[80%] rounded-2xl px-4 py-2 ${
                msg.role === "user"
                  ? "bg-(--bg-user-bubble) text-(--text-user-bubble) rounded-br-md"
                  : "bg-(--bg-assistant-bubble) text-(--text-assistant-bubble) border border-(--border) rounded-bl-md"
              }`}
            >
              <MessagePartRenderer
                msg={msg}
                isLoading={props.isLoading}
                nextToolCallTick={props.nextToolCallTick}
                isNewToolResult={props.isNewToolResult}
                agentNameMap={props.agentNameMap}

                endedMessageIds={props.endedMessageIds}
              />
            </div>
          </div>
        )}
      </For>

      {/* Error message */}
      <Show when={props.error}>
        <div class="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg text-sm">
          {props.error}
        </div>
      </Show>

      {/* Typing indicator — shows during streaming regardless of
          last message role (cross-agent handoffs keep it visible). */}
      <Show
        when={
          props.isLoading &&
          props.messages().length > 0
        }
      >
        <div class="flex justify-start">
          <div class="max-w-[80%] rounded-2xl px-4 py-3 bg-(--bg-assistant-bubble) border border-(--border) rounded-bl-md">
            <div class="ellipsis-indicator text-(--text-secondary)">
              <span class="dot">.</span>
              <span class="dot">.</span>
              <span class="dot">.</span>
            </div>
          </div>
        </div>
      </Show>

      <div ref={messagesEndRef} />
    </div>
  );
}
