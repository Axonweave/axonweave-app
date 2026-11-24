"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  ArrowDown,
  ArrowLeft,
  BarChart3,
  Crosshair,
  Menu,
  MessageSquarePlus,
  Pencil,
  Trash2,
} from "lucide-react";
import {
  SCOPE_LABELS,
  contextFromQuery,
  contextQuery,
  environmentHref,
  toConversationScope,
} from "@/lib/learning-context";
import { useContextLabel } from "@/features/learning-spaces/use-context-label";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { useToast } from "@/hooks/use-toast";
import { aiApi, type AnswerMode, type Conversation, type ConversationScope } from "@/lib/api/ai";
import { RowActions } from "@/features/academic/row-actions";
import { ChatInput } from "./chat-input";
import { DoubtDialog } from "./doubt-dialog";
import { MessageView, type Rating } from "./message-view";
import { buildQuoted } from "./quote";
import { SelectionToolbar } from "./selection-toolbar";
import { useDoubts } from "./use-doubts";
import { useTutor } from "./tutor-context";
import { useChat } from "./use-chat";
import { ModePicker, ScopePicker } from "./scope-bar";
import { Welcome } from "./welcome";

const NEAR_BOTTOM_PX = 80;

export function ChatPanel({ conversationId }: { conversationId: string | null }) {
  const router = useRouter();
  const { toast } = useToast();
  const tutor = useTutor();
  const { status, models, modelId, setModelId, conversations } = tutor;

  // Learning context handed over by a subject, folder or chapter ("Open in AI Tutor"). It preselects
  // what a new conversation reads; the learner can still change it before the first message.
  const params = useSearchParams();
  const contextKey = params.toString();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const presetCtx = useMemo(() => contextFromQuery(params), [contextKey]);
  const presetLabel = useContextLabel(presetCtx);
  const ctxSuffix = presetCtx ? `?${contextQuery(presetCtx)}` : "";

  // Document scope: chosen before the first message, then fixed on the conversation (server-side).
  const [scope, setScope] = useState<ConversationScope | null>(
    presetCtx ? toConversationScope(presetCtx) : null,
  );
  const [pickScope, setPickScope] = useState(false);
  const [mode, setMode] = useState<AnswerMode>("document_only");
  const [lookupScope, setLookupScope] = useState<string>("general");

  useEffect(() => {
    // a different context was handed over while the tutor stayed mounted
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setScope(presetCtx ? toConversationScope(presetCtx) : null);
    setPickScope(false);
  }, [presetCtx]);

  // A handed-over context that does not resolve (deleted, or not this user's) is dropped, so the
  // learner falls back to the normal picker instead of a conversation the server would refuse.
  const presetMissing = !!presetCtx && !presetLabel.loading && presetLabel.data === null;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (presetMissing) setScope(null);
  }, [presetMissing]);

  const chat = useChat({
    conversationId,
    modelId,
    scope: conversationId ? null : scope,
    answerMode: (conversationId ? lookupScope !== "general" : scope !== null) ? mode : null,
    onConversationCreated: (c) => {
      conversations.prepend(c);
      router.replace(`/ai-tutor/${c.id}${ctxSuffix}`);
    },
    onSettled: () => void conversations.reload(),
  });

  const [draft, setDraft] = useState(() =>
    (params.get("q") ?? "").slice(0, status.max_input_chars),
  );
  const [quote, setQuote] = useState<string | null>(null);
  const doubts = useDoubts(conversationId);
  const [ratings, setRatings] = useState<Record<string, Rating>>({});
  const [lookup, setLookup] = useState<Conversation | null>(null);

  // Title: from the loaded list, else fetched once (deep link to an older conversation).
  const known = conversations.items.find((c) => c.id === conversationId) ?? null;
  const current = known ?? (lookup?.id === conversationId ? lookup : null);
  const scopeType = current?.scope_type ?? (conversationId ? "general" : null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLookupScope(scopeType ?? "general");
  }, [scopeType]);
  useEffect(() => {
    if (!conversationId || known) return;
    let live = true;
    aiApi
      .getConversation(conversationId)
      .then((c) => live && setLookup(c))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [conversationId, known]);

  // ── scrolling that never fights the reader ────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    stick.current = near;
    setShowJump(!near);
  }, []);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [chat.items]);

  const jumpToLatest = () => {
    const el = scrollRef.current;
    if (!el) return;
    stick.current = true;
    setShowJump(false);
    el.scrollTop = el.scrollHeight;
  };

  // ── actions ───────────────────────────────────────────────────────────────
  const submit = async (text: string) => {
    stick.current = true;
    setShowJump(false);
    const quoted = quote;
    setDraft("");
    setQuote(null);
    const accepted = await chat.send(quoted ? buildQuoted(quoted, text) : text);
    if (!accepted) {
      setDraft((current) => current || text); // refused: give the text back
      if (quoted) setQuote(quoted);
    }
  };

  const rate = async (messageId: string, rating: Rating) => {
    const previous = ratings[messageId] ?? null;
    setRatings((r) => ({ ...r, [messageId]: rating }));
    try {
      await aiApi.feedback(messageId, rating);
    } catch {
      setRatings((r) => {
        const next = { ...r };
        if (previous) next[messageId] = previous;
        else delete next[messageId];
        return next;
      });
      toast({ title: "Could not save your feedback", variant: "destructive" });
    }
  };

  const latestAssistantId =
    [...chat.items].reverse().find((i) => i.role === "assistant")?.key ?? null;
  const hasIncomplete = chat.items.some((i) => i.status === "failed" || i.status === "cancelled");
  const showWelcome = chat.phase === "ready" && chat.items.length === 0;

  return (
    <section aria-label="AI Tutor chat" className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <header className="border-border flex items-center gap-2 border-b px-3 py-2">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label="Open conversations"
          onClick={tutor.openDrawer}
        >
          <Menu aria-hidden="true" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="text-sm font-semibold">AI Tutor</h1>
          <p className="text-muted-foreground truncate text-xs" data-testid="conversation-title">
            {conversationId ? (current?.title ?? "New conversation") : "New conversation"}
          </p>
        </div>
        {status.is_test_provider && (
          <span
            className="rounded-full border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300"
            data-testid="test-provider-badge"
          >
            Test provider, not a real AI
          </span>
        )}
        {models.length > 1 && (
          <>
            <label htmlFor="model-select" className="sr-only">
              Model
            </label>
            <select
              id="model-select"
              value={modelId ?? models.find((m) => m.is_default)?.id ?? ""}
              onChange={(e) => {
                const chosen = models.find((m) => m.id === e.target.value);
                setModelId(chosen && !chosen.is_default ? chosen.id : null);
              }}
              disabled={chat.busy}
              className="border-input bg-background focus-visible:ring-ring/50 h-8 max-w-40 rounded-lg border px-2 text-sm outline-none focus-visible:ring-3"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </>
        )}
        <Button variant="ghost" size="icon" aria-label="AI usage" onClick={tutor.openUsage}>
          <BarChart3 aria-hidden="true" />
        </Button>
        <Link
          href={`/ai-tutor${ctxSuffix}`}
          aria-label="New chat"
          className={buttonVariants({ variant: "ghost", size: "icon" })}
        >
          <MessageSquarePlus aria-hidden="true" />
        </Link>
        {current && (
          <RowActions
            name="this conversation"
            actions={[
              { label: "Rename", icon: <Pencil />, onSelect: () => tutor.requestRename(current) },
              { label: "Archive", icon: <Archive />, onSelect: () => tutor.archive(current) },
              {
                label: "Delete",
                icon: <Trash2 />,
                destructive: true,
                separated: true,
                onSelect: () => tutor.requestDelete(current),
              },
            ]}
          />
        )}
      </header>

      {/* Announces start and end of an answer only, never the streamed text itself. */}
      <div className="sr-only" role="status" aria-live="polite" data-testid="chat-announcer">
        {chat.announcement}
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="h-full overflow-x-hidden overflow-y-auto px-3 py-4"
          tabIndex={-1}
        >
          {chat.phase === "loading" ? (
            <div className="flex justify-center py-16">
              <LoadingSpinner />
            </div>
          ) : chat.phase === "error" ? (
            <ErrorDisplay
              title="Could not load this conversation"
              message="Check your connection and try again."
              onRetry={chat.reload}
            />
          ) : chat.phase === "notfound" ? (
            <EmptyState
              title="Conversation not found"
              description="It may have been deleted, or it is not yours."
              action={
                <Link href="/ai-tutor" className={buttonVariants()}>
                  Start a new chat
                </Link>
              }
            />
          ) : showWelcome ? (
            <Welcome onPick={(p) => void submit(p)} disabled={chat.busy} />
          ) : (
            <ol className="mx-auto flex max-w-3xl flex-col gap-5" aria-label="Conversation">
              {chat.items.map((item) => (
                <MessageView
                  key={item.key}
                  item={item}
                  isLatestAssistant={item.key === latestAssistantId}
                  busy={chat.busy}
                  error={chat.error}
                  rating={item.id ? (ratings[item.id] ?? null) : null}
                  onRegenerate={(id) => void chat.regenerate(id)}
                  onRate={(id, r) => void rate(id, r)}
                  doubts={item.id ? doubts.doubts.filter((d) => d.messageId === item.id) : []}
                  onOpenDoubt={doubts.reopen}
                />
              ))}
            </ol>
          )}

          {chat.error && !hasIncomplete && !chat.busy && (
            <div
              role="alert"
              className="border-destructive/40 bg-destructive/5 mx-auto mt-4 flex max-w-3xl flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm"
            >
              <span className="flex-1">{chat.error.message}</span>
              <Button size="sm" variant="outline" onClick={() => void chat.retry()}>
                Retry
              </Button>
            </div>
          )}
        </div>

        {showJump && (
          <Button
            variant="outline"
            size="sm"
            className="bg-background absolute bottom-3 left-1/2 -translate-x-1/2 shadow"
            onClick={jumpToLatest}
          >
            <ArrowDown aria-hidden="true" />
            Jump to latest
          </Button>
        )}
      </div>

      {presetCtx && presetLabel.data && (
        <div className="border-border bg-muted/30 flex items-center gap-2 border-t px-3 py-1.5 text-xs">
          <Link
            href={environmentHref(presetCtx)}
            className="text-muted-foreground hover:text-foreground inline-flex min-w-0 items-center gap-1 underline-offset-2 hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">Back to {presetLabel.data}</span>
          </Link>
        </div>
      )}

      {(!conversationId || lookupScope !== "general") && (
        <div className="border-border flex flex-col gap-2 border-t px-3 py-2 sm:flex-row sm:items-center sm:gap-4">
          {!conversationId && presetCtx && presetLabel.data && !pickScope ? (
            <p className="flex min-w-0 items-center gap-2 text-xs" data-testid="context-scope">
              <Crosshair className="text-primary h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="text-muted-foreground shrink-0">Asking about</span>
              <span className="bg-primary/10 text-foreground min-w-0 truncate rounded-full px-2 py-0.5 font-medium">
                {SCOPE_LABELS[presetCtx.scope]}: {presetLabel.data}
              </span>
              <button
                type="button"
                className="text-primary shrink-0 underline-offset-2 hover:underline"
                onClick={() => setPickScope(true)}
                disabled={chat.busy}
              >
                Change
              </button>
            </p>
          ) : !conversationId ? (
            <ScopePicker value={scope} onChange={setScope} disabled={chat.busy} />
          ) : (
            <p className="text-muted-foreground text-xs">
              Answering from your {lookupScope === "document" ? "document" : "documents"}.
            </p>
          )}
          {(conversationId ? lookupScope !== "general" : scope !== null) && (
            <ModePicker value={mode} onChange={setMode} disabled={chat.busy} />
          )}
        </div>
      )}

      <ChatInput
        value={draft}
        onChange={setDraft}
        onSend={() => void submit(draft)}
        onStop={() => void chat.stop()}
        generating={chat.busy}
        maxChars={status.max_input_chars}
        disabled={chat.phase === "loading" || chat.phase === "notfound"}
        quote={quote}
        onClearQuote={() => setQuote(null)}
      />

      <SelectionToolbar
        onCopy={(text) => {
          navigator.clipboard
            ?.writeText(text)
            .then(() => toast({ title: "Copied" }))
            .catch(() => toast({ title: "Could not copy", variant: "destructive" }));
        }}
        onQuote={setQuote}
        onClear={doubts.open}
      />
      <DoubtDialog
        doubt={doubts.active}
        streaming={doubts.streaming}
        onAsk={(r) => void doubts.ask(r)}
        onClose={doubts.close}
      />
    </section>
  );
}
