/**
 * A fetch wrapper that:
 * 1. Extracts error detail from non-ok responses and throws (enriched).
 * 2. Wraps the response body in a ReadableStream that cancels the
 *    underlying reader when the AbortSignal fires — so Stop actually
 *    stops the stream instead of blocking on reader.read() forever.
 *
 * The library's normalizeConnectionAdapter.send() catches errors
 * thrown from connect() and sets them as RUN_ERROR with the full
 * message, which reaches chat.error()?.message.
 *
 * On ok responses, the raw Response is returned for the library
 * to stream SSE chunks from.
 */
export function resilientFetch(
  ...args: Parameters<typeof fetch>
): Promise<Response> {
  const [url, init] = args;
  const signal = init?.signal;

  return fetch(...args).then(async (response) => {
    if (!response.ok || !response.body || !signal) {
      if (!response.ok) {
        let detail = "";
        try {
          const bodyText = await response.text();
          const body = JSON.parse(bodyText) as Record<string, unknown>;
          if (body.detail) detail = `: ${body.detail}`;
        } catch {
          // Couldn't read/parse body — fall through with empty detail
        }

        throw new Error(
          `HTTP error! status: ${response.status} ${response.statusText}${detail}`,
        );
      }
      return response;
    }

    // Wrap the response body in a ReadableStream that checks the abort
    // signal before each read. This lets `stop()` actually cancel the
    // in-flight SSE stream, instead of leaving reader.read() blocked.
    const originalReader = response.body.getReader();

    // When the abort signal fires, cancel the underlying reader so
    // the wrapped pull() resolves (with done=true or an error) instead
    // of blocking forever.
    signal.addEventListener(
      "abort",
      () => {
        originalReader.cancel().catch(() => {});
      },
      { once: true },
    );

    const wrappedStream = new ReadableStream({
      async pull(controller) {
        try {
          const { done, value } = await originalReader.read();
          if (done) {
            controller.close();
          } else {
            controller.enqueue(value);
          }
        } catch (err) {
          controller.error(err);
        }
      },
      cancel() {
        originalReader.cancel().catch(() => {});
      },
    });

    return new Response(wrappedStream, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  });
}
