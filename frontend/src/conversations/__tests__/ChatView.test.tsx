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
});
