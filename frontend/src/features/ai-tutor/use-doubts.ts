"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError } from "@/lib/api/client";
import type { components } from "@/types/api.generated";
import type { CitationView } from "./sse";
import { streamPost } from "./stream-client";

export type QuickAction = NonNullable<components["schemas"]["DoubtRequest"]["quick_action"]>;

export const QUICK_ACTIONS: { id: QuickAction; label: string }[] = [
  { id: "simpler", label: "Simpler" },
  { id: "analogy", label: "Analogy" },
  { id: "example", label: "Example" },
  { id: "step_by_step", label: "Step by step" },
];

export interface DoubtTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "done" | "failed";
  citations: CitationView[];
}

/** A doubt about a selected part of one answer. Lives in component state only. */
export interface Doubt {
  id: string;
  messageId: string;
  text: string;
  /** Character offsets of the selection inside the answer body, used to find it again. */
  start: number;
  end: number;
  turns: DoubtTurn[];
  error: string | null;
}

interface State {
  conversationId: string | null;
  doubts: Doubt[];
  activeId: string | null;
}

let counter = 0;
const nextId = (p: string) => `${p}-${(counter += 1)}`;

/** Doubt threads. They never touch the main chat: the server stores nothing for them. */
export function useDoubts(conversationId: string | null) {
  const [raw, setRaw] = useState<State>({ conversationId, doubts: [], activeId: null });
  // A different conversation starts with a clean slate.
  const state: State =
    raw.conversationId === conversationId ? raw : { conversationId, doubts: [], activeId: null };
  const abortRef = useRef<AbortController | null>(null);
  const [streaming, setStreaming] = useState(false);

  const update = useCallback(
    (fn: (s: State) => State) =>
      setRaw((prev) =>
        fn(
          prev.conversationId === conversationId
            ? prev
            : { conversationId, doubts: [], activeId: null },
        ),
      ),
    [conversationId],
  );

  const patchDoubt = useCallback(
    (id: string, fn: (d: Doubt) => Doubt) =>
      update((s) => ({ ...s, doubts: s.doubts.map((d) => (d.id === id ? fn(d) : d)) })),
    [update],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  useEffect(() => stop, [stop]);

  const open = useCallback(
    (sel: { messageId: string; text: string; start: number; end: number }) => {
      const id = nextId("doubt");
      update((s) => ({
        ...s,
        activeId: id,
        doubts: [...s.doubts, { id, ...sel, turns: [], error: null }],
      }));
    },
    [update],
  );

  const reopen = useCallback((id: string) => update((s) => ({ ...s, activeId: id })), [update]);

  /** Closes the popup. A doubt that was never asked leaves no trace. */
  const close = useCallback(() => {
    stop();
    update((s) => ({
      ...s,
      activeId: null,
      doubts: s.doubts
        .map((d) =>
          d.id === s.activeId
            ? {
                ...d,
                turns: d.turns.filter((t) => !(t.role === "assistant" && t.status === "streaming")),
              }
            : d,
        )
        .filter((d) => d.turns.length > 0),
    }));
  }, [stop, update]);

  const ask = useCallback(
    async (request: { question?: string; quick?: QuickAction }) => {
      const doubt = state.doubts.find((d) => d.id === state.activeId);
      if (!doubt || abortRef.current || !conversationId) return;
      const question = request.question?.trim() || undefined;
      const label = QUICK_ACTIONS.find((a) => a.id === request.quick)?.label ?? "";
      const userText = question ?? label;
      if (!userText) return;
      const history = doubt.turns
        .filter((t) => t.status === "done")
        .map((t) => ({ role: t.role, content: t.content }));
      const replyId = nextId("turn");
      patchDoubt(doubt.id, (d) => ({
        ...d,
        error: null,
        turns: [
          ...d.turns,
          { id: nextId("turn"), role: "user", content: userText, status: "done", citations: [] },
          { id: replyId, role: "assistant", content: "", status: "streaming", citations: [] },
        ],
      }));
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      const patchReply = (fn: (t: DoubtTurn) => DoubtTurn) =>
        patchDoubt(doubt.id, (d) => ({
          ...d,
          turns: d.turns.map((t) => (t.id === replyId ? fn(t) : t)),
        }));
      const fail = (message: string) => {
        patchReply((t) => ({ ...t, status: "failed" }));
        patchDoubt(doubt.id, (d) => ({ ...d, error: message }));
      };
      const body: components["schemas"]["DoubtRequest"] = {
        message_id: doubt.messageId,
        selected_text: doubt.text,
        history,
        ...(question ? { question } : { quick_action: request.quick }),
      };
      let finished = false;
      try {
        for await (const ev of streamPost(
          `/ai/conversations/${encodeURIComponent(conversationId)}/doubt`,
          body,
          controller.signal,
        )) {
          if (ev.type === "delta") {
            patchReply((t) => ({ ...t, content: t.content + ev.text }));
          } else if (ev.type === "citations") {
            patchReply((t) => ({ ...t, citations: ev.citations }));
          } else if (ev.type === "completed") {
            finished = true;
            patchReply((t) => ({
              ...t,
              status: "done",
              content: typeof ev.content === "string" ? ev.content : t.content,
              citations: ev.citations ?? t.citations,
            }));
          } else if (ev.type === "failed") {
            finished = true;
            fail(ev.message);
          }
        }
        if (!finished && !controller.signal.aborted) fail("The answer did not finish.");
      } catch (e) {
        if (!controller.signal.aborted) {
          fail(
            e instanceof ApiRequestError ? e.message : "The connection was lost. Please try again.",
          );
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setStreaming(false);
      }
    },
    [state.doubts, state.activeId, conversationId, patchDoubt],
  );

  const active = state.doubts.find((d) => d.id === state.activeId) ?? null;
  return { doubts: state.doubts, active, streaming, open, reopen, close, ask };
}
