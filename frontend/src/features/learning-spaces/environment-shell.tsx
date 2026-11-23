"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  BrainCircuit,
  ChevronRight,
  ChevronsUpDown,
  ClipboardCheck,
  FileText,
  FlaskConical,
  Folder as FolderIcon,
  FolderTree,
  Gauge,
  LayoutDashboard,
  Network,
  RotateCcw,
  MessagesSquare,
  Plus,
  Search,
  Sparkles,
  Upload,
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
import { cn } from "@/lib/utils";
import {
  ENVIRONMENT_TABS,
  SCOPE_LABELS,
  activeTab,
  environmentBase,
  environmentHref,
  makeContext,
  type EnvironmentTab,
  type LearningContext,
} from "@/lib/learning-context";
import { GenerateDialog } from "@/features/study/generate-dialog";
import { StatusBadge } from "@/features/academic/status";
import { openCommandPalette } from "./command-palette-events";
import { useLearningSpace, useSpaceState, type LearningSpace } from "./space-provider";
import { TONES } from "./tones";
import { roomHref } from "@/features/workspaces/current-workspace";

export const TAB_ICONS: Record<EnvironmentTab, React.ElementType> = {
  overview: LayoutDashboard,
  content: FolderTree,
  tutor: BrainCircuit,
  graph: Network,
  intelligence: Gauge,
  revision: RotateCcw,
  research: FlaskConical,
  progress: ClipboardCheck,
};

/**
 * Wraps one level of the hierarchy (subject, folder or chapter) in its learning environment:
 * where-am-I trail, header with quick actions, and the tab bar. Tabs render as children.
 */
export function EnvironmentShell({ children }: { children: React.ReactNode }) {
  const state = useSpaceState();

  if (state.status === "loading") {
    return (
      <div className="flex min-h-[40vh] items-center justify-center" aria-busy="true">
        <LoadingSpinner />
      </div>
    );
  }
  if (state.status === "error") {
    return <ErrorDisplay message="Could not load this learning space." onRetry={state.retry} />;
  }
  if (state.status === "not-found") {
    const what = state.what.charAt(0).toUpperCase() + state.what.slice(1);
    return (
      <EmptyState
        title={`${what} not found`}
        description="It may have been deleted, or it is not in your account."
        action={
          <Link href="/subjects" className="text-primary underline underline-offset-4">
            Back to subjects
          </Link>
        }
      />
    );
  }
  return <ReadyShell>{children}</ReadyShell>;
}

function ReadyShell({ children }: { children: React.ReactNode }) {
  const space = useLearningSpace();
  const pathname = usePathname();
  const base = environmentBase(space.ctx) ?? "";
  const tab = activeTab(pathname, base);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <EnvironmentHeader space={space} tab={tab} />
      <TabBar ctx={space.ctx} tab={tab} />
      <div key={tab} className="animate-in fade-in-0 slide-in-from-bottom-1 duration-200">
        {children}
      </div>
    </div>
  );
}

// ── Header ───────────────────────────────────────────────────────────────────

/** Subjects without a chosen colour use the brand indigo, never grey. */
export const DEFAULT_SUBJECT_COLOUR = "#6366f1";

function EnvironmentHeader({ space, tab }: { space: LearningSpace; tab: EnvironmentTab }) {
  const { ctx, subject, folder, chapter, scopedChapters, scopedFolders } = space;
  const colour = subject.colour ?? DEFAULT_SUBJECT_COLOUR;
  const title = chapter?.title ?? folder?.name ?? subject.name;
  const description = chapter
    ? chapter.description
    : folder
      ? folder.description
      : subject.description;
  const ScopeIcon = chapter ? FileText : folder ? FolderIcon : BookOpen;
  const chapterCount = folder ? scopedChapters.length : space.chapterTotal;

  return (
    <header className="bg-card relative overflow-hidden rounded-3xl border shadow-sm">
      {/* colour band: the subject's own colour carries through every level below it */}
      <div
        className="h-20 sm:h-24"
        style={{
          backgroundImage: `linear-gradient(120deg, color-mix(in oklch, ${colour} 55%, white) 0%, color-mix(in oklch, ${colour} 25%, white) 55%, color-mix(in oklch, ${colour} 8%, white) 100%)`,
        }}
        aria-hidden="true"
      />
      <div className="px-5 pb-5 sm:px-7 sm:pb-6">
        <div className="-mt-9 flex flex-wrap items-end justify-between gap-4 sm:-mt-10">
          <span
            className="bg-card flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl p-1 text-2xl shadow-md sm:h-[72px] sm:w-[72px]"
            aria-hidden="true"
          >
            <span
              className="flex h-full w-full items-center justify-center rounded-xl"
              style={{ backgroundColor: `color-mix(in oklch, ${colour} 16%, transparent)` }}
            >
              {!folder && !chapter && subject.icon ? (
                subject.icon
              ) : (
                <ScopeIcon className="h-7 w-7" style={{ color: colour }} />
              )}
            </span>
          </span>
          <div className="flex items-center gap-2 pb-1">
            <Link
              href={
                roomHref(ctx.workspaceId, subject.id) + (chapter ? `?chapter=${chapter.id}` : "")
              }
              className={buttonVariants({ size: "lg" })}
            >
              <MessagesSquare aria-hidden="true" />
              {chapter ? "Study this chapter" : "Open study room"}
            </Link>
            <AddMenu space={space} />
          </div>
        </div>

        <div className="mt-3 min-w-0">
          <ScopeTrail space={space} tab={tab} />
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight break-words sm:text-3xl">{title}</h1>
            <span
              className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase"
              style={{
                backgroundColor: `color-mix(in oklch, ${colour} 14%, transparent)`,
                color: `color-mix(in oklch, ${colour} 70%, black)`,
              }}
            >
              {SCOPE_LABELS[ctx.scope]}
            </span>
            {chapter ? <StatusBadge status={chapter.status} /> : null}
          </div>
          {description ? (
            <p className="text-muted-foreground mt-1 line-clamp-2 max-w-2xl text-sm break-words">
              {description}
            </p>
          ) : null}
          <p className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {chapter ? (
              <span className="inline-flex items-center gap-1.5">
                <FolderIcon className="h-3.5 w-3.5" aria-hidden="true" />
                {space.path.length ? space.path.map((f) => f.name).join(" / ") : "Not in a folder"}
              </span>
            ) : (
              <>
                <span className="inline-flex items-center gap-1.5">
                  <FolderIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  {scopedFolders.length} {scopedFolders.length === 1 ? "folder" : "folders"}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  {chapterCount} {chapterCount === 1 ? "chapter" : "chapters"}
                </span>
              </>
            )}
          </p>
        </div>
      </div>
    </header>
  );
}

/** Secondary actions live in one menu so the header shows a single clear next step. */
function AddMenu({ space }: { space: LearningSpace }) {
  const { ctx, subject, folder, chapter } = space;
  const [generating, setGenerating] = useState(false);
  const uploadHref =
    `/library?workspace=${ctx.workspaceId}&subject=${ctx.subjectId}` +
    (chapter ? `&chapter=${chapter.id}` : "");
  const preset = chapter
    ? { type: "chapter" as const, id: chapter.id, label: chapter.title }
    : folder
      ? { type: "folder" as const, id: folder.id, label: folder.name }
      : { type: "subject" as const, id: subject.id, label: subject.name };
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="outline" size="lg" />}>
          <Plus aria-hidden="true" />
          Add
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-64">
          <DropdownMenuItem render={<Link href={uploadHref} />}>
            <Upload aria-hidden="true" />
            <span className="flex flex-col">
              <span>Upload documents</span>
              <span className="text-muted-foreground text-xs">PDFs and notes to learn from</span>
            </span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setGenerating(true)}>
            <Sparkles aria-hidden="true" />
            <span className="flex flex-col">
              <span>Generate study material</span>
              <span className="text-muted-foreground text-xs">Summary, flashcards or a quiz</span>
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {generating ? (
        <GenerateDialog open={generating} onOpenChange={setGenerating} preset={preset} />
      ) : null}
    </>
  );
}

// ── Where am I / change scope ────────────────────────────────────────────────

/** Breadcrumbs that keep the current tab: zooming out from a chapter's graph opens the folder's graph. */
function ScopeTrail({ space, tab }: { space: LearningSpace; tab: EnvironmentTab }) {
  const { ctx, workspace, subject, path, folder, chapter } = space;
  const crumbs: { label: string; href?: string }[] = [
    { label: workspace.name, href: `/subjects?workspace=${workspace.id}` },
    {
      label: subject.name,
      href: environmentHref(
        makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id }),
        tab,
      ),
    },
    ...path.map((f) => ({
      label: f.name,
      href: environmentHref(
        makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, folderId: f.id }),
        tab,
      ),
    })),
  ];
  if (chapter) crumbs.push({ label: chapter.title });
  // the open folder is the last path entry; show it as the current page
  if (folder && !chapter) crumbs[crumbs.length - 1] = { label: folder.name };
  if (!folder && !chapter) crumbs[1] = { label: subject.name };

  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
      <nav aria-label="You are here" className="min-w-0">
        <ol className="text-muted-foreground flex flex-wrap items-center gap-1 text-sm">
          {crumbs.map((c, i) => {
            const last = i === crumbs.length - 1;
            return (
              <li key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-1">
                {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                {c.href && !last ? (
                  <Link
                    href={c.href}
                    className="hover:text-foreground focus-visible:ring-ring max-w-[14rem] truncate rounded-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {c.label}
                  </Link>
                ) : (
                  <span
                    className={cn("max-w-[16rem] truncate", last && "text-foreground font-medium")}
                    aria-current={last ? "page" : undefined}
                  >
                    {c.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      <ScopeSwitcher space={space} tab={tab} />
    </div>
  );
}

const MAX_NARROW = 12;

function ScopeSwitcher({ space, tab }: { space: LearningSpace; tab: EnvironmentTab }) {
  const { ctx, subject, folder, chapter, path, folders, chapters } = space;
  const at = (ids: { folderId?: string; chapterId?: string }) =>
    environmentHref(
      makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, ...ids }),
      tab,
    );

  // wider: every ancestor scope, nearest first
  const wider: { label: string; kind: string; href: string }[] = [];
  const ancestors = chapter ? path : path.slice(0, -1);
  for (const f of [...ancestors].reverse())
    wider.push({ label: f.name, kind: "Folder", href: at({ folderId: f.id }) });
  if (folder || chapter) wider.push({ label: subject.name, kind: "Subject", href: at({}) });
  wider.push({
    label: "Whole workspace",
    kind: "Workspace",
    href: environmentHref(makeContext({ workspaceId: ctx.workspaceId }), tab),
  });

  // narrower: direct children of the current scope
  const parentId = folder?.id ?? null;
  const narrowFolders = chapter
    ? []
    : folders.filter((f) => (f.parent_folder_id ?? null) === parentId);
  const narrowChapters = chapter ? [] : chapters.filter((c) => (c.folder_id ?? null) === parentId);
  const narrower = [
    ...narrowFolders.map((f) => ({ label: f.name, kind: "Folder", href: at({ folderId: f.id }) })),
    ...narrowChapters.map((c) => ({
      label: c.title,
      kind: "Chapter",
      href: at({ chapterId: c.id }),
    })),
  ];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" size="sm" className="bg-background/70 backdrop-blur" />}
      >
        <ChevronsUpDown aria-hidden="true" />
        Change scope
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[70vh] min-w-64 overflow-y-auto">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Zoom out</DropdownMenuLabel>
          {wider.map((w) => (
            <DropdownMenuItem key={w.href} render={<Link href={w.href} />}>
              <span className="min-w-0 flex-1 truncate">{w.label}</span>
              <span className="text-muted-foreground text-xs">{w.kind}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
        {narrower.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel>Focus on</DropdownMenuLabel>
              {narrower.slice(0, MAX_NARROW).map((n) => (
                <DropdownMenuItem key={n.href} render={<Link href={n.href} />}>
                  <span className="min-w-0 flex-1 truncate">{n.label}</span>
                  <span className="text-muted-foreground text-xs">{n.kind}</span>
                </DropdownMenuItem>
              ))}
              {narrower.length > MAX_NARROW && (
                <p className="text-muted-foreground px-2 py-1 text-xs">
                  {narrower.length - MAX_NARROW} more: use search
                </p>
              )}
            </DropdownMenuGroup>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => openCommandPalette()}>
          <Search aria-hidden="true" />
          <span className="flex-1">Search everything…</span>
          <kbd className="text-muted-foreground text-[10px]">Ctrl K</kbd>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ── Tabs ─────────────────────────────────────────────────────────────────────

/** Pill tabs, each in its tool's colour, so the eye finds a tool without reading every label. */
function TabBar({ ctx, tab }: { ctx: LearningContext; tab: EnvironmentTab }) {
  return (
    <nav
      aria-label={`${SCOPE_LABELS[ctx.scope]} sections`}
      className="bg-background/85 supports-[backdrop-filter]:bg-background/70 sticky -top-6 z-20 -mx-6 px-6 py-2 backdrop-blur-md"
    >
      <ul className="bg-card flex [scrollbar-width:none] gap-1 overflow-x-auto rounded-2xl border p-1 shadow-xs">
        {ENVIRONMENT_TABS.map((t) => {
          const Icon = TAB_ICONS[t.id];
          const tone = TONES[t.id];
          const current = t.id === tab;
          return (
            <li key={t.id} className="shrink-0">
              <Link
                href={environmentHref(ctx, t.id)}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "focus-visible:ring-ring flex items-center gap-2 rounded-xl px-3 py-2 text-sm whitespace-nowrap transition-all focus-visible:ring-2 focus-visible:outline-none",
                  current
                    ? cn(tone.active, "font-semibold")
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className={cn("h-4 w-4", !current && tone.icon)} aria-hidden="true" />
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
