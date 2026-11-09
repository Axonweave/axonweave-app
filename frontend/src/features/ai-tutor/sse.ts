/**
 * Server-sent events over a fetch body (D-44). `EventSource` cannot POST, so the response is read
 * with a ReadableStream and parsed here. Pure functions: no I/O, fully unit-tested.
 */

export interface RawSseEvent {
  event: string;
  data: string;
}

/**
 * Incremental parser: feed it text as it arrives (chunks may split a line or a frame anywhere) and
 * it returns the events completed so far. Comment lines (`: ping` heartbeats) are ignored.
 */
export class SseParser {
  private buffer = "";
  private event = "message";
  private data: string[] = [];

  push(chunk: string): RawSseEvent[] {
    this.buffer += chunk;
    const out: RawSseEvent[] = [];
    let index = this.nextLineBreak();
    while (index !== -1) {
      const crlf = this.buffer[index] === "\r" && this.buffer[index + 1] === "\n";
      const line = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + (crlf ? 2 : 1));
      this.line(line, out);
      index = this.nextLineBreak();
    }
    return out;
  }

  /** Index of the next line terminator, or -1 if the buffer holds only a partial line. */
  private nextLineBreak(): number {
    const lf = this.buffer.indexOf("\n");
    const cr = this.buffer.indexOf("\r");
    if (cr === -1) return lf;
    // A lone trailing "\r" may be the first half of "\r\n": wait for more input.
    if (cr === this.buffer.length - 1 && (lf === -1 || lf > cr)) return lf;
    return lf === -1 ? cr : Math.min(lf, cr);
  }

  private line(line: string, out: RawSseEvent[]): void {
    if (line === "") {
      if (this.data.length > 0) out.push({ event: this.event, data: this.data.join("\n") });
      this.event = "message";
      this.data = [];
      return;
    }
    if (line.startsWith(":")) return; // comment / heartbeat
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
  }
}

// ── typed events (spec 12.3) ────────────────────────────────────────────────

/** A source shown with an answer. `id` exists once the server has stored the citation. */
export interface CitationView {
  id: string | null;
  rank: number;
  chunkId?: string | null;
  documentId: string | null;
  documentName: string;
  page: number | null;
  slide: number | null;
  heading: string | null;
  snippet: string | null;
  available: boolean;
}

export type StreamEvent =
  | {
      type: "started";
      messageId: string;
      userMessageId: string;
      conversationId: string;
      modelId: string;
    }
  | { type: "delta"; text: string }
  | { type: "usage"; inputTokens: number | null; outputTokens: number | null; source: string }
  | { type: "citations"; messageId: string; citations: CitationView[] }
  | {
      type: "completed";
      messageId: string;
      finishReason: string;
      /** Validated final text and the citations actually used; the client replaces its draft. */
      content?: string | null;
      citations?: CitationView[] | null;
    }
  | { type: "failed"; messageId: string; code: string; message: string }
  | { type: "cancelled"; messageId: string };

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

function toCitations(v: unknown): CitationView[] | null {
  if (!Array.isArray(v)) return null;
  const out: CitationView[] = [];
  for (const c of v) {
    if (!isRecord(c)) continue;
    const rank = num(c.rank);
    const name = str(c.document_name);
    if (rank === null || name === null) continue;
    out.push({
      id: str(c.id),
      rank,
      chunkId: str(c.chunk_id),
      documentId: str(c.document_id),
      documentName: name,
      page: num(c.page_number),
      slide: num(c.slide_number),
      heading: str(c.section_heading),
      snippet: str(c.snippet),
      available: c.available !== false,
    });
  }
  return out;
}

/** Validates one event. Unknown names and malformed payloads return null: ignored, never trusted. */
export function toStreamEvent(raw: RawSseEvent): StreamEvent | null {
  let json: unknown;
  try {
    json = JSON.parse(raw.data);
  } catch {
    return null;
  }
  if (!isRecord(json)) return null;
  switch (raw.event) {
    case "message.started": {
      const messageId = str(json.message_id);
      if (!messageId) return null;
      return {
        type: "started",
        messageId,
        userMessageId: str(json.user_message_id) ?? "",
        conversationId: str(json.conversation_id) ?? "",
        modelId: str(json.model_id) ?? "",
      };
    }
    case "message.delta": {
      const text = str(json.delta);
      return text === null ? null : { type: "delta", text };
    }
    case "usage.updated":
      return {
        type: "usage",
        inputTokens: num(json.input_tokens),
        outputTokens: num(json.output_tokens),
        source: str(json.usage_source) ?? "unavailable",
      };
    case "message.completed": {
      const messageId = str(json.message_id);
      return messageId
        ? {
            type: "completed",
            messageId,
            finishReason: str(json.finish_reason) ?? "stop",
            content: str(json.content),
            citations: toCitations(json.citations),
          }
        : null;
    }
    case "message.citations": {
      const messageId = str(json.message_id);
      const citations = toCitations(json.citations);
      return messageId && citations ? { type: "citations", messageId, citations } : null;
    }
    case "message.failed": {
      const messageId = str(json.message_id);
      if (!messageId) return null;
      return {
        type: "failed",
        messageId,
        code: str(json.code) ?? "LLM_UNAVAILABLE",
        message: str(json.message) ?? "The answer could not be completed.",
      };
    }
    case "message.cancelled": {
      const messageId = str(json.message_id);
      return messageId ? { type: "cancelled", messageId } : null;
    }
    default:
      return null;
  }
}
