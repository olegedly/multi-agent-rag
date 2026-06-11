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

  it("renders thinking parts in a collapsible reasoning panel", () => {
    const msg = thinkingMsg("m1", "Thought process", "Final answer");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
        nextToolCallTick={0}
      />
    ));

    expect(screen.getByText("Reasoned")).toBeTruthy();
    expect(screen.getByText("Thought process")).toBeTruthy();
    expect(screen.getByText("Final answer")).toBeTruthy();
  });

  it("hides thinking content when reasoning panel is collapsed", () => {
    const msg = thinkingMsg("m1", "Hidden thought", "Final");
    render(() => (
      <MessagePartRenderer
        msg={msg}
        isLoading={false}
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
});
