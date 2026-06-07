/**
 * A fetch wrapper that extracts error detail from non-ok responses
 * and throws with an enriched message, bypassing the library's
 * responseToSSEChunks which relies on Response.clone().json() —
 * a path that silently fails on Bun.
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
  return fetch(...args).then(async (response) => {
    if (response.ok) return response;

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
  });
}
