"use client";

/**
 * Overview of a subject, folder or chapter. Every figure comes from the API or from the learner's
 * own chapter labels; nothing is estimated. A figure the backend cannot narrow to this scope is
 * either labelled with the scope it covers or left out.
 */
import Link from "next/link";
import {
  ArrowRight,
  BookOpenCheck,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  FileText,
  Folder as FolderIcon,
  Gauge,
  PlayCircle,
  Sparkles,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { learnerApi } from "@/lib/api/learner";
import { analyticsApi } from "@/lib/api/revision";
import {
  appliedScope,
  environmentHref,
  makeContext,
  type ContextTool,
  type LearningContext,
} from "@/lib/learning-context";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/features/academic/status";
import { descendantIds } from "@/features/academic/tree";
import { TAB_ICONS } from "./environment-shell";
import { useScopedDocuments, useScopedMaterials } from "./scoped-materials";
import { useLearningSpace, type LearningSpace } from "./space-provider";
import type { Chapter, Folder } from "@/types/api";

export function OverviewTab() {
  const space = useLearningSpace();
  return (
    <div className="space-y-6">
      <StatsRow space={space} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <ContinueCard space={space} />
        <ToolLauncher ctx={space.ctx} name={scopeName(space)} />
      </div>
      {space.chapter ? <ChapterNeighbours space={space} /> : <StructurePreview space={space} />}
    </div>
  );
}

const scopeName = (s: LearningSpace) => s.chapter?.title ?? s.folder?.name ?? s.subject.name;

// ── Stats ────────────────────────────────────────────────────────────────────

function Stat({
  label,
  value,
  hint,
  icon: Icon,
  href,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon: React.ElementType;
  href?: string;
}) {
  const body = (
    <>
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {label}
      </div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {hint ? <div className="text-muted-foreground mt-0.5 truncate text-xs">{hint}</div> : null}
    </>
  );
  const cls =
    "border-border bg-card block rounded-xl border p-4 transition-colors focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none";
  return href ? (
    <Link href={href} className={cn(cls, "hover:border-foreground/20 hover:bg-muted/40")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

const Dash = () => <span className="text-muted-foreground">–</span>;

function StatsRow({ space }: { space: LearningSpace }) {
  const { ctx, scopedChapters, scopedFolders, chapter } = space;
  const docs = useScopedDocuments(1);
  const materials = useScopedMaterials(1);

  const progressScope = appliedScope("progress", ctx);
  const analytics = useAsync(
    () =>
      analyticsApi.overview({
        subject_id: progressScope.applied.subjectId,
        chapter_id: progressScope.applied.chapterId,
      }),
    [progressScope.applied.subjectId, progressScope.applied.chapterId],
  );

  const total = scopedChapters.length;
  const completed = scopedChapters.filter((c) => c.status === "completed").length;
  const pct = total ? Math.round((completed / total) * 100) : null;

  return (
    <section
      aria-label="At a glance"
      className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
    >
      {chapter ? (
        <Stat label="Status" icon={BookOpenCheck} value={<StatusBadge status={chapter.status} />} />
      ) : (
        <>
          <Stat
            label="Folders"
            icon={FolderIcon}
            value={scopedFolders.length}
            href={environmentHref(ctx, "content")}
          />
          <Stat
            label="Chapters"
            icon={FileText}
            value={total}
            href={environmentHref(ctx, "content")}
          />
        </>
      )}
      {!chapter && (
        <Stat
          label="Chapters completed"
          icon={BookOpenCheck}
          value={pct === null ? <Dash /> : `${pct}%`}
          hint={total ? `${completed} of ${total}, as you marked them` : "No chapters yet"}
          href={environmentHref(ctx, "progress")}
        />
      )}
      <Stat
        label="Documents"
        icon={FileText}
        value={docs.data ? docs.data.total : <Dash />}
        href={environmentHref(ctx, "content")}
      />
      <Stat
        label="Study materials"
        icon={Sparkles}
        value={materials.data ? materials.data.total : <Dash />}
        href={environmentHref(ctx, "content")}
      />
      <Stat
        label="Cards due today"
        icon={CalendarClock}
        value={analytics.data ? analytics.data.due_today : <Dash />}
        hint={
          analytics.data
            ? `${analytics.data.overdue} overdue${progressScope.widened ? " · whole subject" : ""}`
            : undefined
        }
        href={environmentHref(ctx, "revision")}
      />
      {chapter && (
        <Stat
          label="Average quiz score"
          icon={Gauge}
          value={
            analytics.data?.average_quiz_percentage != null ? (
              `${Math.round(analytics.data.average_quiz_percentage)}%`
            ) : (
              <Dash />
            )
          }
          hint={analytics.data ? `${analytics.data.quiz_attempts} attempts` : undefined}
          href={environmentHref(ctx, "progress")}
        />
      )}
    </section>
  );
}

// ── Continue learning ────────────────────────────────────────────────────────

/** The chapter to pick up next: the most recently touched in-progress one, else the first not started. */
export function nextChapter(chapters: Chapter[]): { chapter: Chapter; resume: boolean } | null {
  const inProgress = chapters
    .filter((c) => c.status === "in_progress")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  if (inProgress[0]) return { chapter: inProgress[0], resume: true };
  const notStarted = [...chapters]
    .filter((c) => c.status === "not_started")
    .sort((a, b) => a.display_order - b.display_order);
  return notStarted[0] ? { chapter: notStarted[0], resume: false } : null;
}

function ContinueCard({ space }: { space: LearningSpace }) {
  const { ctx, scopedChapters, chapter, folders, subject } = space;
  const mastery = useMastery(ctx);
  const total = scopedChapters.length;
  const completed = scopedChapters.filter((c) => c.status === "completed").length;
  const pct = total ? Math.round((completed / total) * 100) : 0;
  const next = chapter ? null : nextChapter(scopedChapters);
  const chapterCtx = (c: Chapter) =>
    makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, chapterId: c.id });
  const folderName = (c: Chapter) => folders.find((f) => f.id === c.folder_id)?.name;

  return (
    <section
      aria-labelledby="continue-heading"
      className="border-border bg-card relative overflow-hidden rounded-2xl border p-5"
    >
      <h2
        id="continue-heading"
        className="text-muted-foreground text-xs font-semibold tracking-wider uppercase"
      >
        {chapter ? "This chapter" : "Continue learning"}
      </h2>

      {chapter ? (
        <div className="mt-3 space-y-3">
          <p className="text-sm">
            Ask the tutor about this chapter, generate flashcards from it, or revise its cards.
            Every tool above already uses this chapter as its context.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href={environmentHref(ctx, "tutor")} className={buttonVariants()}>
              Start studying
              <ArrowRight className="ml-1 h-4 w-4" aria-hidden="true" />
            </Link>
            <Link
              href={environmentHref(ctx, "revision")}
              className={buttonVariants({ variant: "outline" })}
            >
              Revise
            </Link>
          </div>
        </div>
      ) : next ? (
        <Link
          href={environmentHref(chapterCtx(next.chapter))}
          className="group hover:bg-muted/50 focus-visible:ring-ring -mx-2 mt-2 flex items-center gap-3 rounded-xl p-2 transition-colors focus-visible:ring-2 focus-visible:outline-none"
        >
          <PlayCircle
            className="text-primary h-9 w-9 shrink-0"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1">
            <span className="text-muted-foreground block truncate text-xs">
              {next.resume ? "Pick up where you left off" : "Start next"}
              {folderName(next.chapter) ? ` · ${folderName(next.chapter)}` : ""}
            </span>
            <span className="block truncate font-medium">{next.chapter.title}</span>
          </span>
          <ArrowRight
            className="text-muted-foreground h-4 w-4 transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </Link>
      ) : (
        <p className="text-muted-foreground mt-3 text-sm">
          {total === 0
            ? "Add a chapter in the Content tab to start."
            : "Every chapter here is marked completed. Revise to keep it fresh."}
        </p>
      )}

      {!chapter && total > 0 && (
        <div className="mt-4">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-muted-foreground">Chapters marked completed</span>
            <span className="font-medium tabular-nums">
              {completed}/{total}
            </span>
          </div>
          <div
            className="bg-muted mt-1.5 h-2 overflow-hidden rounded-full"
            role="progressbar"
            aria-label="Chapters marked completed"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
          >
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${pct}%`, backgroundColor: subject.colour ?? "var(--primary)" }}
            />
          </div>
        </div>
      )}

      <div className="border-border mt-4 border-t pt-3 text-sm">
        <Link
          href={environmentHref(ctx, "intelligence")}
          className="hover:text-foreground text-muted-foreground flex items-center justify-between gap-2 underline-offset-4 hover:underline"
        >
          <span>
            Understanding{mastery.widened ? " (whole subject)" : ""}:{" "}
            <span className="text-foreground font-medium">
              {mastery.loading
                ? "…"
                : mastery.assessed
                  ? `${mastery.secure} of ${mastery.assessed} assessed concepts proficient or strong`
                  : "not assessed yet"}
            </span>
          </span>
          <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

function useMastery(ctx: LearningContext) {
  const { applied, widened } = appliedScope("intelligence", ctx);
  const dash = useAsync(
    () =>
      learnerApi.dashboard({ workspace_id: applied.workspaceId, subject_id: applied.subjectId }),
    [applied.workspaceId, applied.subjectId],
  );
  const o = dash.data?.overview;
  return {
    loading: dash.loading && !dash.data,
    assessed: o?.assessed ?? 0,
    secure: (o?.strong ?? 0) + (o?.proficient ?? 0),
    widened,
  };
}

// ── Tools ────────────────────────────────────────────────────────────────────

const TOOL_COPY: Record<ContextTool, { title: string; text: (name: string) => string }> = {
  tutor: { title: "AI Tutor", text: (n) => `Ask questions answered from ${n}'s documents.` },
  graph: { title: "Knowledge Graph", text: () => "See the concepts and how they connect." },
  intelligence: {
    title: "Intelligence",
    text: () => "What you understand and where the gaps are.",
  },
  revision: { title: "Revision", text: () => "Spaced flashcard review for this material." },
  research: { title: "Research", text: () => "Projects, papers and evidence." },
  progress: { title: "Progress", text: () => "Quiz results, reviews and streaks." },
};

function ToolLauncher({ ctx, name }: { ctx: LearningContext; name: string }) {
  return (
    <section aria-labelledby="tools-heading" className="space-y-3">
      <h2
        id="tools-heading"
        className="text-muted-foreground text-xs font-semibold tracking-wider uppercase"
      >
        Learning tools
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {(Object.keys(TOOL_COPY) as ContextTool[]).map((tool) => {
          const Icon = TAB_ICONS[tool];
          const { widened, applied } = appliedScope(tool, ctx);
          return (
            <li key={tool}>
              <Link
                href={environmentHref(ctx, tool)}
                className="group border-border bg-card hover:border-foreground/20 hover:bg-muted/40 focus-visible:ring-ring flex h-full flex-col rounded-xl border p-4 transition-all focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="flex items-center justify-between">
                  <span className="bg-primary/10 text-primary flex h-8 w-8 items-center justify-center rounded-lg">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <ArrowRight
                    className="text-muted-foreground h-4 w-4 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100"
                    aria-hidden="true"
                  />
                </span>
                <span className="mt-3 font-medium">{TOOL_COPY[tool].title}</span>
                <span className="text-muted-foreground mt-0.5 text-sm">
                  {TOOL_COPY[tool].text(name)}
                </span>
                {widened ? (
                  <span className="text-muted-foreground mt-2 text-[11px]">
                    Shows the {applied.scope} level
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── Structure ────────────────────────────────────────────────────────────────

function StructurePreview({ space }: { space: LearningSpace }) {
  const { ctx, subject, folders, chapters, folder } = space;
  const parentId = folder?.id ?? null;
  const children = folders
    .filter((f) => (f.parent_folder_id ?? null) === parentId)
    .sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
  const loose = chapters
    .filter((c) => (c.folder_id ?? null) === parentId)
    .sort((a, b) => a.display_order - b.display_order);
  if (children.length === 0 && loose.length === 0) return null;

  const statsFor = (f: Folder) => {
    const ids = descendantIds(folders, f.id);
    ids.add(f.id);
    const inside = chapters.filter((c) => c.folder_id && ids.has(c.folder_id));
    return { total: inside.length, done: inside.filter((c) => c.status === "completed").length };
  };
  const at = (ids: { folderId?: string; chapterId?: string }) =>
    environmentHref(makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, ...ids }));

  return (
    <section aria-labelledby="structure-preview" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2
          id="structure-preview"
          className="text-muted-foreground text-xs font-semibold tracking-wider uppercase"
        >
          {folder ? "Inside this folder" : "Folders and chapters"}
        </h2>
        <Link
          href={environmentHref(ctx, "content")}
          className="text-primary text-sm underline-offset-4 hover:underline"
        >
          Manage content
        </Link>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {children.map((f) => {
          const s = statsFor(f);
          const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
          return (
            <li key={f.id}>
              <Link
                href={at({ folderId: f.id })}
                className="border-border bg-card hover:border-foreground/20 focus-visible:ring-ring block rounded-xl border p-4 transition-colors focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="flex items-center gap-2 font-medium">
                  <FolderIcon
                    className="text-muted-foreground h-4 w-4 shrink-0"
                    aria-hidden="true"
                  />
                  <span className="truncate">{f.name}</span>
                </span>
                <span className="text-muted-foreground mt-1 block text-xs">
                  {s.total} {s.total === 1 ? "chapter" : "chapters"} · {s.done} completed
                </span>
                <span
                  className="bg-muted mt-2 block h-1.5 overflow-hidden rounded-full"
                  aria-hidden="true"
                >
                  <span
                    className="block h-full rounded-full"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: subject.colour ?? "var(--primary)",
                    }}
                  />
                </span>
              </Link>
            </li>
          );
        })}
        {loose.slice(0, 9).map((c) => (
          <li key={c.id}>
            <Link
              href={at({ chapterId: c.id })}
              className="border-border bg-card hover:border-foreground/20 focus-visible:ring-ring flex items-center gap-2 rounded-xl border p-4 transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <FileText className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate font-medium">{c.title}</span>
              <StatusBadge status={c.status} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Previous / next chapter in the same folder, so a learner can move through material in order. */
function ChapterNeighbours({ space }: { space: LearningSpace }) {
  const { ctx, chapter, chapters, subject } = space;
  if (!chapter) return null;
  const siblings = chapters
    .filter((c) => (c.folder_id ?? null) === (chapter.folder_id ?? null))
    .sort((a, b) => a.display_order - b.display_order);
  const i = siblings.findIndex((c) => c.id === chapter.id);
  const prev = i > 0 ? siblings[i - 1] : null;
  const next = i >= 0 && i < siblings.length - 1 ? siblings[i + 1] : null;
  if (!prev && !next) return null;
  const href = (c: Chapter) =>
    environmentHref(
      makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, chapterId: c.id }),
    );
  const card =
    "border-border bg-card hover:border-foreground/20 focus-visible:ring-ring flex min-w-0 flex-1 items-center gap-3 rounded-xl border p-4 transition-colors focus-visible:ring-2 focus-visible:outline-none";
  return (
    <nav aria-label="Chapter navigation" className="flex flex-col gap-3 sm:flex-row">
      {prev ? (
        <Link href={href(prev)} className={card}>
          <ChevronLeft className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
          <span className="min-w-0">
            <span className="text-muted-foreground block text-xs">Previous chapter</span>
            <span className="block truncate font-medium">{prev.title}</span>
          </span>
        </Link>
      ) : (
        <span className="hidden flex-1 sm:block" />
      )}
      {next ? (
        <Link href={href(next)} className={cn(card, "justify-end text-right")}>
          <span className="min-w-0">
            <span className="text-muted-foreground block text-xs">Next chapter</span>
            <span className="block truncate font-medium">{next.title}</span>
          </span>
          <ChevronRight className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
        </Link>
      ) : null}
    </nav>
  );
}
