import { For, Index, Show, useContext, createEffect, createSignal } from "solid-js";
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
import { formatToolResult } from "./formatToolResult";
import { CollapsibleSection } from "./CollapsibleSection";
import { groupParts } from "./groupParts";
import type { GroupItem, PairItem } from "./groupParts";

// ── Agent name emoji map ──────────────────────────────────────────

const AGENT_NAME_EMOJI: Record<string, string> = {
  Researcher: "🔍",
  Critic: "⚖️",
  Synthesizer: "📝",
};

// ── Props ───────────────────────────────────────────────────────────────

export interface MessagePartRendererProps {
  msg: UIMessage;
  isLoading: boolean;
  nextToolCallTick: number;
  /** Optional set of (msgId, toolCallId) keys that appeared during loading */
  isNewToolResult?: (msgId: string, toolCallId: string) => boolean;
  /** Map of messageId → agent name for assistant messages */
  agentNameMap?: Record<string, string>;
  /** Set of message IDs whose TEXT_MESSAGE_END has been received. */
  endedMessageIds?: Set<string>;
}

// ── Main renderer ────────────────────────────────────────────────────────

export function MessagePartRenderer(props: MessagePartRendererProps) {
  const { msg, isLoading, nextToolCallTick, isNewToolResult, agentNameMap } =
    props;
  const endedMessageIds = (
    useContext(MessageEndedContext) ?? (() => new Set<string>())
  )();
  const agentName =
    msg.role === "assistant" ? agentNameMap?.[msg.id] : undefined;

  return (
    <>
      <div class="text-xs font-medium mb-1 capitalize">
        {agentName
          ? `${AGENT_NAME_EMOJI[agentName] ?? ""} ${agentName}`
          : msg.role}
      </div>
      {/* Use Index (position-based reconciliation) so that existing
          ToolResultPartRenderer instances survive when new parts
          are appended to the message during streaming. */}
      <Index each={groupParts(msg.parts)}>
        {(getItem) => {
          const item: GroupItem = getItem();
          if (item.type === "pair") {
            const paired = item as PairItem;
            return (
              <ToolCallPairRenderer
                toolCall={paired.toolCall}
                toolResult={paired.toolResult}
                msgId={msg.id}
                isNewToolResult={
                  paired.toolResult
                    ? (isNewToolResult?.(
                        msg.id,
                        paired.toolResult.toolCallId,
                      ) ?? false)
                    : false
                }
                nextToolCallTick={nextToolCallTick}
                isLoading={isLoading}
              />
            );
          }
          return (
            <PartRenderer
              part={item.part}
              msgId={msg.id}
              isNewToolResult={false}
              isLoading={isLoading}
              endedMessageIds={endedMessageIds}
              nextToolCallTick={nextToolCallTick}
            />
          );
        }}
      </Index>
    </>
  );
}

// ── Internal sub-renderers (private to this module) ──────────────────────

function PartRenderer(props: {
  part: MessagePart;
  msgId: string;
  isNewToolResult: boolean;
  isLoading: boolean;
  nextToolCallTick: number;
  endedMessageIds?: Set<string>;
}) {
  return (
    <>
      {props.part.type === "text" && <TextPartRenderer part={props.part} />}
      {props.part.type === "thinking" && (
        <ThinkingPartRenderer
          part={props.part}
          isLoading={props.isLoading}
          nextToolCallTick={props.nextToolCallTick}
          msgId={props.msgId}
        />
      )}
      {props.part.type === "tool-result" && (
        <ToolResultPartRenderer
          part={props.part}
          isNew={props.isNewToolResult}
          nextToolCallTick={props.nextToolCallTick}
          isLoading={props.isLoading}
        />
      )}
    </>
  );
}

const TOOL_CALL_LABELS: Record<string, string> = {
  "awaiting-input": "awaiting input",
  "input-streaming": "streaming",
  "input-complete": "processing",
  "approval-requested": "needs approval",
  "approval-responded": "approved",
  complete: "done",
};

function ToolCallPairRenderer(props: {
  toolCall: ToolCallPart;
  toolResult: ToolResultPart | null;
  msgId: string;
  isLoading: boolean;
  isNewToolResult: boolean;
  nextToolCallTick: number;
}) {
  return (
    <div class="mt-2.5">
      <ToolCallRenderer part={props.toolCall} />
      <Show when={props.toolResult}>
        {(tr) => (
          <ToolResultPartRenderer
            part={tr()}
            isNew={props.isNewToolResult}
            isLoading={props.isLoading}
            nextToolCallTick={props.nextToolCallTick}
          />
        )}
      </Show>
    </div>
  );
}

function TextPartRenderer(props: { part: TextPart }) {
  return (
    <div class="mt-3">
      <div class="prose prose-sm max-w-none">
        <SolidMarkdown
          children={props.part.content}
          remarkPlugins={[remarkGfm]}
        />
      </div>
    </div>
  );
}
import { MessageEndedContext } from "./ChatView";
function ThinkingPartRenderer(props: {
  part: ThinkingPart;
  isLoading: boolean;
  nextToolCallTick: number;
  msgId: string;
}) {
  const endedSet = (
    useContext(MessageEndedContext) ?? (() => new Set<string>())
  )();
  // Start expanded during active streaming.
  // Stay open through tool-call interleaving — collapse only when the
  // entire stream stops (handled by StopCollapseContext in CollapsibleSection).
  // When loaded from storage (isLoading=false), start collapsed.

  // ── Stick-to-bottom scrolling ──────────────────────────────────────
  let scrollRef: HTMLDivElement | undefined;
  const [isUserAtBottom, setIsUserAtBottom] = createSignal(true);

  const handleScroll = () => {
    const el = scrollRef;
    if (!el) return;
    if (el.scrollHeight <= el.clientHeight) return;
    const threshold = 40;
    setIsUserAtBottom(
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold,
    );
  };

  // Re-engage stick-to-bottom when streaming starts.
  createEffect(() => {
    if (props.isLoading) {
      setIsUserAtBottom(true);
    }
  });

  // Auto-scroll when thinking content grows during streaming.
  // Uses scrollTop directly instead of scrollIntoView so it always
  // targets the thinking container specifically — scrollIntoView can
  // bubble up to the chat scroll wrapper when content hasn't yet
  // overflowed (no scrollbar means no scrolling box in CSS).
  createEffect(() => {
    void props.part.content;
    if (isUserAtBottom()) {
      requestAnimationFrame(() => {
        if (scrollRef) scrollRef.scrollTop = scrollRef.scrollHeight;
      });
    }
  });

  return (
    <div class="mt-4">
      <CollapsibleSection
        label="Reasoned"
        // Collapse when any agent finishes (endedSet grows per TEXT_MESSAGE_END).
        // Uses collapseOnTick (tied to endedSet.size) so it works across
        // <For>/<Index> boundaries, plus expanded as a safety net.
        expanded={props.isLoading && !endedSet.has(props.msgId)}
        collapseOnTick={endedSet.size}
        leadingIcon={
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-3.5 w-3.5 shrink-0 text-yellow-200"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fill-rule="evenodd"
              d="M5 2a1 1 0 011 1v1h1a1 1 0 010 2H6v1a1 1 0 01-2 0V6H3a1 1 0 010-2h1V3a1 1 0 011-1zm0 10a1 1 0 011 1v1h1a1 1 0 110 2H6v1a1 1 0 01-2 0v-1H3a1 1 0 110-2h1v-1a1 1 0 011-1zM12 2a1 1 0 01.967.744L14.146 7.2 17.5 9.134a1 1 0 010 1.732l-3.354 1.935-1.18 4.455a1 1 0 01-1.933 0L9.854 12.8 6.5 10.866a1 1 0 010-1.732l3.354-1.935 1.18-4.455A1 1 0 0112 2z"
              clip-rule="evenodd"
            />
          </svg>
        }
      >
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          class="mt-1 p-2 rounded-lg bg-(--bg-primary) border border-(--border) text-xs text-(--text-secondary) italic whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto"
        >
          {props.part.content.trim()}
        </div>
      </CollapsibleSection>
    </div>
  );
}

function ToolCallRenderer(props: { part: ToolCallPart }) {
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

function ToolResultPartRenderer(props: {
  part: ToolResultPart;
  isNew: boolean;
  isLoading: boolean;
  nextToolCallTick: number;
}) {
  return (
    <div class="mt-2 pl-5">
      <CollapsibleSection
        label="Result"
        expanded={props.isNew || props.part.state === "streaming"}
        autoCollapseMs={props.isNew ? 1500 : undefined}
        resetTimerOn={props.part.content}
        collapseOnTick={props.nextToolCallTick}
        leadingIcon={
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
        }
      >
        <div class="mt-1">
          <div class="text-xs text-(--text-secondary) font-mono whitespace-pre-wrap leading-relaxed max-h-75 overflow-y-auto">
            {renderToolResultContent(props.part.content, props.part.state)}
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
}

/**
 * Renders tool result content. Only applies YAML formatting when the
 * result has finished streaming (state is 'complete' or 'error').
 * During streaming, raw content is shown as-is.
 */
function renderToolResultContent(
  content: string | unknown[],
  state: string,
): string {
  if (state === "complete" || state === "error") {
    return formatToolResult(content);
  }
  // Still streaming — show raw content without YAML conversion
  return typeof content === "string"
    ? content
    : JSON.stringify(content, null, 2);
}
