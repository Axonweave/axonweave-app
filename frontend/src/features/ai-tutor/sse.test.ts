import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import { SseParser, toStreamEvent, type RawSseEvent } from "./sse";
import { streamPost } from "./stream-client";

const frame = (event: string, data: unknown) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

function parseAll(text: string, chunk = text.length): RawSseEvent[] {
  const parser = new SseParser();
  const out: RawSseEvent[] = [];
  for (let i = 0; i < text.length; i += chunk) out.push(...parser.push(text.slice(i, i + chunk)));
  return out;
}

describe("SseParser", () => {
  const stream =
    frame("message.started", { message_id: "m1" }) +
    ": ping\n\n" +
    frame("message.delta", { delta: "Hello" }) +
    frame("message.delta", { delta: " world" }) +
    frame("message.completed", { message_id: "m1" });

  it("parses whole frames and ignores heartbeat comments", () => {
    const events = parseAll(stream);
    expect(events.map((e) => e.event)).toEqual([
      "message.started",
      "message.delta",
      "message.delta",
      "message.completed",
    ]);
  });

  it.each([1, 2, 3, 7, 13])("gives identical results when split into %i-char chunks", (n) => {
    expect(parseAll(stream, n)).toEqual(parseAll(stream));
  });

  it("handles CRLF line endings, including a CR/LF pair split across chunks", () => {
    const crlf = 'event: message.delta\r\ndata: {"delta":"a"}\r\n\r\n';
    expect(parseAll(crlf)).toEqual([{ event: "message.delta", data: '{"delta":"a"}' }]);
    expect(parseAll(crlf, 1)).toEqual(parseAll(crlf));
  });

  it("joins multi-line data with newlines and defaults the event name", () => {
    expect(parseAll("data: a\ndata: b\n\n")).toEqual([{ event: "message", data: "a\nb" }]);
  });

  it("does not emit an incomplete frame", () => {
    const parser = new SseParser();
    expect(parser.push('event: message.delta\ndata: {"delta":"x"}\n')).toEqual([]);
    expect(parser.push("\n")).toHaveLength(1);
  });

  it("keeps newlines inside model text intact because the server JSON-escapes them", () => {
    const text = "line1\n\nline2\r\nevent: evil";
    const [event] = parseAll(frame("message.delta", { delta: text }));
    expect(toStreamEvent(event)).toEqual({ type: "delta", text });
  });
});

describe("toStreamEvent", () => {
  const ev = (event: string, data: unknown) => ({ event, data: JSON.stringify(data) });

  it("maps every event type", () => {
    expect(
      toStreamEvent(
        ev("message.started", { message_id: "a", user_message_id: "u", model_id: "m" }),
      ),
    ).toMatchObject({ type: "started", messageId: "a", userMessageId: "u", modelId: "m" });
    expect(
      toStreamEvent(
        ev("usage.updated", { input_tokens: 3, output_tokens: 4, usage_source: "estimated" }),
      ),
    ).toEqual({
      type: "usage",
      inputTokens: 3,
      outputTokens: 4,
      source: "estimated",
    });
    expect(
      toStreamEvent(ev("message.completed", { message_id: "a", finish_reason: "stop" })),
    ).toEqual({
      type: "completed",
      messageId: "a",
      finishReason: "stop",
      content: null,
      citations: null,
    });
    expect(
      toStreamEvent(
        ev("message.failed", { message_id: "a", code: "LLM_TIMEOUT", message: "Slow" }),
      ),
    ).toEqual({
      type: "failed",
      messageId: "a",
      code: "LLM_TIMEOUT",
      message: "Slow",
    });
    expect(toStreamEvent(ev("message.cancelled", { message_id: "a" }))).toEqual({
      type: "cancelled",
      messageId: "a",
    });
  });

  it.each([
    ["bad JSON", { event: "message.delta", data: "{not json" }],
    ["JSON that is not an object", { event: "message.delta", data: '"text"' }],
    ["a missing field", ev("message.delta", { nope: 1 })],
    ["a wrong type", ev("message.delta", { delta: 5 })],
    ["an unknown event", ev("message.exploded", { delta: "x" })],
    ["started without an id", ev("message.started", {})],
  ])("ignores %s", (_name, raw) => {
    expect(toStreamEvent(raw)).toBeNull();
  });
});

describe("streamPost", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch(response: Response) {
    const fn = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  function sseResponse(chunks: string[]): Response {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const c of chunks) controller.enqueue(encoder.encode(c));
        controller.close();
      },
    });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  }

  async function collect(gen: AsyncGenerator<unknown>) {
    const out: unknown[] = [];
    for await (const e of gen) out.push(e);
    return out;
  }

  it("sends credentials, JSON body and the CSRF header, and yields typed events", async () => {
    Object.defineProperty(document, "cookie", { value: "csrf_token=tok123", configurable: true });
    const fetchMock = stubFetch(
      sseResponse([
        frame("message.started", { message_id: "m" }).slice(0, 20),
        frame("message.started", { message_id: "m" }).slice(20) +
          frame("message.delta", { delta: "Hi" }),
        frame("message.completed", { message_id: "m" }),
      ]),
    );
    const events = await collect(
      streamPost(
        "/ai/conversations/c/messages",
        { content: "q", stream: true },
        new AbortController().signal,
      ),
    );
    expect(events.map((e) => (e as { type: string }).type)).toEqual([
      "started",
      "delta",
      "completed",
    ]);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/ai/conversations/c/messages");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("tok123");
    expect(JSON.parse(init.body)).toEqual({ content: "q", stream: true });
  });

  it("turns a pre-stream JSON error into an ApiRequestError with the server code", async () => {
    stubFetch(
      new Response(
        JSON.stringify({ success: false, error: { code: "AI_QUOTA_EXCEEDED", message: "Limit" } }),
        {
          status: 429,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    const gen = streamPost("/x", {}, new AbortController().signal);
    await expect(gen.next()).rejects.toMatchObject({ code: "AI_QUOTA_EXCEEDED", status: 429 });
    stubFetch(new Response("<html>gateway</html>", { status: 502 }));
    await expect(streamPost("/x", {}, new AbortController().signal).next()).rejects.toBeInstanceOf(
      ApiRequestError,
    );
  });

  it("rejects a 200 that is not an event stream instead of misreading it", async () => {
    stubFetch(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    await expect(streamPost("/x", {}, new AbortController().signal).next()).rejects.toBeInstanceOf(
      ApiRequestError,
    );
  });
});
