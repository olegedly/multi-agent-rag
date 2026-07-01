import { describe, it, expect } from "vitest";
import { groupParts } from "../groupParts";
import type { ToolCallPart, ToolResultPart, ThinkingPart, TextPart } from "@tanstack/ai-client";

function toolCall(id: string, name = "test"): ToolCallPart {
  return {
    type: "tool-call",
    id,
    name,
    arguments: "{}",
    state: "complete",
  } as ToolCallPart;
}

function toolResult(toolCallId: string, content = "result"): ToolResultPart {
  return {
    type: "tool-result",
    toolCallId,
    content,
    state: "complete",
  } as ToolResultPart;
}

function textBlock(content = "hello"): TextPart {
  return { type: "text", content };
}

function thinkingBlock(content = "thinking..."): ThinkingPart {
  return { type: "thinking", content };
}

describe("groupParts", () => {
  it("pairs a tool-call with its immediately following result", () => {
    const items = groupParts([toolCall("c1"), toolResult("c1")]);

    expect(items).toHaveLength(1);
    expect(items[0].type).toBe("pair");
    const pair = items[0] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair.toolCall.id).toBe("c1");
    expect(pair.toolResult?.toolCallId).toBe("c1");
  });

  it("pairs each tool-call with its matching result even when results arrive after all calls", () => {
    // This is the bug scenario: multiple calls launched async, results come back later in order
    const items = groupParts([
      toolCall("c1"),
      toolCall("c2"),
      toolCall("c3"),
      toolResult("c1"),
      toolResult("c2"),
      toolResult("c3"),
    ]);

    expect(items).toHaveLength(3);
    items.forEach((item, i) => {
      expect(item.type).toBe("pair");
      const pair = item as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
      expect(pair.toolResult).not.toBeNull();
    });
  });

  it("pairs by toolCallId, not by position", () => {
    // Results arrive in a different order than the calls
    const items = groupParts([
      toolCall("c1"),
      toolCall("c2"),
      toolResult("c2"), // c2's result arrives before c1's
      toolResult("c1"),
    ]);

    expect(items).toHaveLength(2);
    const pair0 = items[0] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    const pair1 = items[1] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };

    expect(pair0.toolCall.id).toBe("c1");
    expect(pair0.toolResult?.toolCallId).toBe("c1");

    expect(pair1.toolCall.id).toBe("c2");
    expect(pair1.toolResult?.toolCallId).toBe("c2");
  });

  it("leaves a tool-call unpaired when its result is absent", () => {
    const items = groupParts([toolCall("c1")]);

    expect(items).toHaveLength(1);
    expect(items[0].type).toBe("pair");
    const pair = items[0] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair.toolCall.id).toBe("c1");
    expect(pair.toolResult).toBeNull();
  });

  it("pairs the correct call when some calls have results and some don't", () => {
    const items = groupParts([
      toolCall("c1"),
      toolCall("c2"),
      toolResult("c1"),     // only c1 has a result
    ]);

    // Should produce: pair(c1, result-c1), pair(c2, null)
    expect(items).toHaveLength(2);

    const pair0 = items[0] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair0.toolCall.id).toBe("c1");
    expect(pair0.toolResult).not.toBeNull();

    const pair1 = items[1] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair1.toolCall.id).toBe("c2");
    expect(pair1.toolResult).toBeNull();
  });

  it("passes non-tool parts through as solo items", () => {
    const items = groupParts([textBlock("hello"), thinkingBlock("hmm"), textBlock("world")]);

    expect(items).toHaveLength(3);
    items.forEach((item) => {
      expect(item.type).toBe("solo");
    });
  });

  it("interleaves text/thinking parts with tool pairs", () => {
    const items = groupParts([
      textBlock("first"),
      toolCall("c1"),
      thinkingBlock("thinking"),
      toolResult("c1"),
      textBlock("done"),
    ]);

    expect(items).toHaveLength(4);
    expect(items[0].type).toBe("solo");
    expect((items[0] as { type: "solo"; part: TextPart }).part.type).toBe("text");

    expect(items[1].type).toBe("pair");
    const pair = items[1] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair.toolCall.id).toBe("c1");
    expect(pair.toolResult?.toolCallId).toBe("c1");

    expect(items[2].type).toBe("solo");
    expect((items[2] as { type: "solo"; part: ThinkingPart }).part.type).toBe("thinking");

    expect(items[3].type).toBe("solo");
    expect((items[3] as { type: "solo"; part: TextPart }).part.type).toBe("text");
  });

  it("handles empty parts array", () => {
    const items = groupParts([]);
    expect(items).toHaveLength(0);
  });

  it("handles results that arrive interleaved with text between calls and results", () => {
    const items = groupParts([
      toolCall("c1"),
      textBlock("intermediate"),
      toolCall("c2"),
      toolResult("c1"),
      toolResult("c2"),
    ]);

    // Output: pair(c1, r1), solo(text), pair(c2, r2)
    expect(items).toHaveLength(3);

    // call-1 with result-1
    const pair0 = items[0] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair0.toolCall.id).toBe("c1");
    expect(pair0.toolResult?.toolCallId).toBe("c1");

    // intermediate text
    expect(items[1].type).toBe("solo");

    // call-2 with result-2
    const pair1 = items[2] as { type: "pair"; toolCall: ToolCallPart; toolResult: ToolResultPart | null };
    expect(pair1.toolCall.id).toBe("c2");
    expect(pair1.toolResult?.toolCallId).toBe("c2");
  });

  it("skips standalone tool-results (consumed by their matching call)", () => {
    // A stray tool-result without a preceding call should be consumed
    const items = groupParts([
      toolCall("c1"),
      toolResult("c1"),
      toolResult("orphan"),
    ]);

    expect(items).toHaveLength(1);
    expect(items[0].type).toBe("pair");
  });
});
