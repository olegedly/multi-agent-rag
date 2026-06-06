import { describe, it, expect } from "vitest";
import { generateTitle } from "../title";

describe("generateTitle", () => {
  it("truncates a long single-word input to ~50 chars", () => {
    const long =
      "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz0123456789abcdef";
    const result = generateTitle(long);
    // Single word with no space: just truncate to 50 exactly
    expect(result).toBe("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwx"); // 50 chars
    expect(result.length).toBe(50);
  });

  it("walks back to last word boundary before truncating", () => {
    const text = "This is a very long sentence that should be cut at a word boundary indeed";
    const result = generateTitle(text);
    expect(result).toBe("This is a very long sentence that should be cut");
  });

  it("returns input unchanged when shorter than max", () => {
    const text = "Hello world";
    expect(generateTitle(text)).toBe("Hello world");
  });

  it("trims trailing whitespace and punctuation", () => {
    const text = "   Hello world!!!   ";
    expect(generateTitle(text)).toBe("Hello world");
  });

  it("returns empty string for empty input", () => {
    expect(generateTitle("")).toBe("");
  });

  it("falls back to 'New conversation' for whitespace-only input", () => {
    expect(generateTitle("   ")).toBe("New conversation");
  });

  it("trims trailing punctuation after word-boundary truncation", () => {
    const text = "This is a very long question about MCP and ADK? Is that correct?";
    const result = generateTitle(text);
    // Should not end with punctuation
    expect(result).toMatch(/[a-zA-Z0-9]$/);
  });

  it("handles single word under max without changing it", () => {
    expect(generateTitle("Hello")).toBe("Hello");
  });
});
