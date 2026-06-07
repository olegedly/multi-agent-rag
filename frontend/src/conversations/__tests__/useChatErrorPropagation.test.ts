import { describe, it, expect, afterEach } from "vitest";
import { createRoot } from "solid-js";
import { useChat, fetchServerSentEvents } from "@tanstack/ai-solid";
import { resilientFetch } from "../resilientFetch";

/**
 * CI/PROD BUG: jsdom's Response.clone() implementation can fail, and the
 * library's responseToSSEChunks uses an empty catch {} that silently
 * swallows the failure — losing the server's error detail.
 *
 * Fix: a custom fetchClient in fetchServerSentEvents options that pre-reads
 * the response body on non-ok and patches response.clone to return a
 * plain object with working json().
 */

describe("useChat error propagation", () => {
  afterEach(() => {
    delete (globalThis as Record<string, unknown>).fetch;
  });

  // ── RED: proves the bug without resilientFetch ─────────────────────

  it("RED: detail is DROPPED when Response.clone().json() fails", async () => {
    const detail = "Daily demo budget reached. Try again tomorrow.";

    // Simulate jsdom where clone() returns something whose json() rejects
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
        text: () => (bodyConsumed
          ? Promise.reject(new Error("Body already consumed"))
          : Promise.resolve(bodyText)),
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

    // BUG: clone().json() fails → details lost → only "HTTP error! status: 429"
    expect(result.errorMsg).not.toContain("Daily demo budget");
  });

  // ── GREEN: fix with resilientFetch ─────────────────────────────────

  it("GREEN: resilientFetch preserves detail when clone fails", async () => {
    const detail = "Daily demo budget reached. Try again tomorrow.";

    // Same broken clone simulation as above
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
        text: () => (bodyConsumed
          ? Promise.reject(new Error("Body already consumed"))
          : Promise.resolve(bodyText)),
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

  // ── Happy path: standard Response (clone works normally) ───────────

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

  // ── Fallback: non-JSON error body ──────────────────────────────────

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
