/**
 * A fetch wrapper that pre-reads non-ok response bodies so the library's
 * responseToSSEChunks can always extract body.detail via
 * response.clone().json() — even in runtimes where Response.clone()
 * silently fails (jsdom, Bun, Node).
 *
 * The library code (connection-adapters.js:63-76) does:
 *
 *   const body = await response.clone().json();
 *   if (body.detail) detail = `: ${body.detail}`;
 *
 * but wraps it in try/catch {}, silently swallowing failures.
 *
 * Instead of patching the original Response (which doesn't work on Bun),
 * this returns a plain wrapper object that satisfies the shape the
 * library needs: response.ok, status, statusText, and clone().
 */
export function resilientFetch(
  ...args: Parameters<typeof fetch>
): Promise<Response> {
  return fetch(...args).then(async (response) => {
    if (response.ok) return response;

    try {
      const bodyText = await response.text();
      const parsed = JSON.parse(bodyText) as Record<string, unknown>;

      // Return a plain object with just the shape the library reads.
      // The library never passes a non-ok response to getResponseStreamReader,
      // so we don't need to implement the full Response interface.
      return {
        ok: false,
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
        clone() {
          return {
            ok: false,
            status: response.status,
            statusText: response.statusText,
            json: () => Promise.resolve(parsed),
          };
        },
      } as unknown as Response;
    } catch {
      // Body read/parse failed — return original and let library's
      // own try/catch in responseToSSEChunks handle the fallback
      return response;
    }
  });
}
