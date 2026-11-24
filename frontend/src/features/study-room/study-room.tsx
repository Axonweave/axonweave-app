"use client";

/**
 * A study room: one place for one topic. Chats on the left, the conversation in the middle, and
 * every tool (files, materials, revision, intelligence, graph, progress, research, chapters) in a
 * panel that slides in beside it. The room is a subject in the API; tools reuse the subject's
 * learning-environment views, so nothing here duplicates their logic.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  BookOpenCheck,
  ChevronDown,
  ClipboardCheck,
  Crosshair,
  FileText,
  FlaskConical,
  FolderTree,
  Gauge,
  Layers,
  MessagesSquare,
  MoreHorizontal,
  Network,
  RotateCcw,
  Settings2,
  X,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
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
import { aiApi, type AiModel, type AiStatus, type Conversation } from "@/lib/api/ai";
import { environmentHref } from "@/lib/learning-context";
import { cn } from "@/lib/utils";
import { NoticeDialog } from "@/features/ai-tutor/dialogs";
import { EnvironmentTab } from "@/features/learning-spaces/environment-tab";
import { ScopedMaterials } from "@/features/learning-spaces/scoped-materials";
import { useLearningSpace, useSpaceState } from "@/features/learning-spaces/space-provider";
import { TONES, type Tone } from "@/features/learning-spaces/tones";
import { DEFAULT_SUBJECT_COLOUR } from "@/features/learning-spaces/environment-shell";
import { workspaceHref } from "@/features/workspaces/current-workspace";
import { FilesPanel } from "./files-panel";
import { RoomChat } from "./room-chat";
import { RoomChats, useRoomChats } from "./room-chats";
import { useRoomState, type Panel } from "./room-state";

const PANEL_META: Record<Panel, { label: string; icon: React.ElementType; tone: Tone }> = {
  files: { label: "Files", icon: FileText, tone: TONES.content },
  materials: { label: "Materials", icon: Layers, tone: TONES.tutor },
  revision: { label: "Revision", icon: RotateCcw, tone: TONES.revision },
  intelligence: { label: "Intelligence", icon: Gauge, tone: TONES.intelligence },
  graph: { label: "Knowledge Graph", icon: Network, tone: TONES.graph },
  progress: { label: "Progress", icon: ClipboardCheck, tone: TONES.progress },
  research: { label: "Research", icon: FlaskConical, tone: TONES.research },
  chapters: { label: "Chapters", icon: FolderTree, tone: TONES.overview },
};
/** Always visible in the room's top bar; the rest sit under "More tools". */
const MAIN_PANELS: Panel[] = ["files", "materials", "revision", "intelligence"];
const MORE_PANELS: Panel[] = ["graph", "progress", "research", "chapters"];

export function StudyRoom() {
  const state = useSpaceState();
  if (state.status === "loading")
    return (
      <div className="flex h-full items-center justify-center" aria-busy="true">
        <LoadingSpinner />
      </div>
    );
  if (state.status === "error")
    return (
      <div className="p-6">
        <ErrorDisplay message="Could not open this study room." onRetry={state.retry} />
      </div>
    );
  if (state.status === "not-found")
    return (
      <div className="p-6">
        <EmptyState
          title="Study room not found"
          description="It may have been deleted, or it isn't in your account."
          action={
            <Link href="/workspaces" className={buttonVariants()}>
              Your workspaces
            </Link>
          }
        />
      </div>
    );
  return <ReadyRoom />;
}

type AiBoot = { status: AiStatus; models: AiModel[]; acknowledged: boolean } | null;

function useAiBoot() {
  const [boot, setBoot] = useState<AiBoot>(null);
  useEffect(() => {
    let live = true;
    Promise.all([aiApi.status(), aiApi.preferences()])
      .then(async ([status, prefs]) => {
        const models = status.configured ? await aiApi.models().catch(() => []) : [];
        if (live)
          setBoot({ status, models, acknowledged: prefs.ai_notice_acknowledged_at !== null });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return [boot, setBoot] as const;
}

function ReadyRoom() {
  const space = useLearningSpace();
  const { subject, workspace, chapters } = space;
  const room = useRoomState();
  const chats = useRoomChats(space);
  const [boot, setBoot] = useAiBoot();
  const [chatsOpen, setChatsOpen] = useState(false);
  const colour = subject.colour ?? DEFAULT_SUBJECT_COLOUR;

  const chapter = room.chapterId ? (chapters.find((c) => c.id === room.chapterId) ?? null) : null;
  const sortedChapters = [...chapters].sort((a, b) => a.display_order - b.display_order);

  const chapterName = useCallback(
    (c: Conversation) =>
      c.scope_type === "chapter"
        ? (chapters.find((x) => x.id === c.scope_id)?.title ?? null)
        : null,
    [chapters],
  );

  // a new chat starts empty, so a fresh key resets the chat engine
  const [chatKey, setChatKey] = useState(0);
  const newChat = () => {
    room.openChat(null);
    setChatKey((k) => k + 1);
    setChatsOpen(false);
  };

  // Escape closes the tool panel
  const { panel, openPanel } = room;
  useEffect(() => {
    if (!panel) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) openPanel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, openPanel]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ── room bar ─────────────────────────────────────────────────────── */}
      <header className="bg-background flex min-h-14 flex-wrap items-center gap-x-3 gap-y-2 border-b px-4 py-2">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          aria-label="Chats in this room"
          onClick={() => setChatsOpen(true)}
        >
          <MessagesSquare aria-hidden="true" />
        </Button>
        <span
          className="bg-card flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-base"
          aria-hidden="true"
        >
          {subject.icon || (
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colour }} />
          )}
        </span>
        <div className="min-w-0">
          <nav aria-label="You are here" className="text-muted-foreground text-xs">
            <Link href={workspaceHref(workspace.id)} className="hover:text-foreground">
              {workspace.name}
            </Link>
          </nav>
          <h1 className="truncate text-base leading-tight font-semibold">{subject.name}</h1>
        </div>

        <ChapterPicker
          chapters={sortedChapters}
          current={chapter}
          onPick={(id) => {
            room.setChapter(id);
            newChat();
          }}
        />

        <div className="ml-auto flex items-center gap-1">
          <nav aria-label="Room tools" className="hidden items-center gap-1 md:flex">
            {MAIN_PANELS.map((p) => (
              <PanelButton key={p} panel={p} active={room.panel === p} onClick={room.openPanel} />
            ))}
          </nav>
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label="More tools"
              className="text-muted-foreground hover:bg-muted hover:text-foreground data-[popup-open]:bg-muted data-[popup-open]:text-foreground focus-visible:ring-ring flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline">More</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-60">
              <DropdownMenuGroup className="md:hidden">
                {MAIN_PANELS.map((p) => (
                  <PanelItem key={p} panel={p} onClick={room.openPanel} />
                ))}
                <DropdownMenuSeparator />
              </DropdownMenuGroup>
              <DropdownMenuGroup>
                <DropdownMenuLabel>More tools</DropdownMenuLabel>
                {MORE_PANELS.map((p) => (
                  <PanelItem key={p} panel={p} onClick={room.openPanel} />
                ))}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel>Go to</DropdownMenuLabel>
                <DropdownMenuItem render={<Link href={environmentHref(space.ctx)} />}>
                  <Settings2 aria-hidden="true" />
                  Room settings
                </DropdownMenuItem>
                <DropdownMenuItem render={<Link href="/ai-tutor" />}>
                  <BookOpenCheck aria-hidden="true" />
                  All AI Tutor chats
                </DropdownMenuItem>
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* ── body ─────────────────────────────────────────────────────────── */}
      <div className="relative flex min-h-0 flex-1">
        <aside
          className={cn(
            "bg-sidebar w-64 shrink-0 border-r",
            "max-lg:bg-background max-lg:absolute max-lg:inset-y-0 max-lg:left-0 max-lg:z-30 max-lg:shadow-xl max-lg:transition-transform max-lg:duration-200",
            !chatsOpen && "max-lg:invisible max-lg:-translate-x-full",
          )}
          aria-label="Room chats"
        >
          <div className="flex items-center justify-end p-1 lg:hidden">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Close chats"
              onClick={() => setChatsOpen(false)}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
          <RoomChats
            chats={chats}
            activeId={room.chatId}
            onOpen={(id) => {
              room.openChat(id);
              setChatsOpen(false);
            }}
            onNew={newChat}
            onChanged={chats.reload}
            chapterName={chapterName}
          />
        </aside>
        {chatsOpen ? (
          <button
            type="button"
            aria-label="Close chats"
            className="absolute inset-0 z-20 bg-black/20 lg:hidden"
            onClick={() => setChatsOpen(false)}
          />
        ) : null}

        <RoomChat
          key={room.chatId ?? `new-${chatKey}-${room.chapterId ?? ""}`}
          space={space}
          ai={boot}
          conversationId={room.chatId}
          chapter={chapter ? { id: chapter.id, title: chapter.title } : null}
          onConversationCreated={(c) => {
            room.openChat(c.id);
            chats.reload();
          }}
          onSettled={chats.reload}
          onOpenPanel={room.openPanel}
        />

        {room.panel ? <ToolPanel panel={room.panel} onClose={() => room.openPanel(null)} /> : null}
      </div>

      {boot ? (
        <NoticeDialog
          open={boot.status.configured && !boot.acknowledged}
          status={boot.status}
          onAcknowledged={() => setBoot({ ...boot, acknowledged: true })}
        />
      ) : null}
    </div>
  );
}

function ChapterPicker({
  chapters,
  current,
  onPick,
}: {
  chapters: { id: string; title: string }[];
  current: { id: string; title: string } | null;
  onPick: (id: string | null) => void;
}) {
  if (chapters.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Focus: ${current ? current.title : "whole room"}. Change focus`}
        className={cn(
          "focus-visible:ring-ring inline-flex h-7 max-w-56 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none",
          current
            ? "border-primary/40 bg-primary/5 text-primary"
            : "bg-card text-muted-foreground hover:text-foreground",
        )}
      >
        <Crosshair className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{current ? current.title : "All chapters"}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 min-w-60 overflow-y-auto">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Focus the chat and tools on</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => onPick(null)}>
            <span className="flex-1">All chapters (whole room)</span>
            {!current ? <span className="text-primary text-xs">●</span> : null}
          </DropdownMenuItem>
          {chapters.map((c) => (
            <DropdownMenuItem key={c.id} onClick={() => onPick(c.id)}>
              <span className="flex-1 truncate">{c.title}</span>
              {current?.id === c.id ? <span className="text-primary text-xs">●</span> : null}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function PanelButton({
  panel,
  active,
  onClick,
}: {
  panel: Panel;
  active: boolean;
  onClick: (p: Panel | null) => void;
}) {
  const { label, icon: Icon, tone } = PANEL_META[panel];
  return (
    <button
      type="button"
      onClick={() => onClick(active ? null : panel)}
      aria-pressed={active}
      className={cn(
        "focus-visible:ring-ring flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none",
        active
          ? cn(tone.active, "font-semibold")
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className={cn("h-4 w-4", !active && tone.icon)} aria-hidden="true" />
      {label}
    </button>
  );
}

function PanelItem({ panel, onClick }: { panel: Panel; onClick: (p: Panel) => void }) {
  const { label, icon: Icon, tone } = PANEL_META[panel];
  return (
    <DropdownMenuItem onClick={() => onClick(panel)}>
      <Icon className={tone.icon} aria-hidden="true" />
      {label}
    </DropdownMenuItem>
  );
}

function ToolPanel({ panel, onClose }: { panel: Panel; onClose: () => void }) {
  const { label, icon: Icon, tone } = PANEL_META[panel];
  return (
    <aside
      aria-label={label}
      className="bg-background animate-in slide-in-from-right-8 fade-in-0 absolute inset-y-0 right-0 z-30 flex w-full flex-col border-l shadow-xl duration-200 sm:w-[min(640px,92%)] 2xl:static 2xl:w-[640px] 2xl:shadow-none"
    >
      <div className="flex items-center gap-2 border-b px-4 py-2.5">
        <span className={cn("flex h-8 w-8 items-center justify-center rounded-lg", tone.chip)}>
          <Icon className={cn("h-4 w-4", tone.icon)} aria-hidden="true" />
        </span>
        <h2 className="flex-1 text-sm font-semibold">{label}</h2>
        <Button variant="ghost" size="icon" aria-label={`Close ${label}`} onClick={onClose}>
          <X aria-hidden="true" />
        </Button>
      </div>
      <div
        key={panel}
        className="animate-in fade-in-0 min-h-0 flex-1 overflow-y-auto p-4 duration-200"
      >
        <PanelBody panel={panel} />
      </div>
    </aside>
  );
}

function PanelBody({ panel }: { panel: Panel }) {
  switch (panel) {
    case "files":
      return <FilesPanel />;
    case "materials":
      return <ScopedMaterials />;
    case "chapters":
      return <EnvironmentTab tab="content" />;
    default:
      return <EnvironmentTab tab={panel} />;
  }
}
