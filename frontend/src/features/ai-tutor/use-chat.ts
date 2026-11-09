"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  aiApi,
  type AnswerMode,
  type ChatMessageRecord,
  type CitationRecord,
  type Conversation,
  type ConversationScope,
} from "@/lib/api/ai";
import { ApiRequestError } from "@/lib/api/client";
import type { CitationView, StreamEvent } from "./sse";
import { streamPost } from "./stream-client";

export type ItemStatus = "pending" | "streaming" | "completed" | "failed" | "cancelled";

export interface ChatItem {
  /** Stable React key: survives the swap from the local draft to the server record. */
  key: string;
  /** Server message id, once known. */
  id: string | null;
  role: "user" | "assistant";
  content: string;
  status: ItemStatus;
  errorCode: string | null;
  /** Sources of a document-grounded answer (empty for general answers). */
  citations: CitationView[];
}

export interface ChatError {
  code: string;
  message: string;
  /** Pre-stream failures give the text back to the input; later ones are retried via regenerate. */
  retryable: boolean;
}

export type LoadPhase = "idle" | "loading" | "ready" | "error" | "notfound";

/** After a stream ends, re-read until the server no longer reports the answer as active. */
const SETTLE_ATTEMPTS = 12;
const SETTLE_DELAY_MS = 300;

let counter = 0;
const nextKey = () => `local-${(counter += 1)}`;

/** Server rows -> view items. Superseded answers (regenerated) and system/tool rows are hidden. */
export function toCitationView(c: CitationRecord): CitationView {
  return {
    id: c.id,
    rank: c.rank,
    documentId: c.document_id,
    documentName: c.document_name,
    page: c.page_number,
    slide: c.slide_number,
    heading: c.section_heading,
    snippet: c.snippet,
    available: c.available,
  };
}

export function fromRecords(
  records: ChatMessageRecord[],
  citations: Record<string, CitationView[]> = {},
): ChatItem[] {
  return records
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.superseded_at === null)
    .map((m) => ({
      key: m.id,
      id: m.id,
      role: m.role as "user" | "assistant",
      content: m.content,
      status: m.status,
      errorCode: m.error_code,
      citations: citations[m.id] ?? [],
    }));
}

const FRIENDLY: Record<string, string> = {
  AI_GENERATION_IN_PROGRESS: "A response is already being generated in this conversation.",
  LLM_NOT_CONFIGURED: "AI is not configured on this server.",
  CONNECTION_LOST: "The connection was lost before the answer finished.",
};

function describe(e: unknown): ChatError {
  if (e instanceof ApiRequestError) {
    return { code: e.code, message: FRIENDLY[e.code] ?? e.message, retryable: true };
  }
  return { code: "CONNECTION_LOST", message: FRIENDLY.CONNECTION_LOST, retryable: true };
}

interface Options {
  conversationId: string | null;
  modelId: string | null;
  /** Used only when this send creates the conversation: the scope is then stored server-side. */
  scope?: ConversationScope | null;
  /** Sent with each message of a scoped conversation; ignored by the server otherwise. */
  answerMode?: AnswerMode | null;
  onConversationCreated: (conversation: Conversation) => void;
  /** Called when a send/regenerate finishes (title, ordering and usage may have changed). */
  onSettled: () => void;
}

export function useChat({
  conversationId,
  modelId,
  scope = null,
  answerMode = null,
  onConversationCreated,
  onSettled,
}: Options) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [phase, setPhase] = useState<LoadPhase>("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ChatError | null>(null);
  const [announcement, setAnnouncement] = useState("");

  const idRef = useRef<string | null>(conversationId);
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const assistantIdRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);
  const lastTextRef = useRef("");
  const itemsRef = useRef<ChatItem[]>([]);
  const epochRef = useRef(0);
  const skipLoadFor = useRef<string | null>(null);
  const callbacks = useRef({ onConversationCreated, onSettled });

  useEffect(() => {
    callbacks.current = { onConversationCreated, onSettled };
  });
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  /**
   * Replace the view with what the server has stored. Resolves to true while the server still
   * lists an answer as pending/streaming (e.g. right after a disconnect, before it has recorded
   * the cancellation), so callers can look again instead of showing a stale state.
   */
  const load = useCallback(async (id: string, epoch: number): Promise<boolean> => {
    try {
      const records = await aiApi.listMessages(id);
      if (epochRef.current !== epoch) return false;
      // Citations of document-grounded answers are stored server-side; a failure here must not
      // hide the conversation, so it only costs the source list.
      const grounded = records.filter(
        (m) => m.role === "assistant" && m.status === "completed" && m.answer_mode,
      );
      const cites: Record<string, CitationView[]> = {};
      await Promise.all(
        grounded.map(async (m) => {
          try {
            cites[m.id] = (await aiApi.citations(m.id)).map(toCitationView);
          } catch {
            /* keep the answer without its source list */
          }
        }),
      );
      if (epochRef.current !== epoch) return false;
      setItems(fromRecords(records, cites));
      setPhase("ready");
      return records.some(
        (m) =>
          m.role === "assistant" &&
          m.superseded_at === null &&
          (m.status === "pending" || m.status === "streaming"),
      );
    } catch (e) {
      if (epochRef.current !== epoch) return false;
      setPhase(e instanceof ApiRequestError && e.status === 404 ? "notfound" : "error");
      return false;
    }
  }, []);

  // Switching conversation: stop what is running, then load the new one from the server.
  // Resetting state when the prop changes is the point of this effect.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (skipLoadFor.current !== null && skipLoadFor.current === conversationId) {
      // We just created this conversation and are already streaming its first turn: the route
      // change must not abort or reset it.
      skipLoadFor.current = null;
      return;
    }
    epochRef.current += 1;
    const epoch = epochRef.current;
    abortRef.current?.abort();
    busyRef.current = false;
    setBusy(false);
    setError(null);
    setAnnouncement("");
    idRef.current = conversationId;

    if (conversationId === null) {
      setItems([]);
      setPhase("ready");
    } else {
      setItems([]);
      setPhase("loading");
      void load(conversationId, epoch);
    }
  }, [conversationId, load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => () => abortRef.current?.abort(), []);

  /**
   * Runs one streamed generation and keeps `items` in step with it.
   * Resolves to false only when the server refused the request before storing anything, so the
   * caller may put the user's text back in the input. Later failures return true: the turn exists.
   */
  const consume = useCallback(
    async (
      id: string,
      path: string,
      body: unknown,
      draftKey: string,
      rollback: () => void,
    ): Promise<boolean> => {
      const epoch = epochRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      assistantIdRef.current = null;
      stoppedRef.current = false;
      const alive = () => epochRef.current === epoch;

      let buffer = "";
      let timer: ReturnType<typeof setTimeout> | null = null;
      const flush = () => {
        timer = null;
        if (!buffer || !alive()) return;
        const text = buffer;
        buffer = "";
        setItems((prev) =>
          prev.map((i) =>
            i.key === draftKey ? { ...i, content: i.content + text, status: "streaming" } : i,
          ),
        );
      };

      let terminal: StreamEvent["type"] | null = null;
      let ok = true;
      setAnnouncement("The assistant is responding.");
      try {
        for await (const ev of streamPost(path, body, controller.signal)) {
          if (!alive()) return true;
          if (ev.type === "started") {
            assistantIdRef.current = ev.messageId;
            setItems((prev) =>
              prev.map((i) => (i.key === draftKey ? { ...i, id: ev.messageId } : i)),
            );
          } else if (ev.type === "delta") {
            buffer += ev.text;
            if (timer === null) timer = setTimeout(flush, 40);
          } else if (ev.type === "citations") {
            setItems((prev) =>
              prev.map((i) => (i.key === draftKey ? { ...i, citations: ev.citations } : i)),
            );
          } else if (ev.type === "completed" || ev.type === "cancelled") {
            terminal = ev.type;
            if (ev.type === "completed" && typeof ev.content === "string") {
              // The server validated the text (invalid [n] markers removed): replace the draft.
              flush();
              const finalText = ev.content;
              const finalCites = ev.citations ?? null;
              setItems((prev) =>
                prev.map((i) =>
                  i.key === draftKey
                    ? { ...i, content: finalText, citations: finalCites ?? i.citations }
                    : i,
                ),
              );
            }
          } else if (ev.type === "failed") {
            terminal = "failed";
            setError({ code: ev.code, message: ev.message, retryable: true });
          }
        }
        if (terminal === null && !stoppedRef.current) {
          setError(describe(null)); // stream ended without a final event; the turn is stored
        }
      } catch (e) {
        if (!alive()) return true;
        if (stoppedRef.current) {
          terminal = "cancelled";
        } else if (e instanceof ApiRequestError) {
          rollback(); // refused before anything was stored: nothing to show but the reason
          setError(describe(e));
          ok = false;
          terminal = "failed";
        } else {
          setError(describe(e)); // connection lost mid-stream; the turn is stored, so ok stays true
        }
      } finally {
        if (timer !== null) clearTimeout(timer);
        flush();
      }

      if (!alive()) return ok;
      setAnnouncement(
        terminal === "completed"
          ? "Response complete."
          : terminal === "cancelled"
            ? "Response stopped."
            : "The response did not finish.",
      );
      // The server is the source of truth: replace the local draft with what was stored.
      let active = await load(id, epoch);
      for (let attempt = 0; active && attempt < SETTLE_ATTEMPTS && alive(); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, SETTLE_DELAY_MS));
        if (alive()) active = await load(id, epoch);
      }
      if (alive()) {
        busyRef.current = false;
        setBusy(false);
        callbacks.current.onSettled();
      }
      return ok;
    },
    [load],
  );

  const send = useCallback(
    async (text: string): Promise<boolean> => {
      const content = text.trim();
      if (!content || busyRef.current) return false; // duplicate-send guard (synchronous)
      busyRef.current = true;
      setBusy(true);
      setError(null);
      lastTextRef.current = content;

      let id = idRef.current;
      if (id === null) {
        try {
          const conversation = await aiApi.createConversation(modelId, scope);
          id = conversation.id;
          idRef.current = id;
          skipLoadFor.current = id;
          callbacks.current.onConversationCreated(conversation);
        } catch (e) {
          busyRef.current = false;
          setBusy(false);
          setError(describe(e));
          return false;
        }
      }

      const userKey = nextKey();
      const draftKey = nextKey();
      setItems((prev) => [
        ...prev,
        {
          key: userKey,
          id: null,
          role: "user",
          content,
          status: "completed",
          errorCode: null,
          citations: [],
        },
        {
          key: draftKey,
          id: null,
          role: "assistant",
          content: "",
          status: "pending",
          errorCode: null,
          citations: [],
        },
      ]);
      const ok = await consume(
        id,
        `/ai/conversations/${encodeURIComponent(id)}/messages`,
        {
          content,
          stream: true,
          ...(modelId ? { model_id: modelId } : {}),
          ...(answerMode ? { answer_mode: answerMode } : {}),
        },
        draftKey,
        () => setItems((prev) => prev.filter((i) => i.key !== userKey && i.key !== draftKey)),
      );
      return ok;
    },
    [consume, modelId, scope, answerMode],
  );

  const regenerate = useCallback(
    async (messageId: string): Promise<void> => {
      const id = idRef.current;
      if (!id || busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setError(null);
      const draftKey = nextKey();
      setItems((prev) =>
        prev.map((i) =>
          i.id === messageId
            ? {
                ...i,
                key: draftKey,
                id: null,
                content: "",
                status: "pending",
                errorCode: null,
                citations: [],
              }
            : i,
        ),
      );
      await consume(
        id,
        `/ai/conversations/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/regenerate`,
        { stream: true, ...(modelId ? { model_id: modelId } : {}) },
        draftKey,
        () => void load(id, epochRef.current),
      );
    },
    [consume, load, modelId],
  );

  const stop = useCallback(async () => {
    const id = idRef.current;
    const messageId = assistantIdRef.current;
    stoppedRef.current = true;
    if (id && messageId) {
      try {
        await aiApi.cancel(id, messageId); // the server stops the provider call and stores usage
      } catch {
        /* the abort below still disconnects, which the server also treats as a cancel */
      }
    }
    abortRef.current?.abort();
  }, []);

  /** Retry after an error: regenerate an unfinished answer, or resend text that was never stored. */
  const retry = useCallback(async (): Promise<string | null> => {
    const lastAssistant = [...itemsRef.current].reverse().find((i) => i.role === "assistant");
    if (lastAssistant?.id && lastAssistant.status !== "completed") {
      await regenerate(lastAssistant.id);
      return null;
    }
    const text = lastTextRef.current;
    if (text) await send(text);
    return null;
  }, [regenerate, send]);

  const reload = useCallback(() => {
    const id = idRef.current;
    if (!id) return;
    setPhase("loading");
    void load(id, epochRef.current);
  }, [load]);

  return { items, phase, busy, error, announcement, send, stop, regenerate, retry, reload };
}
