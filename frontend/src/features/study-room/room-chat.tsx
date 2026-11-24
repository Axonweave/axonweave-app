"use client";

/**
 * The conversation in the middle of a study room. Built on the AI Tutor's own chat engine
 * (streaming, citations, stop, regenerate), with the room as the scope so answers come from the
 * room's files. The "+" button in the composer uploads files into the room and starts the study
 * tools, so nothing needs a different page.
 */
import { useLayoutEffect, useRef, useState } from "react";
import {
  ArrowDown,
  BookOpenCheck,
  FileText,
  FileUp,
  Layers,
  ListChecks,
  Plus,
  RotateCcw,
  ScrollText,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  aiApi,
  type AiModel,
  type AiStatus,
  type AnswerMode,
  type Conversation,
} from "@/lib/api/ai";
import { documentsApi } from "@/lib/api/documents";
import type { GenerationType } from "@/lib/api/study";
import { ChatInput } from "@/features/ai-tutor/chat-input";
import { MessageView, type Rating } from "@/features/ai-tutor/message-view";
import { ModePicker } from "@/features/ai-tutor/scope-bar";
import { useChat } from "@/features/ai-tutor/use-chat";
import { ACCEPT } from "@/features/documents/upload-zone";
import { GenerateDialog } from "@/features/study/generate-dialog";
import type { LearningSpace } from "@/features/learning-spaces/space-provider";
import type { Panel } from "./room-state";

export interface RoomEvent {
  key: string;
  icon: React.ElementType;
  text: string;
  action?: { label: string; panel: Panel };
}

const TOOLS: { type: GenerationType; label: string; hint: string; icon: React.ElementType }[] = [
  { type: "summary", label: "Summary", hint: "The key ideas in short", icon: ScrollText },
  { type: "flashcards", label: "Flashcards", hint: "Cards for spaced revision", icon: Layers },
  { type: "quiz", label: "Quiz", hint: "Test yourself", icon: ListChecks },
  {
    type: "study_guide",
    label: "Study guide",
    hint: "A structured walkthrough",
    icon: BookOpenCheck,
  },
];

const NEAR_BOTTOM_PX = 80;

export function RoomChat({
  space,
  ai,
  conversationId,
  chapter,
  onConversationCreated,
  onSettled,
  onOpenPanel,
}: {
  space: LearningSpace;
  ai: { status: AiStatus; models: AiModel[] } | null;
  conversationId: string | null;
  chapter: { id: string; title: string } | null;
  onConversationCreated: (c: Conversation) => void;
  onSettled: () => void;
  onOpenPanel: (p: Panel) => void;
}) {
  const { toast } = useToast();
  const { subject, ctx } = space;
  const focusName = chapter?.title ?? subject.name;

  const [mode, setMode] = useState<AnswerMode>("document_first");
  const chat = useChat({
    conversationId,
    modelId: null,
    scope: conversationId
      ? null
      : chapter
        ? { kind: "chapter", id: chapter.id }
        : { kind: "subject", id: subject.id },
    answerMode: mode,
    onConversationCreated,
    onSettled,
  });

  const [draft, setDraft] = useState("");
  const [ratings, setRatings] = useState<Record<string, Rating>>({});
  // things done in the room during this visit (uploads, generations), shown under the chat
  const [events, setEvents] = useState<RoomEvent[]>([]);
  const [generate, setGenerate] = useState<GenerationType | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  // ── scrolling that never fights the reader ────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [showJump, setShowJump] = useState(false);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [chat.items, events]);
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    stick.current = near;
    setShowJump(!near);
  };

  const addEvent = (e: Omit<RoomEvent, "key">) =>
    setEvents((list) => [...list, { ...e, key: `${Date.now()}-${list.length}` }]);

  const submit = async (text: string) => {
    if (!ai?.status.configured) return;
    stick.current = true;
    setShowJump(false);
    setDraft("");
    const accepted = await chat.send(text);
    if (!accepted) setDraft((current) => current || text);
  };

  const rate = async (messageId: string, rating: Rating) => {
    setRatings((r) => ({ ...r, [messageId]: rating }));
    try {
      await aiApi.feedback(messageId, rating);
    } catch {
      toast({ title: "Could not save your feedback", variant: "destructive" });
    }
  };

  const upload = async (files: File[]) => {
    if (files.length === 0) return;
    setUploading(true);
    try {
      const result = await documentsApi.upload(files, {
        workspace_id: ctx.workspaceId,
        subject_id: subject.id,
        chapter_id: chapter?.id ?? null,
      });
      if (result.documents.length > 0) {
        addEvent({
          icon: FileUp,
          text: `Added ${result.documents.map((d) => d.display_name).join(", ")} to ${focusName}. It's being read now; the tutor can use it once processing finishes.`,
          action: { label: "View files", panel: "files" },
        });
      }
      for (const r of result.rejected) {
        toast({
          title: `${r.filename} was not uploaded`,
          description: r.message,
          variant: "destructive",
        });
      }
    } catch (e) {
      toast({
        title: "Upload failed",
        description:
          e instanceof ApiRequestError ? e.message : "Check your connection and try again.",
        variant: "destructive",
      });
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const latestAssistantId =
    [...chat.items].reverse().find((i) => i.role === "assistant")?.key ?? null;
  const empty = chat.phase !== "loading" && chat.items.length === 0;
  const notConfigured = ai !== null && !ai.status.configured;

  const plusMenu = (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button type="button" variant="outline" size="icon" />}
        aria-label="Add files or use a study tool"
        disabled={uploading}
      >
        {uploading ? <LoadingSpinner size="sm" /> : <Plus aria-hidden="true" />}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="min-w-64">
        <DropdownMenuItem onClick={() => fileInput.current?.click()}>
          <FileUp aria-hidden="true" />
          <span className="flex flex-col">
            <span>Upload files</span>
            <span className="text-muted-foreground text-xs">
              PDF, slides, Word, notes or images
            </span>
          </span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>Make from {focusName}</DropdownMenuLabel>
          {TOOLS.map((t) => (
            <DropdownMenuItem key={t.type} onClick={() => setGenerate(t.type)}>
              <t.icon aria-hidden="true" />
              <span className="flex flex-col">
                <span>{t.label}</span>
                <span className="text-muted-foreground text-xs">{t.hint}</span>
              </span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => onOpenPanel("revision")}>
          <RotateCcw aria-hidden="true" />
          Revise due cards
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <section aria-label="Study room chat" className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <div className="sr-only" role="status" aria-live="polite">
        {chat.announcement}
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="h-full overflow-x-hidden overflow-y-auto px-4 py-6"
          tabIndex={-1}
        >
          {chat.phase === "loading" ? (
            <div className="flex justify-center py-16">
              <LoadingSpinner />
            </div>
          ) : chat.phase === "error" ? (
            <ErrorDisplay
              title="Could not load this chat"
              message="Check your connection and try again."
              onRetry={chat.reload}
            />
          ) : chat.phase === "notfound" ? (
            <EmptyState title="Chat not found" description="It may have been deleted." />
          ) : empty ? (
            <RoomWelcome
              name={focusName}
              colour={subject.colour}
              notConfigured={notConfigured}
              onAsk={(p) => void submit(p)}
              onUpload={() => fileInput.current?.click()}
              onGenerate={setGenerate}
              onOpenPanel={onOpenPanel}
              busy={chat.busy}
            />
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
                />
              ))}
            </ol>
          )}

          {events.length > 0 ? (
            <ul
              className="mx-auto mt-5 flex max-w-3xl flex-col gap-3"
              aria-label="Done in this room"
            >
              {events.map((e) => (
                <li
                  key={e.key}
                  className="animate-in fade-in-0 slide-in-from-bottom-2 bg-card flex items-start gap-3 rounded-lg border p-3 text-sm shadow-xs duration-300"
                >
                  <span className="bg-muted text-muted-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-md">
                    <e.icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1 pt-1">{e.text}</span>
                  {e.action ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onOpenPanel(e.action!.panel)}
                    >
                      {e.action.label}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}

          {chat.error && !chat.busy && !chat.items.some((i) => i.status === "failed") ? (
            <div
              role="alert"
              className="border-destructive/40 bg-destructive/5 mx-auto mt-4 flex max-w-3xl flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm"
            >
              <span className="flex-1">{chat.error.message}</span>
              <Button size="sm" variant="outline" onClick={() => void chat.retry()}>
                Retry
              </Button>
            </div>
          ) : null}
        </div>

        {showJump ? (
          <Button
            variant="outline"
            size="sm"
            className="bg-background absolute bottom-3 left-1/2 -translate-x-1/2 shadow"
            onClick={() => {
              const el = scrollRef.current;
              if (!el) return;
              stick.current = true;
              setShowJump(false);
              el.scrollTop = el.scrollHeight;
            }}
          >
            <ArrowDown aria-hidden="true" />
            Jump to latest
          </Button>
        ) : null}
      </div>

      <div className="px-3 pt-1">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-2">
          <p className="text-muted-foreground flex min-w-0 items-center gap-1.5 text-xs">
            <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">
              Answers from <span className="text-foreground font-medium">{focusName}</span>
              {conversationId ? "" : chapter ? " (this chapter)" : " (whole room)"}
            </span>
          </p>
          {notConfigured ? null : (
            <ModePicker value={mode} onChange={setMode} disabled={chat.busy} />
          )}
        </div>
      </div>

      <input
        ref={fileInput}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-label="Upload files to this room"
        onChange={(e) => void upload(Array.from(e.target.files ?? []))}
      />

      {notConfigured ? (
        <p className="text-muted-foreground px-4 pt-2 text-center text-xs">
          The AI Tutor isn&apos;t set up on this server yet, so asking questions is unavailable. Use
          <span className="font-medium"> + </span> to add files, and the buttons above for revision
          and progress.
        </p>
      ) : null}
      {/* The "+" stays usable without AI or before it has loaded: uploads never need a model. */}
      <ChatInput
        value={draft}
        onChange={setDraft}
        onSend={() => void submit(draft)}
        onStop={() => void chat.stop()}
        generating={chat.busy}
        maxChars={ai?.status.max_input_chars ?? 4000}
        disabled={!ai || notConfigured || chat.phase === "loading" || chat.phase === "notfound"}
        leading={plusMenu}
        placeholder={notConfigured ? "Chat is unavailable" : `Ask anything about ${focusName}…`}
      />

      {generate ? (
        <GenerateDialog
          open={!!generate}
          onOpenChange={(o) => !o && setGenerate(null)}
          defaultType={generate}
          preset={
            chapter
              ? { type: "chapter", id: chapter.id, label: chapter.title }
              : { type: "subject", id: subject.id, label: subject.name }
          }
          onStarted={() => {
            const label = TOOLS.find((t) => t.type === generate)?.label ?? "Study material";
            setGenerate(null);
            addEvent({
              icon: Layers,
              text: `${label} for ${focusName} is being made. It appears under Materials when ready.`,
              action: { label: "Open materials", panel: "materials" },
            });
          }}
        />
      ) : null}
    </section>
  );
}

function RoomWelcome({
  name,
  colour,
  notConfigured,
  onAsk,
  onUpload,
  onGenerate,
  onOpenPanel,
  busy,
}: {
  name: string;
  colour: string | null;
  notConfigured: boolean;
  onAsk: (prompt: string) => void;
  onUpload: () => void;
  onGenerate: (t: GenerationType) => void;
  onOpenPanel: (p: Panel) => void;
  busy: boolean;
}) {
  const c = colour ?? "#6366f1";
  const prompts = [
    `Summarise the key ideas of ${name}`,
    "Explain the hardest concept simply",
    "What should I learn first?",
    "Quiz me with five questions",
  ];
  const actions: { label: string; icon: React.ElementType; run: () => void }[] = [
    { label: "Upload files", icon: FileUp, run: onUpload },
    { label: "Flashcards", icon: Layers, run: () => onGenerate("flashcards") },
    { label: "Quiz", icon: ListChecks, run: () => onGenerate("quiz") },
    { label: "Revise", icon: RotateCcw, run: () => onOpenPanel("revision") },
  ];
  return (
    <div className="animate-in fade-in-0 mx-auto flex max-w-2xl flex-col px-2 pt-10 pb-6 duration-300">
      <p className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: c }} aria-hidden="true" />
        {name}
      </p>
      <h2 className="mt-2 text-xl font-semibold tracking-tight">Start studying</h2>
      <p className="text-muted-foreground mt-1 text-sm">
        Ask a question about this room&apos;s material, add files with{" "}
        <span className="text-foreground font-medium">+</span>, or start with one of these.
      </p>

      <ul className="mt-5 grid w-full grid-cols-2 gap-2 sm:grid-cols-4">
        {actions.map((a, i) => (
          <li
            key={a.label}
            className="animate-in fade-in-0 fill-mode-both duration-300"
            style={{ animationDelay: `${60 + i * 40}ms` }}
          >
            <button
              type="button"
              onClick={a.run}
              className="bg-card hover:bg-muted/50 focus-visible:ring-ring hover:border-foreground/20 flex h-full w-full items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <a.icon className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
              {a.label}
            </button>
          </li>
        ))}
      </ul>

      {!notConfigured ? (
        <ul className="mt-6 divide-y rounded-lg border" aria-label="Suggested questions">
          {prompts.map((p) => (
            <li key={p}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onAsk(p)}
                className="text-muted-foreground hover:text-foreground hover:bg-muted/50 flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm transition-colors disabled:opacity-50"
              >
                {p}
                <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
