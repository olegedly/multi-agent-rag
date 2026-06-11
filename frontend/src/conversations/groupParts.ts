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
 * Groups message parts by pairing each tool-call with its matching result
 * (when the result immediately follows the call).
 */
export function groupParts(parts: MessagePart[]): GroupItem[] {
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
