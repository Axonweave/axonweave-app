import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import type { StreamEvent } from "./sse";
import { fromRecords, useChat } from "./use-chat";

const mocks = vi.hoisted(() => ({
  listMessages: vi.fn(),
  createConversation: vi.fn(),
  cancel: vi.fn(),
  streamPost: vi.fn(),
}));

vi.mock("@/lib/api/ai", () => ({
  aiApi: {
    listMessages: mocks.listMessages,
    createConversation: mocks.createConversation,
    cancel: mocks.cancel,
  },
}));
vi.mock("./stream-client", () => ({ streamPost: mocks.streamPost }));

const rec = (over: Record<string, unknown>) => ({
  id: "x",
  conversation_id: "c1",
  role: "user",
  content: "",
  status: "completed",
  sequence_number: 1,
  error_code: null,
  superseded_at: null,
  ...over,
});

/** An async generator that yields the given events, optionally waiting on a gate between them. */
function events(list: StreamEvent[], gate?: Promise<void>) {
  return async function* (_path: string, _body: unknown, signal: AbortSignal) {
    for (const e of list) {
      if (gate)
        await Promise.race([
          gate,
          new Promise((_r, rej) =>
            signal.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))),
          ),
        ]);
      yield e;
    }
  };
}

const started = (id = "a1"): StreamEvent => ({
  type: "started",
  messageId: id,
  userMessageId: "u1",
  conversationId: "c1",
  modelId: "m",
});

function setup(conversationId: string | null = "c1") {
  const onCreated = vi.fn();
  const onSettled = vi.fn();
  const hook = renderHook(() =>
    useChat({ conversationId, modelId: null, onConversationCreated: onCreated, onSettled }),
  );
  return { ...hook, onCreated, onSettled };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.listMessages.mockResolvedValue([]);
});

describe("fromRecords", () => {
  it("hides superseded answers and non-chat roles", () => {
    const items = fromRecords([
      rec({ id: "u", role: "user", content: "q" }),
      rec({ id: "old", role: "assistant", content: "old", superseded_at: "2026-01-01" }),
      rec({ id: "sys", role: "system", content: "prompt" }),
      rec({ id: "new", role: "assistant", content: "new" }),
    ] as never);
    expect(items.map((i) => i.id)).toEqual(["u", "new"]);
  });
});

describe("useChat", () => {
  it("loads history from the server for a conversation", async () => {
    mocks.listMessages.mockResolvedValue([
      rec({ id: "u", role: "user", content: "hi" }),
      rec({ id: "a", role: "assistant", content: "hello" }),
    ]);
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.items.map((i) => i.content)).toEqual(["hi", "hello"]);
  });

  it("reports a missing or foreign conversation as not found", async () => {
    mocks.listMessages.mockRejectedValue(new ApiRequestError("RESOURCE_NOT_FOUND", "no", 404));
    const { result } = setup("someone-elses");
    await waitFor(() => expect(result.current.phase).toBe("notfound"));
  });

  it("streams deltas in order, then replaces the draft with the stored messages", async () => {
    mocks.streamPost.mockImplementation(
      events([
        started(),
        { type: "delta", text: "Hel" },
        { type: "delta", text: "lo" },
        { type: "completed", messageId: "a1", finishReason: "stop" },
      ]),
    );
    const { result, onSettled } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    mocks.listMessages.mockResolvedValue([
      rec({ id: "u1", role: "user", content: "Hi" }),
      rec({ id: "a1", role: "assistant", content: "Hello", sequence_number: 2 }),
    ]);

    await act(async () => {
      await result.current.send("Hi");
    });

    expect(mocks.streamPost.mock.calls[0][0]).toBe("/ai/conversations/c1/messages");
    expect(mocks.streamPost.mock.calls[0][1]).toEqual({ content: "Hi", stream: true });
    expect(result.current.items.map((i) => [i.role, i.content, i.status])).toEqual([
      ["user", "Hi", "completed"],
      ["assistant", "Hello", "completed"],
    ]);
    expect(result.current.busy).toBe(false);
    expect(onSettled).toHaveBeenCalled();
    expect(result.current.announcement).toBe("Response complete.");
  });

  it("ignores a second send while one is running (duplicate protection)", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => (release = r));
    mocks.streamPost.mockImplementation(
      events([started(), { type: "completed", messageId: "a1", finishReason: "stop" }], gate),
    );
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    let first!: Promise<boolean>;
    let second!: boolean;
    await act(async () => {
      first = result.current.send("one");
      second = await result.current.send("two");
    });
    expect(second).toBe(false);
    expect(mocks.streamPost).toHaveBeenCalledTimes(1);
    await act(async () => {
      release();
      await first;
    });
  });

  it("Stop calls the cancel endpoint with the assistant id, then aborts the request", async () => {
    mocks.cancel.mockResolvedValue({});
    let signalSeen: AbortSignal | undefined;
    mocks.streamPost.mockImplementation(async function* (
      _p: string,
      _b: unknown,
      signal: AbortSignal,
    ) {
      signalSeen = signal;
      yield started("a9");
      yield { type: "delta", text: "partial" } as StreamEvent;
      await new Promise((_r, reject) =>
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
      );
    });
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    let sending!: Promise<boolean>;
    await act(async () => {
      sending = result.current.send("long question");
    });
    await waitFor(() => expect(result.current.items.some((i) => i.id === "a9")).toBe(true));
    mocks.listMessages.mockResolvedValue([
      rec({ id: "u1", role: "user", content: "long question" }),
      rec({ id: "a9", role: "assistant", content: "partial", status: "cancelled" }),
    ]);

    await act(async () => {
      await result.current.stop();
      await sending;
    });

    expect(mocks.cancel).toHaveBeenCalledWith("c1", "a9");
    expect(signalSeen?.aborted).toBe(true);
    expect(result.current.items.at(-1)).toMatchObject({ status: "cancelled", content: "partial" });
    expect(result.current.error).toBeNull(); // a user stop is not an error
    expect(result.current.busy).toBe(false);
    expect(result.current.announcement).toBe("Response stopped.");
  });

  it("keeps re-reading until the server has recorded a cancel after a disconnect", async () => {
    // Stop before the first token: only the connection is dropped, so the server may still list
    // the answer as pending for a moment. The view must not freeze on that stale state.
    mocks.cancel.mockResolvedValue({});
    mocks.streamPost.mockImplementation(async function* (
      _p: string,
      _b: unknown,
      signal: AbortSignal,
    ) {
      await new Promise((_r, reject) =>
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
      );
      yield started(); // never reached
    });
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    const user = rec({ id: "u1", role: "user", content: "q" });
    mocks.listMessages
      .mockResolvedValueOnce([
        user,
        rec({ id: "a1", role: "assistant", content: "", status: "pending" }),
      ])
      .mockResolvedValue([
        user,
        rec({ id: "a1", role: "assistant", content: "", status: "cancelled" }),
      ]);

    let sending!: Promise<boolean>;
    await act(async () => {
      sending = result.current.send("q");
    });
    await act(async () => {
      await result.current.stop();
      await sending;
    });

    expect(mocks.listMessages.mock.calls.length).toBeGreaterThanOrEqual(3); // initial + stale + settled
    expect(result.current.items.at(-1)).toMatchObject({ status: "cancelled" });
    expect(result.current.busy).toBe(false);
  });

  it("returns false and removes the optimistic messages when the server refuses the request", async () => {
    mocks.streamPost.mockImplementation(async function* () {
      throw new ApiRequestError("AI_QUOTA_EXCEEDED", "Daily limit reached.", 429);
    });
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    let accepted = true;
    await act(async () => {
      accepted = await result.current.send("hello");
    });
    expect(accepted).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.error).toMatchObject({
      code: "AI_QUOTA_EXCEEDED",
      message: "Daily limit reached.",
    });
    expect(result.current.busy).toBe(false);
  });

  it("keeps partial text and shows the reason on message.failed", async () => {
    mocks.streamPost.mockImplementation(
      events([
        started(),
        { type: "delta", text: "Part" },
        {
          type: "failed",
          messageId: "a1",
          code: "LLM_UNAVAILABLE",
          message: "Service unavailable.",
        },
      ]),
    );
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    mocks.listMessages.mockResolvedValue([
      rec({ id: "u1", role: "user", content: "q" }),
      rec({
        id: "a1",
        role: "assistant",
        content: "Part",
        status: "failed",
        error_code: "LLM_UNAVAILABLE",
      }),
    ]);
    await act(async () => {
      expect(await result.current.send("q")).toBe(true); // the turn is stored: do not restore the text
    });
    expect(result.current.items.at(-1)).toMatchObject({ status: "failed", content: "Part" });
    expect(result.current.error?.message).toBe("Service unavailable.");
  });

  it("treats a dropped connection as a retryable error, not as success", async () => {
    mocks.streamPost.mockImplementation(async function* () {
      yield started();
      yield { type: "delta", text: "ab" } as StreamEvent;
      throw new TypeError("network error");
    });
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(async () => {
      await result.current.send("q");
    });
    expect(result.current.error?.code).toBe("CONNECTION_LOST");
    expect(result.current.busy).toBe(false);
  });

  it("creates a conversation on first send and tells the caller", async () => {
    mocks.createConversation.mockResolvedValue({ id: "new-id", title: null });
    mocks.streamPost.mockImplementation(
      events([started(), { type: "completed", messageId: "a1", finishReason: "stop" }]),
    );
    const { result, onCreated } = setup(null);
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(async () => {
      await result.current.send("first");
    });
    expect(onCreated).toHaveBeenCalledWith({ id: "new-id", title: null });
    expect(mocks.streamPost.mock.calls[0][0]).toBe("/ai/conversations/new-id/messages");
  });

  it("regenerate streams from the regenerate endpoint and swaps the old answer", async () => {
    mocks.listMessages.mockResolvedValue([
      rec({ id: "u1", role: "user", content: "q" }),
      rec({ id: "a1", role: "assistant", content: "old" }),
    ]);
    const { result } = setup("c1");
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    mocks.streamPost.mockImplementation(
      events([
        started("a2"),
        { type: "delta", text: "new" },
        { type: "completed", messageId: "a2", finishReason: "stop" },
      ]),
    );
    mocks.listMessages.mockResolvedValue([
      rec({ id: "u1", role: "user", content: "q" }),
      rec({ id: "a1", role: "assistant", content: "old", superseded_at: "2026-01-01" }),
      rec({ id: "a2", role: "assistant", content: "new", sequence_number: 3 }),
    ]);
    await act(async () => {
      await result.current.regenerate("a1");
    });
    expect(mocks.streamPost.mock.calls[0][0]).toBe("/ai/conversations/c1/messages/a1/regenerate");
    expect(result.current.items.map((i) => i.content)).toEqual(["q", "new"]);
  });
});
