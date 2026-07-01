import { describe, it, expect } from "vitest";
import { formatToolResult } from "../formatToolResult";

describe("formatToolResult", () => {
  it("formats a JSON string as YAML", () => {
    const json = JSON.stringify({ query: "EU AI Act", top_k: 5 });
    const result = formatToolResult(json);
    expect(result).toContain("query: EU AI Act");
    expect(result).toContain("top_k: 5");
    expect(result).not.toContain('"query"');
  });

  it("converts literal \\n sequences to real newlines", () => {
    const json = JSON.stringify({ content: "Line one\\nLine two" });
    const result = formatToolResult(json);
    expect(result).toContain("Line one");
    expect(result).toContain("Line two");
    // Multi-line value should use block scalar |
    expect(result).toContain("content: |");
  });

  it("returns non-JSON strings unchanged", () => {
    const result = formatToolResult("plain text");
    expect(result).toBe("plain text");
  });

  it("formats an array as YAML list", () => {
    const arr = [{ id: 1, score: 0.95 }];
    const result = formatToolResult(JSON.stringify(arr));
    expect(result).toContain("id: 1");
    expect(result).toContain("score: 0.95");
  });

  it("handles null and undefined values", () => {
    const json = JSON.stringify({ a: null, b: undefined });
    const result = formatToolResult(json);
    expect(result).toContain("a: null");
  });

  it("handles empty objects", () => {
    const result = formatToolResult(JSON.stringify({}));
    expect(result).toBe("{}");
  });

  it("handles empty arrays", () => {
    const result = formatToolResult(JSON.stringify([]));
    expect(result).toBe("[]");
  });

  it("handles deeply nested structures", () => {
    const obj = { level1: { level2: { level3: { key: "deep" } } } };
    const result = formatToolResult(JSON.stringify(obj));
    expect(result).toContain("level1:");
    expect(result).toContain("level2:");
    expect(result).toContain("level3:");
    expect(result).toContain("key: deep");
  });

  it("renders arrays of primitives correctly", () => {
    const result = formatToolResult(JSON.stringify(["a", "b", "c"]));
    expect(result).toContain("- a");
    expect(result).toContain("- b");
    expect(result).toContain("- c");
  });

  it("renders raw non-string content via JSON.stringify", () => {
    const result = formatToolResult([{ id: 1 }]);
    expect(result).toContain("id");
    expect(result).toContain("1");
  });
});
