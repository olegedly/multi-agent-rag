import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { ChatView } from "../ChatView";
import type { UIMessage } from "@tanstack/ai-client";

function textMsg(role: "user" | "assistant", content: string): UIMessage {
  return {
    id: crypto.randomUUID(),
    role,
    parts: [{ type: "text" as const, content }],
  };
}

function thinkingMsg(content: string): UIMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    parts: [
      { type: "thinking" as const, content },
      { type: "text" as const, content: "Final answer" },
    ],
  };
}

function toolCallMsg(): UIMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    parts: [
      {
        type: "tool-call" as const,
        id: "call-1",
        name: "rag_search",
        arguments: '{"query": "EU AI Act", "top_k": 5}',
        state: "complete" as const,
      },
      {
        type: "tool-result" as const,
        toolCallId: "call-1",
        content: "Found 3 documents about the EU AI Act",
        state: "complete" as const,
      },
      { type: "text" as const, content: "Based on my search..." },
    ],
  };
}

function toolCallStreamingMsg(): UIMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    parts: [
      {
        type: "tool-call" as const,
        id: "call-2",
        name: "rag_search",
        arguments: '{"query": "',
        state: "input-streaming" as const,
      },
    ],
  };
}

describe("ChatView", () => {
  it("renders user and assistant messages", () => {
    const messages = createSignal<UIMessage[]>([
      textMsg("user", "Hello"),
      textMsg("assistant", "Hi there!"),
    ]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("Hi there!")).toBeTruthy();
  });

  it("shows empty input area when no messages", () => {
    const messages = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const textarea = screen.getByPlaceholderText("Type your message...") as HTMLTextAreaElement;
    expect(textarea).toBeTruthy();
    expect(textarea.value).toBe("");
    // Send button should be disabled when input is empty
    const sendBtn = screen.getByText("Send") as HTMLButtonElement;
    expect(sendBtn.disabled).toBe(true);
  });

  it("calls onSend when submitting text", () => {
    const messages = createSignal<UIMessage[]>([]);
    const onSend = vi.fn();

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={onSend}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const textarea = screen.getByPlaceholderText("Type your message...") as HTMLTextAreaElement;
    fireEvent.input(textarea, { target: { value: "Test message" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(onSend).toHaveBeenCalledWith("Test message");
  });

  it("does not call onSend when loading", () => {
    const messages = createSignal<UIMessage[]>([textMsg("user", "Hi")]);
    const onSend = vi.fn();

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={onSend}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const textarea = screen.getByPlaceholderText("Type your message...") as HTMLTextAreaElement;
    // Textarea should be disabled when loading
    expect(textarea.disabled).toBe(true);

    // Send button should be replaced by Stop button
    expect(screen.getByText("Stop")).toBeTruthy();
    expect(() => screen.getByText("Send")).toThrow();
  });

  it("does not submit empty text", () => {
    const messages = createSignal<UIMessage[]>([]);
    const onSend = vi.fn();

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={onSend}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const textarea = screen.getByPlaceholderText("Type your message...") as HTMLTextAreaElement;
    // Submit with only whitespace
    fireEvent.input(textarea, { target: { value: "   " } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("calls onStop when Stop button is clicked", () => {
    const messages = createSignal<UIMessage[]>([textMsg("user", "Hi")]);
    const onStop = vi.fn();

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={onStop}
        onDismissStorageError={() => {}}
      />
    ));

    fireEvent.click(screen.getByText("Stop"));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("shows error message", () => {
    const messages = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error="Something went wrong"
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    expect(screen.getByText("Something went wrong")).toBeTruthy();
  });

  it("shows storage error banner and dismisses on button click", () => {
    const messages = createSignal<UIMessage[]>([]);
    const onDismiss = vi.fn();

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError="Storage quota exceeded"
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={onDismiss}
      />
    ));

    expect(screen.getByText("Storage quota exceeded")).toBeTruthy();

    // Click dismiss (the X button inside the banner)
    const dismissBtn = screen.getByText("Storage quota exceeded").closest("div")?.querySelector("button");
    fireEvent.click(dismissBtn!);
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("shows typing indicator when loading after user message", () => {
    const messages = createSignal<UIMessage[]>([textMsg("user", "Hi")]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // The ellipsis indicator should be present
    const dots = document.querySelectorAll(".ellipsis-indicator .dot");
    expect(dots.length).toBe(3);
  });

  it("does NOT show typing indicator when loading with no messages yet", () => {
    const messages = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const dots = document.querySelectorAll(".ellipsis-indicator");
    expect(dots.length).toBe(0);
  });

  it("does NOT show typing indicator when last message is assistant", () => {
    const messages = createSignal<UIMessage[]>([
      textMsg("user", "Hi"),
      textMsg("assistant", "Hello"),
    ]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const dots = document.querySelectorAll(".ellipsis-indicator");
    expect(dots.length).toBe(0);
  });

  // ── Tracer bullet: ThinkingPart rendering ────────────────────────────

  it("renders thinking parts in a collapsible reasoning panel", () => {
    const messages = createSignal<UIMessage[]>([thinkingMsg("Thought process here")]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Should show a reasoning section label
    expect(screen.getByText("Reasoned")).toBeTruthy();
    // Should show the thinking content
    expect(screen.getByText("Thought process here")).toBeTruthy();
    // Should show the final text answer too
    expect(screen.getByText("Final answer")).toBeTruthy();
  });

  it("hides thinking content when reasoning panel is collapsed", async () => {
    const messages = createSignal<UIMessage[]>([thinkingMsg("Hidden thought")]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Content should be visible initially
    expect(screen.getByText("Hidden thought")).toBeTruthy();

    // Click the toggle to collapse
    const toggle = screen.getByText("Reasoned");
    fireEvent.click(toggle);

    // Content hidden via CSS transition — check the wrapper class
    const wrapper = screen.getByText("Hidden thought").closest('[class*="overflow-hidden"]')!;
    expect(wrapper.className).toContain("opacity-0");
  });

  // ── Tracer bullet: ToolCallPart rendering ────────────────────────────

  it("renders completed tool call parts", () => {
    const messages = createSignal<UIMessage[]>([toolCallMsg()]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Tool name should be visible
    expect(screen.getByText("rag_search")).toBeTruthy();
    // Tool result content should be visible
    expect(screen.getByText("Found 3 documents about the EU AI Act")).toBeTruthy();
    // Final text should still be visible
    expect(screen.getByText("Based on my search...")).toBeTruthy();
  });

  it("renders streaming tool call parts with partial args", () => {
    const messages = createSignal<UIMessage[]>([toolCallStreamingMsg()]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Tool name should be visible
    expect(screen.getByText("rag_search")).toBeTruthy();
    // The streaming state indicator
    expect(screen.getByText("streaming")).toBeTruthy();
  });

  // ── Tracer bullet: JSON tool result converted to YAML ───────────────

  it("renders JSON tool result content as YAML", () => {
    const jsonResult = JSON.stringify({
      results: [
        { id: 1, score: 0.95, content: "Chunk about AI" },
        { id: 2, score: 0.87, content: "Chunk about regulation" },
      ],
      error: null,
    });

    const msg: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "rag_search",
          arguments: '{"query": "AI"}',
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: jsonResult,
          state: "complete" as const,
        },
      ],
    };
    const messages = createSignal<UIMessage[]>([msg]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // YAML output should have unquoted keys and colon-separated values
    const all = document.body.textContent || "";
    expect(all).toContain("results:");
    expect(all).toContain("error: null");
    expect(all).toContain("score: 0.95");
    // No JSON double-quoted keys in YAML output
    expect(all).not.toContain('"results"');
  });

  // ── Tracer bullet: literal \n in tool results converted to real newlines ──

  it("converts literal \\n sequences to real newlines in YAML output", () => {
    // Simulate backend JSON with literal \n in string values
    const jsonResult = JSON.stringify({
      content: "Line one\\nLine two\\nLine three",
    });

    const msg: UIMessage = {
      id: crypto.randomUUID(),
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
          content: jsonResult,
          state: "complete" as const,
        },
      ],
    };
    const messages = createSignal<UIMessage[]>([msg]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const all = document.body.textContent || "";
    // The YAML block scalar pipe symbol indicates multi-line
    expect(all).toContain("content: |");
    // Each line should appear on its own line, not as one with literal \n
    expect(all).toContain("Line one");
    expect(all).toContain("Line two");
    expect(all).toContain("Line three");
    // No literal \n should remain
    expect(all).not.toContain("Line one\\n");
  });

  // ── Tracer bullet: vertical spacing between tool parts ──────────────

  it("has vertical spacing between adjacent tool calls", () => {
    const msg: UIMessage = {
      id: crypto.randomUUID(),
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
          type: "tool-call" as const,
          id: "call-2",
          name: "rag_read_document",
          arguments: "{}",
          state: "complete" as const,
        },
      ],
    };
    const messages = createSignal<UIMessage[]>([msg]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Both tool names should be visible
    expect(screen.getByText("rag_search")).toBeTruthy();
    expect(screen.getByText("rag_read_document")).toBeTruthy();
  });

  // ── Tracer bullet: tool call arguments are visible, not truncated ──────

  it("shows tool call arguments (not truncated)", () => {
    const args = '{"query": "EU AI Act", "top_k": 5}';
    const msg: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "rag_search",
          arguments: args,
          state: "complete" as const,
        },
      ],
    };
    const messages = createSignal<UIMessage[]>([msg]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const all = document.body.textContent || "";
    // Arguments are now rendered as YAML
    expect(all).toContain("query: EU AI Act");
    expect(all).toContain("top_k: 5");
    // No raw JSON braces remaining
    expect(all).not.toContain('"query"');
  });

  // ── Tracer bullet: empty parts ───────────────────────────────────────

  it("handles messages with no parts gracefully", () => {
    const msg: UIMessage = { id: "empty", role: "assistant", parts: [] };
    const messages = createSignal<UIMessage[]>([msg]);

    render(() => (
      <ChatView
        messages={messages[0]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Should not crash — role badge should show
    expect(screen.getByText("assistant")).toBeTruthy();
  });

  // ── Bug 1: tool result auto-expand during loading ────────────────────

  /** Check if a tool result content's wrapper has the expanded CSS class. */
  function expectToolResultState(resultText: string, expanded: boolean) {
    const el = screen.getByText(resultText);
    const wrapper = el.closest('[class*="overflow-hidden"]') as HTMLElement | null;
    expect(wrapper).toBeTruthy();
    const cls = wrapper!.className;
    const hasCollapsed = cls.includes("max-h-0") && cls.includes("opacity-0");
    if (expanded) {
      expect(hasCollapsed).toBe(false);
    } else {
      expect(hasCollapsed).toBe(true);
    }
  }

  it("starts tool result expanded when it appears during loading (no prior messages)", () => {
    const [msgs, setMsgs] = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={msgs}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    const msg: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "test_tool",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "Hello from tool!",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([msg]);
    expectToolResultState("Hello from tool!", true);
  });

  it("starts tool result collapsed when loaded from storage (no loading)", () => {
    const msg: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "existing-call",
          name: "previous_tool",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "existing-call",
          content: "Old result from storage",
          state: "complete" as const,
        },
        { type: "text" as const, content: "Finished" },
      ],
    };
    render(() => (
      <ChatView
        messages={() => [msg]}
        isLoading={false}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));
    expectToolResultState("Old result from storage", false);
  });

  it("starts new tool result expanded when arriving after loading starts", () => {
    const existingMsg: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "existing-call",
          name: "previous_tool",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "existing-call",
          content: "Old result",
          state: "complete" as const,
        },
        { type: "text" as const, content: "Finished" },
      ],
    };
    const newMsg: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "new-call",
          name: "new_tool",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "new-call",
          content: "Brand new result",
          state: "complete" as const,
        },
      ],
    };
    const [msgs, setMsgs] = createSignal<UIMessage[]>([existingMsg]);
    const [loading, setLoading] = createSignal(false);
    render(() => (
      <ChatView
        messages={msgs}
        isLoading={loading()}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));
    expectToolResultState("Old result", false);
    setLoading(true);
    return new Promise<void>((resolve) => {
      queueMicrotask(() => {
        setMsgs([existingMsg, newMsg]);
        expectToolResultState("Brand new result", true);
        resolve();
      });
    });
  });

  // ── Bug: chaotic expansion with multiple sequential tool calls ────

  it("does not re-expand previous result when a second tool-call arrives (same message)", () => {
    const [msgs, setMsgs] = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={msgs}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Step 1: first tool-call with result arrives
    const step1: UIMessage = {
      id: crypto.randomUUID(),
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step1]);

    expectToolResultState("First result", true);

    // Step 2: second tool-call with result arrives, appended to same msg
    const step2: UIMessage = {
      id: step1.id,
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "read",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-2",
          content: "Second result",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step2]);

    // First result should be collapsed (nextToolCallTick collapsed it when
    // call-2 appeared). Second result should be expanded (new during loading).
    expectToolResultState("Second result", true);
  });

  it("does not collapse results that arrive already paired with their calls", () => {
    const [msgs, setMsgs] = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={msgs}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Two tool-calls with their results arrive together in one batch
    const msg: UIMessage = {
      id: crypto.randomUUID(),
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "read",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-2",
          content: "Second result",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([msg]);

    // Both should be expanded — they're new during loading
    expectToolResultState("First result", true);
    expectToolResultState("Second result", true);
  });

  it("collapses paired results only when a truly unpaired tool-call appears", () => {
    const [msgs, setMsgs] = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={msgs}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Step 1: paired call+result arrive
    const step1: UIMessage = {
      id: crypto.randomUUID(),
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "read",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-2",
          content: "Second result",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step1]);

    expectToolResultState("First result", true);
    expectToolResultState("Second result", true);

    // Step 2: new UNPAIRED tool-call arrives (no result)
    const step2: UIMessage = {
      id: step1.id,
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "read",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-2",
          content: "Second result",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-3",
          name: "another",
          arguments: "{}",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step2]);

    // Both should now be collapsed — a new unpaired call arrived
    expectToolResultState("First result", false);
    expectToolResultState("Second result", false);
  });

  it("does not collapse result when first tool-call arrives alone then result arrives later", () => {
    const [msgs, setMsgs] = createSignal<UIMessage[]>([]);

    render(() => (
      <ChatView
        messages={msgs}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Step 1: first tool-call alone (no result yet)
    const step1: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "tool-call" as const,
          id: "call-1",
          name: "search",
          arguments: "{}",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step1]);

    // No result to check yet

    // Step 2: result arrives for call-1, and a new call-2 appears too
    const step2: UIMessage = {
      id: step1.id,
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
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
    setMsgs([step2]);

    // First result arrived in same batch as call-2. The pairing means
    // call-1 is resolved by its result, but call-2 is unresolved.
    // The result should STILL be expanded (it's new during loading, and
    // the only truly new tool-call — call-2 — is part of the same batch).
    expectToolResultState("First result", true);
  });

  it("key stability: does not re-render previously collapsed results as expanded", () => {
    const [msgs, setMsgs] = createSignal<UIMessage[]>([]);

    const { container } = render(() => (
      <ChatView
        messages={msgs}
        isLoading={true}
        error={null}
        storageError={null}
        onSend={() => {}}
        onStop={() => {}}
        onDismissStorageError={() => {}}
      />
    ));

    // Step 1: single paired call+result
    const step1: UIMessage = {
      id: "msg-1",
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step1]);
    expectToolResultState("First result", true);

    // Step 2: unpaired call-2 arrives
    const step2: UIMessage = {
      id: "msg-1",
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
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
    setMsgs([step2]);
    expectToolResultState("First result", false);

    // Step 3: result for call-2 arrives
    const step3: UIMessage = {
      id: "msg-1",
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
          type: "tool-result" as const,
          toolCallId: "call-1",
          content: "First result",
          state: "complete" as const,
        },
        {
          type: "tool-call" as const,
          id: "call-2",
          name: "read",
          arguments: "{}",
          state: "complete" as const,
        },
        {
          type: "tool-result" as const,
          toolCallId: "call-2",
          content: "Second result",
          state: "complete" as const,
        },
      ],
    };
    setMsgs([step3]);

    // First result should stay collapsed (it was collapsed and shouldn't re-expand)
    expectToolResultState("First result", false);
    // Second result should be expanded (new, during loading)
    expectToolResultState("Second result", true);
  });
});
