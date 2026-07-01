import type { MessagePart, ToolCallPart, ToolResultPart } from "@tanstack/ai-client";


export interface SoloItem {
  type: "solo";
  part: MessagePart;
}

export interface PairItem {
  type: "pair";
  toolCall: ToolCallPart;
  toolResult: ToolResultPart | null;
}

export type GroupItem = SoloItem | PairItem;

/**
 * Groups message parts by pairing each tool-call with its matching result.
 *
 * Uses map-based lookup (by toolCallId) so that pairings work correctly
 * even when results arrive out of order or after multiple calls have been
 * sent (multi-async-tool-call scenario). Each tool-result is consumed at
 * most once; any remaining unmatched results are omitted from output.
 */
export function groupParts(parts: MessagePart[]): GroupItem[] {
  // First pass: collect all tool results keyed by toolCallId
  const resultMap = new Map<string, ToolResultPart>();
  for (const part of parts) {
    if (part.type === "tool-result") {
      resultMap.set(part.toolCallId, part);
    }
  }

  // Second pass: emit solo items and tool-calls (with looked-up results)
  const result: GroupItem[] = [];
  const consumed = new Set<string>();
  for (const part of parts) {
    if (part.type === "tool-call") {
      const match = resultMap.get(part.id);
      if (match && !consumed.has(part.id)) {
        consumed.add(part.id);
        result.push({ type: "pair", toolCall: part, toolResult: match });
      } else {
        result.push({ type: "pair", toolCall: part, toolResult: null });
      }
    } else if (part.type !== "tool-result") {
      result.push({ type: "solo", part });
    }
    // tool-result parts are skipped — consumed by their matching call above
  }
  return result;
}
