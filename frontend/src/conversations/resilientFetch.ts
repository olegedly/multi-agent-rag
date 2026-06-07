/**
 * A fetch wrapper that patches Response.clone() on non-ok responses
 * so the library's responseToSSEChunks can always read body.detail
 * via response.clone().json() — even in runtimes where Response.clone()
 * consumes the body stream and makes json() fail (jsdom, Node, etc.).
 *
 * The library code (connection-adapters.js:63-76) does:
 *
 *   const body = await response.clone().json();
 *   if (body.detail) detail = `: ${body.detail}`;
 *
 * but wraps it in try/catch {}, silently swallowing failures. This
 * wrapper pre-reads the body with response.text(), then patches
 * response.clone to return a plain object with a working json() method.
 *
 * On ok responses, the original response is passed through unchanged.
 */
export function resilientFetch(
  ...args: Parameters<typeof fetch>
): Promise<Response> {
  return fetch(...args).then(async (response) => {
    if (response.ok) return response;

    try {
      const bodyText = await response.text();
      // Patch clone to return a fake response that json() can parse
      response.clone = () =>
        ({
          ok: response.ok,
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
          json: () => Promise.resolve(JSON.parse(bodyText)),
        }) as unknown as Response;
    } catch {
      // Body read failed — let the library's clone try and fail naturally
    }

    return response;
  });
}
