import { describe, it, expect, afterEach } from "vitest";
import { createRoot } from "solid-js";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import { resilientFetch } from "../resilientFetch";

/**
 * resilientFetch throws on non-ok responses, bypassing the library's
 * responseToSSEChunks which depends on Response.clone().json() and
 * silently swallows failures.
 *
 * The library's normalizeConnectionAdapter.send() catches the thrown
 * error, pushes a RUN_ERROR event, and re-throws. ChatClient catches
 * the re-throw in streamResponse() and calls reportStreamError(),
 * which sets chat.error.
 */

describe("useChat error propagation", () => {
  afterEach(() => {
    delete (globalThis as Record<string, unknown>).fetch;
  });

  // ── Red: proves bug without resilientFetch ─────────────────────────

  it("detail is DROPPED when Response.clone().json() fails (no resilientFetch)", async () => {
    const detail = "Daily demo budget reached. Try again tomorrow.";

    // Simulate jsdom/Bun where clone() returns something whose json() rejects
    globalThis.fetch = (() => {
      const bodyText = JSON.stringify({ detail });
      let bodyConsumed = false;
      return Promise.resolve({
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
        headers: new Headers({ "Content-Type": "application/json" }),
        clone() {
          bodyConsumed = true;
          return {
            ok: false,
            status: 429,
            json: () => Promise.reject(new Error("Body already consumed")),
          } as unknown as Response;
        },
        text: () =>
          bodyConsumed
            ? Promise.reject(new Error("Body already consumed"))
            : Promise.resolve(bodyText),
      }) as unknown as Response;
    }) as unknown as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>((resolve) => {
      createRoot((dispose) => {
        const chat = useChat({
          connection: fetchServerSentEvents("/api/chat"),
        });
        queueMicrotask(async () => {
          try { await chat.sendMessage("Hello"); } catch {}
          resolve({ errorMsg: chat.error()?.message ?? null });
          dispose();
        });
      });
    });

    expect(result.errorMsg).not.toContain("Daily demo budget");
  });

  // ── Green: fix with resilientFetch ─────────────────────────────────

  it("resilientFetch preserves 429 detail when clone fails", async () => {
    const detail = "Daily demo budget reached. Try again tomorrow.";

    // Same broken clone as above
    globalThis.fetch = (() => {
      const bodyText = JSON.stringify({ detail });
      let bodyConsumed = false;
      return Promise.resolve({
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
        headers: new Headers({ "Content-Type": "application/json" }),
        clone() {
          bodyConsumed = true;
          return {
            ok: false,
            status: 429,
            json: () => Promise.reject(new Error("Body already consumed")),
          } as unknown as Response;
        },
        text: () =>
          bodyConsumed
            ? Promise.reject(new Error("Body already consumed"))
            : Promise.resolve(bodyText),
      }) as unknown as Response;
    }) as unknown as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>((resolve) => {
      createRoot((dispose) => {
        const chat = useChat({
          connection: fetchServerSentEvents("/api/chat", {
            fetchClient: resilientFetch,
          }),
        });
        queueMicrotask(async () => {
          try { await chat.sendMessage("Hello"); } catch {}
          resolve({ errorMsg: chat.error()?.message ?? null });
          dispose();
        });
      });
    });

    expect(result.errorMsg).toContain("Daily demo budget");
  });

  // ── Standard Response: 422 with detail ─────────────────────────────

  it("422 detail reaches error signal with standard Response", async () => {
    const detail = "Too many user messages (3). Maximum allowed is 2.";
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail }), {
          status: 422,
          statusText: "Unprocessable Entity",
          headers: { "Content-Type": "application/json" },
        }),
      )) as unknown as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>((resolve) => {
      createRoot((dispose) => {
        const chat = useChat({
          connection: fetchServerSentEvents("/api/chat", {
            fetchClient: resilientFetch,
          }),
        });
        queueMicrotask(async () => {
          try { await chat.sendMessage("Hello"); } catch {}
          resolve({ errorMsg: chat.error()?.message ?? null });
          dispose();
        });
      });
    });

    expect(result.errorMsg).toContain("Too many user messages");
  });

  // ── Non-JSON error body ────────────────────────────────────────────

  it("error without detail still has status info", async () => {
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response("Internal error", {
          status: 500,
          statusText: "Internal Server Error",
          headers: { "Content-Type": "text/plain" },
        }),
      )) as unknown as typeof fetch;

    const result = await new Promise<{ errorMsg: string | null }>((resolve) => {
      createRoot((dispose) => {
        const chat = useChat({
          connection: fetchServerSentEvents("/api/chat", {
            fetchClient: resilientFetch,
          }),
        });
        queueMicrotask(async () => {
          try { await chat.sendMessage("Hello"); } catch {}
          resolve({ errorMsg: chat.error()?.message ?? null });
          dispose();
        });
      });
    });

    expect(result.errorMsg).toContain("HTTP error");
    expect(result.errorMsg).toContain("500");
  });
});
