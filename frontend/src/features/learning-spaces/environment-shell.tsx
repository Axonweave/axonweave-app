"use client";

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
  Search,
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
import { GenerateButton } from "@/features/study/generate-button";
import { StatusBadge } from "@/features/academic/status";
import { openCommandPalette } from "./command-palette-events";
import { useLearningSpace, useSpaceState, type LearningSpace } from "./space-provider";

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

function EnvironmentHeader({ space, tab }: { space: LearningSpace; tab: EnvironmentTab }) {
  const { ctx, subject, folder, chapter, scopedChapters, scopedFolders } = space;
  const colour = subject.colour ?? "#6b7280";
  const title = chapter?.title ?? folder?.name ?? subject.name;
  const description = chapter
    ? chapter.description
    : folder
      ? folder.description
      : subject.description;
  const ScopeIcon = chapter ? FileText : folder ? FolderIcon : BookOpen;
  const uploadHref =
    `/library?workspace=${ctx.workspaceId}&subject=${ctx.subjectId}` +
    (chapter ? `&chapter=${chapter.id}` : "");

  return (
    <header
      className="border-border relative overflow-hidden rounded-2xl border p-5 sm:p-6"
      style={{
        backgroundImage: `radial-gradient(120% 140% at 0% 0%, color-mix(in oklch, ${colour} 14%, transparent) 0%, transparent 60%)`,
      }}
    >
      <ScopeTrail space={space} tab={tab} />

      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-lg shadow-sm ring-1 ring-black/5"
            style={{ backgroundColor: `color-mix(in oklch, ${colour} 22%, var(--background))` }}
            aria-hidden="true"
          >
            {!folder && !chapter && subject.icon ? (
              subject.icon
            ) : (
              <ScopeIcon className="h-5 w-5" style={{ color: colour }} />
            )}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight break-words">{title}</h1>
              <span className="bg-background/70 text-muted-foreground rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-wide uppercase">
                {SCOPE_LABELS[ctx.scope]}
              </span>
              {chapter ? <StatusBadge status={chapter.status} /> : null}
            </div>
            {description ? (
              <p className="text-muted-foreground mt-1 line-clamp-2 max-w-2xl text-sm break-words">
                {description}
              </p>
            ) : null}
            <p className="text-muted-foreground mt-1.5 text-sm">
              {chapter ? (
                <>
                  In {space.path.length ? space.path.map((f) => f.name).join(" / ") : subject.name}
                </>
              ) : (
                <>
                  {scopedFolders.length} {scopedFolders.length === 1 ? "folder" : "folders"}
                  {" · "}
                  {folder ? scopedChapters.length : space.chapterTotal}{" "}
                  {(folder ? scopedChapters.length : space.chapterTotal) === 1
                    ? "chapter"
                    : "chapters"}
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link href={uploadHref} className={buttonVariants({ variant: "outline" })}>
            <Upload className="mr-1 h-4 w-4" aria-hidden="true" />
            Upload documents
          </Link>
          <GenerateButton
            preset={
              chapter
                ? { type: "chapter", id: chapter.id, label: chapter.title }
                : folder
                  ? { type: "folder", id: folder.id, label: folder.name }
                  : { type: "subject", id: subject.id, label: subject.name }
            }
          />
          {tab !== "tutor" ? (
            <Link href={environmentHref(ctx, "tutor")} className={buttonVariants()}>
              <BrainCircuit className="mr-1 h-4 w-4" aria-hidden="true" />
              Ask the AI Tutor
            </Link>
          ) : null}
        </div>
      </div>
    </header>
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

function TabBar({ ctx, tab }: { ctx: LearningContext; tab: EnvironmentTab }) {
  return (
    <nav
      aria-label={`${SCOPE_LABELS[ctx.scope]} sections`}
      className="bg-background/80 supports-[backdrop-filter]:bg-background/60 sticky -top-6 z-20 -mx-6 border-b px-6 backdrop-blur"
    >
      <ul className="-mb-px flex [scrollbar-width:none] gap-1 overflow-x-auto">
        {ENVIRONMENT_TABS.map((t) => {
          const Icon = TAB_ICONS[t.id];
          const current = t.id === tab;
          return (
            <li key={t.id} className="shrink-0">
              <Link
                href={environmentHref(ctx, t.id)}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "focus-visible:ring-ring flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:outline-none",
                  current
                    ? "border-primary text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:border-border border-transparent",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
