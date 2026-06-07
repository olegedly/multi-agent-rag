import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createRoot } from "solid-js";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";

describe("useChat error propagation", () => {
  beforeEach(() => {
    // Reset fetch before each test
    delete (globalThis as any).fetch;
  });

  afterEach(() => {
    delete (globalThis as any).fetch;
  });

  it("fetchServerSentEvents: 422 detail reaches error signal", async () => {
    const detail = "Too many user messages (3). Maximum allowed is 2.";

    // Mock fetch to return 422
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail }), {
          status: 422,
          statusText: "Unprocessable Entity",
          headers: { "Content-Type": "application/json" },
        }),
      )) as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>(
      (resolve) => {
        createRoot((dispose) => {
          const chat = useChat({
            connection: fetchServerSentEvents("/api/chat"),
          });

          queueMicrotask(async () => {
            try {
              await chat.sendMessage("Hello");
            } catch {
              // sendMessage may not reject (library catches internally)
            }
            resolve({ errorMsg: chat.error()?.message ?? null });
            dispose();
          });
        });
      },
    );

    expect(result.errorMsg).toContain("Too many user messages");
  });

  it("fetchServerSentEvents: 429 detail reaches error signal", async () => {
    const detail = "Daily demo budget reached. Try again tomorrow.";

    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail }), {
          status: 429,
          statusText: "Too Many Requests",
          headers: { "Content-Type": "application/json" },
        }),
      )) as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>(
      (resolve) => {
        createRoot((dispose) => {
          const chat = useChat({
            connection: fetchServerSentEvents("/api/chat"),
          });

          queueMicrotask(async () => {
            try {
              await chat.sendMessage("Hello");
            } catch {
              // ignore
            }
            resolve({ errorMsg: chat.error()?.message ?? null });
            dispose();
          });
        });
      },
    );

    expect(result.errorMsg).toContain("Daily demo budget reached");
  });

  it("fetchServerSentEvents: error without detail still has status info", async () => {
    // Server returns non-ok without JSON body or detail
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response("Internal error", {
          status: 500,
          statusText: "Internal Server Error",
          headers: { "Content-Type": "text/plain" },
        }),
      )) as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>(
      (resolve) => {
        createRoot((dispose) => {
          const chat = useChat({
            connection: fetchServerSentEvents("/api/chat"),
          });

          queueMicrotask(async () => {
            try {
              await chat.sendMessage("Hello");
            } catch {
              // ignore
            }
            resolve({ errorMsg: chat.error()?.message ?? null });
            dispose();
          });
        });
      },
    );

    // Should still have the HTTP error prefix with status
    expect(result.errorMsg).toContain("HTTP error");
    expect(result.errorMsg).toContain("500");
  });
});
