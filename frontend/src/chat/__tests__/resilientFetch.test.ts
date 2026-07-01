import { describe, it, expect, vi, afterEach } from "vitest";
import { resilientFetch } from "../resilientFetch";

describe("resilientFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  /**
   * Tracer bullet: when the underlying reader's read() rejects after
   * signal abort, the catch block converts the error to AbortError
   * instead of propagating the raw error.
   *
   * We mock response.body.getReader() to return a controlled reader
   * whose read() rejects with TypeError the first time it's called.
   * Since signal is already aborted, the catch block converts to
   * AbortError.
   */
  it("converts reader TypeError to AbortError when signal is aborted", async () => {
    // Arrange: a response whose stream reader's read() throws
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: hello\n\n"));
      },
    });
    const response = new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });

    let readCall = 0;
    const cancelSpy = vi.fn().mockResolvedValue(undefined);
    const mockReader: Partial<ReadableStreamDefaultReader<Uint8Array>> = {
      read: vi.fn().mockImplementation(async () => {
        readCall++;
        if (readCall === 1) {
          // First read: succeed with chunk data
          return { done: false, value: new TextEncoder().encode("data: hello\n\n") };
        }
        // Second read: throw as if stream was cancelled
        throw new TypeError("Controller is already closed");
      }),
      cancel: cancelSpy,
      releaseLock: vi.fn(),
      closed: Promise.resolve(undefined),
    };

    vi.spyOn((response as any).body, "getReader").mockReturnValue(
      mockReader as any,
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    const ac = new AbortController();
    const wrapped = await resilientFetch("http://test/chat", {
      signal: ac.signal,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });

    const reader = wrapped.body!.getReader();
    // First read: succeeds via mock
    const first = await reader.read();
    expect(first.done).toBe(false);

    // Abort — now signal.aborted = true
    ac.abort();

    // Second read: mock throws TypeError, catch block converts to AbortError
    await expect(reader.read()).rejects.toThrow();
    await expect(reader.read()).rejects.toHaveProperty("name", "AbortError");
  });

  /**
   * Integration-style tracer bullet: after a normal stream read followed
   * by abort, the stream stops cleanly — either by returning {done: true}
   * (the well-behaved runtime path where cancel resolves the pending read
   * with done) or by rejecting with AbortError (the defensive path where
   * cancel throws and the catch block converts it). Both outcomes
   * represent a clean stop with no user-visible error.
   *
   * Unlike the mock-based test above, this uses a real ReadableStream
   * and exercises the actual cancel→pull→signal.aborted flow through
   * resilientFetch's stream wrapper without mocking getReader.
   */
  it("stops cleanly (done or AbortError) after abort following a normal read", async () => {
    let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controllerRef = controller;
        // Enqueue one chunk so the first read() succeeds
        controller.enqueue(new TextEncoder().encode("data: hello\n\n"));
      },
    });
    const response = new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    const ac = new AbortController();
    const wrapped = await resilientFetch("http://test/chat", {
      signal: ac.signal,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });

    const reader = wrapped.body!.getReader();

    // First read: consumes the buffered chunk
    const first = await reader.read();
    expect(first.done).toBe(false);
    expect(new TextDecoder().decode(first.value)).toBe("data: hello\n\n");

    // Issue a second read — this triggers pull() which calls
    // originalReader.read() and blocks (no more data enqueued).
    const secondPromise = reader.read();

    // Abort the signal. The abort handler calls originalReader.cancel().
    // In jsdom this resolves the pending read with {done: true}, so
    // pull() calls controller.close() and the read resolves with
    // {done: true}. In other runtimes it may reject, triggering the
    // defensive catch→AbortError path.
    ac.abort();

    // Both {done: true} and AbortError are acceptable clean-stop outcomes.
    try {
      const result = await secondPromise;
      expect(result.done).toBe(true);
    } catch (e: unknown) {
      expect((e as Error).name).toBe("AbortError");
    }
  });

  it("passes through data correctly when not aborted", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: hello\n\n"));
        controller.close();
      },
    });
    const response = new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    const ac = new AbortController();
    const wrapped = await resilientFetch("http://test/chat", {
      signal: ac.signal,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });

    const reader = wrapped.body!.getReader();
    const { done, value } = await reader.read();
    expect(done).toBe(false);
    expect(new TextDecoder().decode(value)).toBe("data: hello\n\n");

    const second = await reader.read();
    expect(second.done).toBe(true);
  });
});
