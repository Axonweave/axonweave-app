import { API_BASE, ApiRequestError, getCsrfToken } from "@/lib/api/client";
import { SseParser, toStreamEvent, type StreamEvent } from "./sse";

/**
 * POST a JSON body and yield the typed SSE events of the response (D-44).
 * Sends the session cookie and the CSRF header. Errors found before streaming starts (404, 422,
 * 429, 503 ...) come back as a normal JSON envelope and are thrown as `ApiRequestError`.
 * Aborting `signal` closes the connection; the backend then cancels the upstream call.
 */
export async function* streamPost(
  path: string,
  body: unknown,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const headers = new Headers({ "Content-Type": "application/json", Accept: "text/event-stream" });
  const csrf = getCsrfToken();
  if (csrf) headers.set("X-CSRF-Token", csrf);

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    credentials: "include",
    signal,
  });

  const type = response.headers.get("content-type") ?? "";
  if (!response.ok || !type.startsWith("text/event-stream")) {
    let code = "REQUEST_FAILED";
    let message = "The request could not be completed.";
    try {
      const json = await response.json();
      if (json?.error?.code) code = String(json.error.code);
      if (json?.error?.message) message = String(json.error.message);
    } catch {
      /* not JSON: keep the generic message */
    }
    throw new ApiRequestError(code, message, response.status);
  }
  if (!response.body) throw new ApiRequestError("STREAM_UNAVAILABLE", "No response stream.", 200);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const raw of parser.push(decoder.decode(value, { stream: true }))) {
        const event = toStreamEvent(raw);
        if (event) yield event;
      }
    }
    for (const raw of parser.push(decoder.decode())) {
      const event = toStreamEvent(raw);
      if (event) yield event;
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
