import {
  For,
  Show,
  on,
  createSignal,
  createEffect,
  onMount,
  onCleanup,
} from "solid-js";
import { SolidMarkdown } from "solid-markdown";
import remarkGfm from "remark-gfm";
import type {
  UIMessage,
  MessagePart,
  TextPart,
  ToolCallPart,
  ToolResultPart,
  ThinkingPart,
} from "@tanstack/ai-client";

interface ChatViewProps {
  messages: () => UIMessage[];
  isLoading: boolean;
  error: string | null;
  storageError: string | null;
  onSend: (text: string) => void;
  onStop: () => void;
  onDismissStorageError: () => void;
}

// ── Part grouping — pair each tool-call with its matching result ────────

type SoloItem = { type: "solo"; part: MessagePart };
type PairItem = {
  type: "pair";
  toolCall: ToolCallPart;
  toolResult: ToolResultPart | null;
};
type GroupItem = SoloItem | PairItem;

function groupParts(parts: MessagePart[]): GroupItem[] {
  const result: GroupItem[] = [];
  let i = 0;
  while (i < parts.length) {
    const part = parts[i];
    if (part.type !== "tool-call") {
      result.push({ type: "solo", part });
      i++;
      continue;
    }

    // Look ahead for a tool-result with matching toolCallId
    const next = parts[i + 1];
    if (
      next &&
      next.type === "tool-result" &&
      next.toolCallId === part.id
    ) {
      result.push({ type: "pair", toolCall: part, toolResult: next });
      i += 2;
    } else {
      result.push({ type: "pair", toolCall: part, toolResult: null });
      i++;
    }
  }
  return result;
}

function isDesktop(): boolean {
  return (
    !("ontouchstart" in window) && window.matchMedia("(pointer: fine)").matches
  );
}

export function ChatView(props: ChatViewProps) {
  const [input, setInput] = createSignal("");
  let messagesEndRef: HTMLDivElement | undefined;
  let scrollContainerRef: HTMLDivElement | undefined;
  let textareaRef: HTMLTextAreaElement | undefined;
  let isUserAtBottom = true;

  // Track which tool result parts are "new" (appeared during current load)
  let seenToolPartKeys = new Set<string>();
  let wasLoadingForKeys = false;

  // Signal that ticks when a new tool-call appears during loading.
  // ToolResultPartRenderers watch this to collapse when the next call starts.
  const [nextToolCallTick, setNextToolCallTick] = createSignal(0);

  let prevToolCallCount = 0;
  createEffect(() => {
    if (!props.isLoading) return;
    let count = 0;
    for (const msg of props.messages()) {
      for (const part of msg.parts) {
        if (part.type === "tool-call") count++;
      }
    }
    if (count > prevToolCallCount) {
      setNextToolCallTick((t) => t + 1);
    }
    prevToolCallCount = count;
  });

  const isNewToolResult = (msgId: string, toolCallId: string): boolean => {
    if (props.isLoading) {
      return !seenToolPartKeys.has(`${msgId}:${toolCallId}`);
    }
    return false;
  };

  // Snapshot current tool-result keys on mount and at each loading→start
  // transition, so previously-seen results don't get the auto-collapse.
  let didInitialSnapshot = false;
  createEffect(() => {
    const loading = props.isLoading;
    if (!didInitialSnapshot) {
      didInitialSnapshot = true;
    } else if (wasLoadingForKeys === loading) {
      return;
    }
    wasLoadingForKeys = loading;

    const keys = new Set<string>();
    for (const msg of props.messages()) {
      for (const part of msg.parts) {
        if (part.type === "tool-result") {
          keys.add(`${msg.id}:${part.toolCallId}`);
        }
      }
    }
    seenToolPartKeys = keys;
  });

  const handleScroll = () => {
    const el = scrollContainerRef;
    if (!el) return;
    const threshold = 100;
    isUserAtBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  };

  // Autofocus on app load (desktop only)
  onMount(() => {
    if (isDesktop()) {
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

  // Auto-grow textarea height as content grows, capped by max-h with scroll
  createEffect(() => {
    input(); // react to input changes
    const ta = textareaRef;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
  });

  createEffect(() => {
    // Only auto-scroll if the user hasn't scrolled up.
    // Uses instant scroll (not smooth) to avoid intermediate scroll
    // events that can conflict with the user's scroll position.
    props.messages();
    if (isUserAtBottom) {
      queueMicrotask(() => {
        messagesEndRef?.scrollIntoView();
      });
    }
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
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
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
                <div class="text-xs font-medium mb-1 opacity-70 capitalize">
                  {msg.role}
                </div>
                <For each={groupParts(msg.parts)}>
                  {(item) =>
                    item.type === "pair" ? (
                      <ToolCallPairRenderer
                        toolCall={item.toolCall}
                        toolResult={item.toolResult}
                        msgId={msg.id}
                        isNewToolResult={
                          item.toolResult
                            ? isNewToolResult(msg.id, item.toolResult.toolCallId)
                            : false
                        }
                        nextToolCallTick={nextToolCallTick()}
                      />
                    ) : (
                      <PartRenderer
                        part={item.part}
                        msgId={msg.id}
                        isNewToolResult={false}
                      />
                    )
                  }
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

        {/* Typing indicator — shown when loading but no assistant message yet */}
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
    </div>
  );
}

// ── Part renderer (for solo parts) ──────────────────────────────────────

function PartRenderer(props: {
  part: MessagePart;
  msgId: string;
  isNewToolResult: boolean;
}) {
  return (
    <>
      {props.part.type === "text" && <TextPartRenderer part={props.part} />}
      {props.part.type === "thinking" && (
        <ThinkingPartRenderer part={props.part} />
      )}
      {props.part.type === "tool-result" && (
        <ToolResultPartRenderer
          part={props.part}
          isNew={props.isNewToolResult}
        />
      )}
    </>
  );
}

// ── Tool call + result pair (rendered as one visual block) ──────────────

function ToolCallPairRenderer(props: {
  toolCall: ToolCallPart;
  toolResult: ToolResultPart | null;
  msgId: string;
  isNewToolResult: boolean;
  nextToolCallTick: number;
}) {
  return (
    <div class="mt-2 mb-2">
      <ToolCallPartRenderer part={props.toolCall} />
      <Show when={props.toolResult}>
        {(tr) => (
          <ToolResultPartRenderer
            part={tr()}
            isNew={props.isNewToolResult}
            nextToolCallTick={props.nextToolCallTick}
          />
        )}
      </Show>
    </div>
  );
}

// ── Text part ────────────────────────────────────────────────────────────

function TextPartRenderer(props: { part: TextPart }) {
  return (
    <div class="prose prose-sm max-w-none">
      <SolidMarkdown
        children={props.part.content}
        remarkPlugins={[remarkGfm]}
      />
    </div>
  );
}

// ── Thinking/reasoning part (collapsible) ─────────────────────────────────

function ThinkingPartRenderer(props: { part: ThinkingPart }) {
  const [expanded, setExpanded] = createSignal(true);

  return (
    <div class="mb-2">
      <button
        onClick={() => setExpanded(!expanded())}
        class="flex items-center gap-1.5 text-xs font-medium text-(--text-secondary) hover:text-(--accent) transition-colors cursor-pointer"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class={`h-3.5 w-3.5 transition-transform ${expanded() ? "rotate-90" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fill-rule="evenodd"
            d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
            clip-rule="evenodd"
          />
        </svg>
        <span>Reasoned</span>
      </button>
      <Show when={expanded()}>
        <div class="mt-1 p-2 rounded-lg bg-(--bg-primary) border border-(--border) text-xs text-(--text-secondary) italic whitespace-pre-wrap leading-relaxed">
          {props.part.content}
        </div>
      </Show>
    </div>
  );
}

// ── Tool call part ────────────────────────────────────────────────────────

const TOOL_CALL_LABELS: Record<string, string> = {
  "awaiting-input": "awaiting input",
  "input-streaming": "streaming",
  "input-complete": "processing",
  "approval-requested": "needs approval",
  "approval-responded": "approved",
  complete: "done",
};

function ToolCallPartRenderer(props: { part: ToolCallPart }) {
  return (
    <div class="flex items-start gap-2 text-xs">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="h-3.5 w-3.5 mt-0.5 shrink-0 text-(--accent)"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path
          fill-rule="evenodd"
          d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
          clip-rule="evenodd"
        />
      </svg>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5">
          <code class="font-mono font-medium text-(--text-primary)">
            {props.part.name}
          </code>
          <span
            class="px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{
              "background-color":
                props.part.state === "complete"
                  ? "var(--badge-done-bg)"
                  : props.part.state === "input-streaming"
                    ? "var(--badge-streaming-bg)"
                    : props.part.state === "awaiting-input"
                      ? "var(--badge-waiting-bg)"
                      : "var(--badge-other-bg)",
              color:
                props.part.state === "complete"
                  ? "var(--badge-done-text)"
                  : props.part.state === "input-streaming"
                    ? "var(--badge-streaming-text)"
                    : props.part.state === "awaiting-input"
                      ? "var(--badge-waiting-text)"
                      : "var(--badge-other-text)",
            }}
          >
            {TOOL_CALL_LABELS[props.part.state] ?? props.part.state}
          </span>
        </div>
        <div class="mt-0.5 text-(--text-secondary) font-mono text-[11px] whitespace-pre-wrap max-h-24 overflow-y-auto">
          {formatToolResult(props.part.arguments)}
        </div>
      </div>
    </div>
  );
}

// ── YAML formatter for tool results ───────────────────────────────────────

function formatToolResult(content: string | Array<any>): string {
  if (typeof content !== "string") {
    return JSON.stringify(content, null, 2);
  }

  try {
    const parsed = JSON.parse(content);
    return jsonToYaml(parsed);
  } catch {
    return content;
  }
}

function jsonToYaml(value: unknown, indent: number = 0): string {
  const pad = "  ".repeat(indent);

  if (value === null || value === undefined) return "null";

  if (typeof value === "string") {
    const clean = value.replace(/\\n/g, "\n");
    if (clean.includes("\n")) {
      const lines = clean.split("\n");
      return `|\n${pad}  ${lines.join(`\n${pad}  `)}`;
    }
    if (
      /^[a-zA-Z0-9_/.\- ]+$/.test(clean) &&
      !/^[\-:?\[\]{}#,|>!@&*'"%`]/.test(clean)
    ) {
      return clean;
    }
    return `"${clean}"`;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    const items = value.map((item) => {
      if (typeof item === "object" && item !== null) {
        const sub = jsonToYaml(item, indent + 1);
        const lines = sub.split("\n");
        return (
          `${pad}- ${lines[0]}` +
          lines
            .slice(1)
            .map((l) => `\n${pad}  ${l}`)
            .join("")
        );
      }
      return `${pad}- ${jsonToYaml(item, indent + 1)}`;
    });
    return items.join("\n");
  }

  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return "{}";
  return entries
    .map(([key, val]) => {
      const keyStr = /^[a-zA-Z_]\w*$/.test(key) ? key : JSON.stringify(key);
      const rendered = jsonToYaml(val, indent + 1);
      if (
        val === null ||
        typeof val === "string" ||
        typeof val === "number" ||
        typeof val === "boolean"
      ) {
        return `${pad}${keyStr}: ${rendered}`;
      }
      return `${pad}${keyStr}:\n${rendered}`;
    })
    .join("\n");
}

// ── Tool result part (collapsible with auto-collapse) ────────────────────

function ToolResultPartRenderer(props: {
  part: ToolResultPart;
  isNew: boolean;
  nextToolCallTick?: number;
}) {
  const [expanded, setExpanded] = createSignal(props.isNew);
  let userInteracted = false;
  let timerRef: number | undefined;

  onMount(() => {
    if (!props.isNew) return;
    timerRef = window.setTimeout(() => {
      if (!userInteracted) {
        setExpanded(false);
      }
    }, 1500);
  });

  onCleanup(() => {
    if (timerRef !== undefined) clearTimeout(timerRef);
  });

  // When the next tool call starts, collapse immediately (faster than 1.5s).
  // Deferred so it doesn't fire on mount — only when the tick actually changes.
  createEffect(
    on(
      () => props.nextToolCallTick,
      () => {
        if (!userInteracted && expanded()) {
          if (timerRef !== undefined) {
            clearTimeout(timerRef);
            timerRef = undefined;
          }
          setExpanded(false);
        }
      },
      { defer: true },
    ),
  );

  const toggle = () => {
    if (!userInteracted) {
      userInteracted = true;
      if (timerRef !== undefined) {
        clearTimeout(timerRef);
        timerRef = undefined;
      }
    }
    setExpanded(!expanded());
  };

  return (
    <div class="mb-2">
      <button
        onClick={toggle}
        class="flex items-center gap-1.5 text-xs font-medium text-(--text-secondary) hover:text-(--accent) transition-colors cursor-pointer w-full text-left"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-3.5 w-3.5 shrink-0 text-green-400"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fill-rule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clip-rule="evenodd"
          />
        </svg>
        <span class="flex items-center gap-1">
          Result
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class={`h-3 w-3 mt-[2.6px] transition-transform duration-200 ${expanded() ? "rotate-90" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fill-rule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </span>
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        classList={{
          "max-h-0 opacity-0": !expanded(),
          "max-h-80 opacity-100": expanded(),
        }}
      >
        <div class="mt-1 pl-5">
          <div class="text-xs text-(--text-secondary) font-mono whitespace-pre-wrap leading-relaxed max-h-75 overflow-y-auto">
            {formatToolResult(props.part.content)}
          </div>
        </div>
      </div>
    </div>
  );
}
