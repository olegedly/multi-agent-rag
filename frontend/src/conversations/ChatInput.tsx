import {
  createSignal,
  createEffect,
  onMount,
  onCleanup,
  Show,
  type JSX,
} from "solid-js";

export interface ChatInputProps {
  isLoading: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  /** Incrementing value that triggers autofocus (e.g. after '+ New') */
  focusTick?: number;
}

function isDesktop(): boolean {
  return (
    !("ontouchstart" in window) && window.matchMedia("(pointer: fine)").matches
  );
}

export function ChatInput(props: ChatInputProps) {
  const [input, setInput] = createSignal("");
  let textareaRef: HTMLTextAreaElement | undefined;

  // Autofocus on mount (desktop only)
  onMount(() => {
    if (isDesktop()) {
      queueMicrotask(() => {
        textareaRef?.focus();
      });
    }
  });

  // Re-focus when focusTick changes (e.g. '+ New' button clicked)
  createEffect(() => {
    // Access focusTick to create reactive dependency
    const tick = props.focusTick;
    if (tick !== undefined && tick > 0 && isDesktop()) {
      queueMicrotask(() => {
        textareaRef?.focus();
      });
    }
  });

  // Autofocus after LLM response finishes streaming (desktop only)
  let wasLoadingForFocus = false;
  createEffect(() => {
    const loading = props.isLoading;
    if (wasLoadingForFocus && !loading && isDesktop()) {
      queueMicrotask(() => {
        textareaRef?.focus();
      });
    }
    wasLoadingForFocus = loading;
  });

  // Auto-grow textarea height
  createEffect(() => {
    input();
    const ta = textareaRef;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
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
          class="flex-1 resize-none rounded-xl px-4 py-2 text-sm bg-(--bg-chat-input) text-(--text-primary) border border-(--border) focus:outline-none focus:border-(--accent) transition-colors placeholder:text-(--text-secondary) disabled:opacity-50 max-h-45 overflow-y-hidden"
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
  );
}
