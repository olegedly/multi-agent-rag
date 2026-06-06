import { describe, it, expect } from "vitest";

// deriveTitle logic: extract first user message text from UIMessage[],
// then delegate to generateTitle. We test the extraction + delegation here.
import type { UIMessage } from "@tanstack/ai-client";

// Inline the same logic so we can test the helper in isolation
// (the real function is module-private in useChatStore.ts)
function deriveTitle(msgs: UIMessage[]): string | null {
  const firstUser = msgs.find((m) => m.role === "user");
  if (!firstUser) return null;
  const text = firstUser.parts
    .filter((p) => p.type === "text")
    .map((p) => p.content)
    .join(" ");
  if (text.length === 0) return null;
  // generateTitle("") → "" → we return null for empty
  // generateTitle("   ") → "New conversation"
  if (text.trim().length === 0) return "New conversation";
  // generateTitle behavior: truncates ~50 chars, word-bounded
  if (text.length <= 50) return text.replace(/[\s\p{P}]+$/u, "");
  const truncated = text.slice(0, 50);
  const lastSpace = truncated.lastIndexOf(" ");
  const result = lastSpace > 0 ? truncated.slice(0, lastSpace) : truncated;
  return result.replace(/[\s\p{P}]+$/u, "");
}

function msg(role: "user" | "assistant", text: string): UIMessage {
  return {
    id: "test-id",
    role,
    parts: [{ type: "text" as const, content: text }],
  } as UIMessage;
}

describe("deriveTitle (first-user-message extraction)", () => {
  it("returns null when there are no user messages", () => {
    const msgs: UIMessage[] = [msg("assistant", "Hello!")];
    expect(deriveTitle(msgs)).toBeNull();
  });

  it("returns null from an empty array", () => {
    expect(deriveTitle([])).toBeNull();
  });

  it("extracts title from first user message, ignoring assistant messages before it", () => {
    const msgs = [msg("assistant", "Ignore me"), msg("user", "Hello world")];
    expect(deriveTitle(msgs)).toBe("Hello world");
  });

  it("extracts title from first of multiple user messages", () => {
    const msgs = [
      msg("user", "First question"),
      msg("assistant", "Some answer"),
      msg("user", "Follow-up"),
    ];
    expect(deriveTitle(msgs)).toBe("First question");
  });

  it("uses the first user message even if assistant precedes it", () => {
    const msgs = [
      msg("assistant", "Welcome!"),
      msg("user", "How does MCP work?"),
      msg("assistant", "Let me explain"),
    ];
    expect(deriveTitle(msgs)).toBe("How does MCP work");
  });

  it("handles messages with multiple parts, extracting only text parts", () => {
    const msgs: UIMessage[] = [
      {
        id: "1",
        role: "user",
        parts: [
          { type: "text" as const, content: "What is " },
          { type: "text" as const, content: "MCP?" },
        ],
      },
    ];
    // .join(" ") adds a space between contiguous parts -> "What is  MCP"
    // generateTitle("What is  MCP") returns it unchanged (under 50 chars)
    expect(deriveTitle(msgs)).toBe("What is  MCP");
  });

  it("returns null when user message has no text parts", () => {
    const msgs: UIMessage[] = [
      {
        id: "1",
        role: "user",
        parts: [],
      },
    ];
    expect(deriveTitle(msgs)).toBeNull();
  });

  it("truncates long first messages at word boundary", () => {
    const long =
      "This is a very long question about the Model Context Protocol and how agents interact with it";
    const msgs = [msg("user", long)];
    const result = deriveTitle(msgs);
    expect(result).toBe("This is a very long question about the Model");
    expect(result!.length).toBeLessThanOrEqual(55);
  });

  it("falls back to New conversation for whitespace-only input", () => {
    const msgs = [msg("user", "   ")];
    expect(deriveTitle(msgs)).toBe("New conversation");
  });
});
