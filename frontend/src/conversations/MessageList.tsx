import { For, Show, createEffect, onCleanup } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";
import { MessagePartRenderer } from "./MessagePartRenderer";

export interface MessageListProps {
  messages: () => UIMessage[];
  isLoading: boolean;
  error: string | null;
  nextToolCallTick: number;
  isNewToolResult: (msgId: string, toolCallId: string) => boolean;
}

export function MessageList(props: MessageListProps) {
  let messagesEndRef: HTMLDivElement | undefined;
  let scrollContainerRef: HTMLDivElement | undefined;
  let isUserAtBottom = true;

  const handleScroll = () => {
    const el = scrollContainerRef;
    if (!el) return;
    // If content fits in the viewport, scrolling is a no-op.
    // Don't let it cancel future stick-to-bottom behavior once
    // content grows past the viewport.
    if (el.scrollHeight <= el.clientHeight) return;
    const threshold = 100;
    isUserAtBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  };

  createEffect(() => {
    props.messages();
    if (isUserAtBottom) {
      queueMicrotask(() => {
        messagesEndRef?.scrollIntoView();
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

      {/* Typing indicator */}
      <Show
        when={
          props.isLoading &&
          props.messages().length > 0 &&
          props.messages()[props.messages().length - 1].role === "user"
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
