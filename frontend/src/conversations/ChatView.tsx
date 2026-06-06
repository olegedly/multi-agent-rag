import { For, Show, createSignal, createEffect, onMount } from "solid-js";
import type { UIMessage } from "@tanstack/ai-client";

interface ChatViewProps {
  messages: () => UIMessage[];
  isLoading: boolean;
  error: string | null;
  storageError: string | null;
  onSend: (text: string) => void;
  onStop: () => void;
  onDismissStorageError: () => void;
}

function isDesktop(): boolean {
  return !("ontouchstart" in window) && window.matchMedia("(pointer: fine)").matches;
}

export function ChatView(props: ChatViewProps) {
  const [input, setInput] = createSignal("");
  let messagesEndRef: HTMLDivElement | undefined;
  let textareaRef: HTMLTextAreaElement | undefined;

  // Autofocus on app load (desktop only)
  onMount(() => {
    if (isDesktop()) {
      queueMicrotask(() => {
        textareaRef?.focus();
      });
    }
  });

  // Autofocus after LLM response finishes streaming (desktop only)
  let wasLoading = false;
  createEffect(() => {
    const loading = props.isLoading;
    if (wasLoading && !loading && isDesktop()) {
      queueMicrotask(() => {
        textareaRef?.focus();
      });
    }
    wasLoading = loading;
  });

  createEffect(() => {
    // Scroll to bottom whenever messages change
    props.messages();
    queueMicrotask(() => {
      messagesEndRef?.scrollIntoView({ behavior: "smooth" });
    });
  });

  const handleSubmit = (e: Event) => {
    e.preventDefault();
    const text = input().trim();
    if (text && !props.isLoading) {
      props.onSend(text);
      setInput("");
    }
  };

  return (
    <div class="flex flex-col h-full bg-(--bg-primary)">
      {/* Storage error banner */}
      <Show when={props.storageError}>
        <div class="flex items-center justify-between px-4 py-2 bg-red-900/80 text-red-100 text-sm">
          <span>{props.storageError}</span>
          <button
            onClick={props.onDismissStorageError}
            class="ml-2 p-1 hover:bg-red-800 rounded transition-colors cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path
                fill-rule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clip-rule="evenodd"
              />
            </svg>
          </button>
        </div>
      </Show>

      {/* Messages area */}
      <div class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
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
                <div class="text-xs font-medium mb-1 opacity-70 capitalize">
                  {msg.role}
                </div>
                <For each={msg.parts}>
                  {(part) => (
                    <>
                      {part.type === "text" && (
                        <p class="text-sm whitespace-pre-wrap">{part.content}</p>
                      )}
                    </>
                  )}
                </For>
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

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div class="border-t border-(--border) bg-(--bg-secondary) px-4 py-3">
        <form onSubmit={handleSubmit} class="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input()}
            onInput={(e) => setInput(e.currentTarget.value)}
            disabled={props.isLoading}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Type your message..."
            class="flex-1 resize-none rounded-xl px-4 py-2 text-sm bg-(--bg-chat-input) text-(--text-primary) border border-(--border) focus:outline-none focus:border-(--accent) transition-colors placeholder:text-(--text-secondary) disabled:opacity-50"
            rows={1}
          />
          <Show
            when={!props.isLoading}
            fallback={
              <button
                type="button"
                onClick={props.onStop}
                class="px-4 py-2 bg-(--danger) text-white rounded-xl text-sm hover:bg-(--danger-hover) transition-colors cursor-pointer"
              >
                Stop
              </button>
            }
          >
            <button
              type="submit"
              disabled={!input().trim()}
              class="px-4 py-2 bg-(--accent) text-white rounded-xl text-sm hover:bg-(--accent-hover) transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              Send
            </button>
          </Show>
        </form>
      </div>
    </div>
  );
}
