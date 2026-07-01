import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { MessagePartRenderer } from "../MessagePartRenderer";
import type { UIMessage } from "@tanstack/ai-client";

function textMsg(id: string, role: "user" | "assistant", content: string): UIMessage {
  return {
    id,
    role,
    parts: [{ type: "text" as const, content }],
  };
}

function thinkingMsg(id: string, thought: string, answer: string): UIMessage {
  return {
    id,
    role: "assistant",
    parts: [
      { type: "thinking" as const, content: thought },
      { type: "text" as const, content: answer },
    ],
  };
}

function toolCallMsg(id: string, name: string, args: string, state: string = "complete"): UIMessage {
  return {
    id: `${id}-msg`,
    role: "assistant",
    parts: [
      {
        type: "tool-call" as const,
        id,
        name,
        arguments: args,
        state: state as any,
      },
    ],
  };
}

function pairedMsg(
  id: string,
  name: string,
  args: string,
  resultContent: string,
): UIMessage {
  return {
    id: `${id}-msg`,
    role: "assistant",
    parts: [
      {
        type: "tool-call" as const,
        id,
        name,
        arguments: args,
        state: "complete" as const,
      },
      {
        type: "tool-result" as const,
        toolCallId: id,
        content: resultContent,
        state: "complete" as const,
      },
    ],
  };
}

describe("MessagePartRenderer", () => {
  it("renders text parts as markdown", () => {
    const msg = textMsg("m1", "user", "Hello **world**");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    // Markdown bold should be rendered
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("world")).toBeTruthy();
  });

  it("renders thinking parts expanded during streaming (isLoading=true)", () => {
    const msg = thinkingMsg("m1", "Thought process", "Final answer");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={true}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("Reasoned")).toBeTruthy();
    expect(screen.getByText("Thought process")).toBeTruthy();
    expect(screen.getByText("Final answer")).toBeTruthy();
  });

  it("collapses thinking content when loaded from storage (isLoading=false)", () => {
    const msg = thinkingMsg("m1", "Stored thought", "Done");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    // Content hidden via CSS transition
    const wrapper = screen.getByText("Stored thought").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).toContain("opacity-0");
  });

  it("hides thinking content when reasoning panel is collapsed", () => {
    const msg = thinkingMsg("m1", "Hidden thought", "Final");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={true}
        nextToolCallTick={0}
      />
    ));

    // Content is hidden via CSS transition — check the wrapper class
    const wrapper = screen.getByText("Hidden thought").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).not.toContain("opacity-0");

    fireEvent.click(screen.getByText("Reasoned"));
    expect(wrapper.className).toContain("opacity-0");
  });

  it("renders tool call name and state badge", () => {
    const msg = toolCallMsg("call-1", "rag_search", '{"query":"test"}', "complete");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("rag_search")).toBeTruthy();
    expect(screen.getByText("done")).toBeTruthy();
  });

  it("renders tool call arguments as YAML", () => {
    const msg = toolCallMsg("call-1", "rag_search", '{"query":"EU AI Act","top_k":5}', "complete");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    const all = document.body.textContent || "";
    expect(all).toContain("query: EU AI Act");
    expect(all).toContain("top_k: 5");
  });

  it("renders paired tool call and result together", () => {
    const msg = pairedMsg("call-1", "rag_search", "{}", "Found 3 results");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("rag_search")).toBeTruthy();
    expect(screen.getByText("Found 3 results")).toBeTruthy();
  });

  it("renders paired result in a collapsible section", () => {
    const msg = pairedMsg("call-1", "test", "{}", "Collapsible result");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("Result")).toBeTruthy();
    expect(screen.getByText("Collapsible result")).toBeTruthy();
  });

  it("renders multiple part types in sequence", () => {
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        { type: "thinking" as const, content: "Reasoning step" },
        { type: "text" as const, content: "Answer text" },
      ],
    };
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("Reasoning step")).toBeTruthy();
    expect(screen.getByText("Answer text")).toBeTruthy();
  });

  it("handles messages with no parts gracefully", () => {
    const msg: UIMessage = { id: "empty", role: "assistant", parts: [] };
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    // Should render the role badge
    expect(screen.getByText("assistant")).toBeTruthy();
  });

  it("shows streaming state badge", () => {
    const msg = toolCallMsg("call-1", "rag_search", '{"query":"', "input-streaming");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={true}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("streaming")).toBeTruthy();
  });

  it("renders multiple consecutive tool-calls", () => {
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "search",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "read",
          arguments: "{}",
          state: "complete" as const,
        },
      ],
    };
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("search")).toBeTruthy();
    expect(screen.getByText("read")).toBeTruthy();
  });

  // ── Streaming vs complete: YAML conversion timing ────────────────

  it("renders streaming tool result content as raw text, not YAML", () => {
    // A streaming result with JSON content — should show raw, not YAML
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-stream",
          name: "rag_search",
          arguments: "{}",
          state: "input-streaming" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-stream",
          content: '{"results": [{"score": 0.95}]}',
          state: "streaming" as const,
        },
      ],
    };

    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={true}
        nextToolCallTick={0}
      />
    ));

    const all = document.body.textContent || "";
    // Streaming — should show the raw JSON, not YAML
    expect(all).toContain('"results"');
    expect(all).toContain('"score"');
    // Should NOT have YAML keys
    expect(all).not.toContain("results:");
  });

  it("renders completed tool result content as YAML", () => {
    // Same JSON content but complete state — should be YAML
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-done",
          name: "rag_search",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-done",
          content: '{"results": [{"score": 0.95}]}',
          state: "complete" as const,
        },
      ],
    };

    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    const all = document.body.textContent || "";
    // Complete — should show YAML
    expect(all).toContain("results:");
    expect(all).toContain("score: 0.95");
    // Should NOT have raw JSON keys
    expect(all).not.toContain('"results"');
  });

  it("renders error state tool result content as YAML", () => {
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-err",
          name: "rag_search",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-err",
          content: '{"error": "Rate limited", "code": 429}',
          state: "error" as const,
          error: "Rate limited",
        },
      ],
    };

    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    const all = document.body.textContent || "";
    // Error is terminal — should show YAML
    expect(all).toContain("error: Rate limited");
    expect(all).toContain("code: 429");
  });

  it("transitions from raw text to YAML when result becomes complete", () => {
    // Simulate streaming: a tool result arriving in streaming state,
    // then being replaced by a complete version.
    const msg = createSignal({
      id: "m1",
      role: "assistant" as const,
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "rag_search",
          arguments: "{}",
          state: "input-streaming" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: '{"score": 0.95}',
          state: "streaming" as const,
        },
      ],
    });

    // Render the streaming version directly — Index+For don't apply here
    const { unmount } = render(() => (
      <MessagePartRenderer
        msg={msg[0]()}
        isLoading={true}
        nextToolCallTick={0}
      />
    ));

    let bodyText = document.body.textContent || "";
    expect(bodyText).toContain('"score"');
    expect(bodyText).not.toContain("score: 0.95");

    // Unmount and re-render with complete version
    unmount();

    const complete: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "rag_search",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: '{"score": 0.95}',
          state: "complete" as const,
        },
      ],
    };

    render(() => (
      <MessagePartRenderer
        msg={complete}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    bodyText = document.body.textContent || "";
    expect(bodyText).toContain("score: 0.95");
    expect(bodyText).not.toContain('"score"');
  });

  // ── Agent name badge ──────────────────────────────────────────────

  it("renders agent name badge when agentNameMap has entry", () => {
    const msg: UIMessage = {
      id: "msg-1",
      role: "assistant",
      parts: [{ type: "text" as const, content: "Analysis" }],
    };
    const agentNameMap = { "msg-1": "Researcher" };
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
        agentNameMap={agentNameMap}
      />
    ));

    expect(screen.getByText("🔍 Researcher")).toBeTruthy();
  });

  it("does not render agent name badge when agentNameMap is empty", () => {
    const msg: UIMessage = {
      id: "msg-1",
      role: "assistant",
      parts: [{ type: "text" as const, content: "Analysis" }],
    };
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
        agentNameMap={{}}
      />
    ));

    expect(screen.queryByText(/Researcher|Critic|Synthesizer/)).toBeNull();
  });

  it("renders interleaved thinking, tool calls, and text in correct order", () => {
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        { type: "thinking" as const, content: "First reasoning" },
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "rag_search",
          arguments: '{"query":"first"}',
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: '{"results": ["first result"]}',
          state: "complete" as const,
        },
        { type: "thinking" as const, content: "Second reasoning" },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "rag_read_document",
          arguments: '{"chunk_ids":[1]}',
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-2",
          content: '{"results": ["read result"]}',
          state: "complete" as const,
        },
        { type: "text" as const, content: "Final answer" },
      ],
    };

    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    // All parts should appear in order
    const allText = document.body.textContent ?? "";
    const firstIdx = allText.indexOf("First reasoning");
    const tool1Idx = allText.indexOf("rag_search");
    const secondIdx = allText.indexOf("Second reasoning");
    const tool2Idx = allText.indexOf("rag_read_document");
    const finalIdx = allText.indexOf("Final answer");

    expect(firstIdx).toBeGreaterThanOrEqual(0);
    expect(tool1Idx).toBeGreaterThan(firstIdx);
    expect(secondIdx).toBeGreaterThan(tool1Idx);
    expect(tool2Idx).toBeGreaterThan(secondIdx);
    expect(finalIdx).toBeGreaterThan(tool2Idx);
  });

  it("does not render tool call JSON as raw text outside tool call renderer", () => {
    const msg: UIMessage = {
      id: "m1",
      role: "assistant",
      parts: [
        { type: "thinking" as const, content: "Searching for data..." },
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "rag_search",
          arguments: '{"query":"safe uses"}',
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: '{"results": ["found"]}',
          state: "complete" as const,
        },
        { type: "text" as const, content: "Safe uses include..." },
      ],
    };

    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    // The tool name should appear (from the ToolCallRenderer badge)
    expect(screen.getByText("rag_search")).toBeTruthy();

    // The tool state badge should say "done"
    expect(screen.getByText("done")).toBeTruthy();

    // The tool call arguments appear as YAML inside the tool call renderer.
    // Arguments {"query":"safe uses"} → YAML: "query: safe uses"
    const bodyText = document.body.textContent ?? "";
    expect(bodyText).toContain("query:");
    expect(bodyText).toContain("safe uses");

    // The result "found" should be visible (inside tool result collapsible)
    expect(bodyText).toContain("found");

    // The thinking content should be visible
    expect(screen.getByText("Searching for data...")).toBeTruthy();

    // The final text should be visible
    expect(screen.getByText("Safe uses include...")).toBeTruthy();

    // CRITICAL: The raw JSON blob "{"type":"rag_search"..." should NOT
    // appear anywhere. The tool call arguments go through the tool call
    // renderer, not as a separate TextPart.
    // The type field from a hypothetical content-injected JSON would be
    // '{"type":"rag_search"' — this must not appear verbatim.
    expect(bodyText).not.toContain('"type":"rag_search"');
  });

  it("renders emoji based on agent role", () => {
    const msg: UIMessage = {
      id: "msg-1",
      role: "assistant",
      parts: [{ type: "text" as const, content: "Test" }],
    };
    const expectations: Record<string, string> = {
      Researcher: "🔍",
      Critic: "⚖️",
      Synthesizer: "📝",
    };
    const names = Object.keys(expectations);
    for (let i = 0; i < names.length; i++) {
      const name = names[i];
      const emoji = expectations[name];
      const { unmount } = render(() => (
        <MessagePartRenderer
          msg={msg}
          isLoading={false}
          nextToolCallTick={0}
          agentNameMap={{ "msg-1": name }}
        />
      ));
      expect(screen.getByText(`${emoji} ${name}`)).toBeTruthy();
      unmount();
    }
  });
});
