"use client";

/**
 * Overview of a subject, folder or chapter:
 *   1. four figures at a glance (chapters done, cards to review, documents, materials),
 *   2. the one thing to do next, with progress,
 *   3. the learning tools,
 *   4. what is inside (folders and chapters) or the previous/next chapter.
 * Every figure comes from the API or from the learner's own chapter labels; nothing is estimated.
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
  Layers,
  Play,
  RotateCcw,
} from "lucide-react";
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
import { StatusBadge, statusLabel } from "@/features/academic/status";
import { descendantIds } from "@/features/academic/tree";
import { TAB_ICONS } from "./environment-shell";
import { useScopedDocuments, useScopedMaterials } from "./scoped-materials";
import { useLearningSpace, type LearningSpace } from "./space-provider";
import type { Chapter, Folder } from "@/types/api";

// ── shared look ──────────────────────────────────────────────────────────────

/** Small uppercase label above a value, as on a scoreboard. */
const CAPS = "text-[11px] font-semibold tracking-[0.12em] uppercase";
/** The one bold call to action on a screen. */
const CTA =
  "bg-signature text-signature-ink focus-visible:ring-ring inline-flex h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold transition hover:brightness-105 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none active:scale-[0.98]";
/** A quieter pill next to it. */
const PILL =
  "hover:bg-muted focus-visible:ring-ring inline-flex h-11 items-center gap-2 rounded-full border px-5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none";
const CARD = "bg-card rounded-2xl border";
const CARD_LINK =
  "bg-card hover:border-foreground/20 focus-visible:ring-ring rounded-2xl border transition-colors focus-visible:ring-2 focus-visible:outline-none";

export function OverviewTab() {
  const space = useLearningSpace();
  return (
    <div className="space-y-10">
      <StatTiles space={space} />
      <ContinueCard space={space} />
      <ToolLauncher ctx={space.ctx} name={scopeName(space)} />
      {space.chapter ? <ChapterNeighbours space={space} /> : <StructurePreview space={space} />}
    </div>
  );
}

const scopeName = (s: LearningSpace) => s.chapter?.title ?? s.folder?.name ?? s.subject.name;

function SectionTitle({
  id,
  children,
  hint,
  action,
}: {
  id: string;
  children: React.ReactNode;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-3">
      <div>
        <h2 id={id} className="font-display text-xl font-semibold">
          {children}
        </h2>
        {hint ? <p className="text-muted-foreground mt-0.5 text-sm">{hint}</p> : null}
      </div>
      {action}
    </div>
  );
}

// ── figures at a glance ─────────────────────────────────────────────────────

function useDue(ctx: LearningContext) {
  const scope = appliedScope("progress", ctx);
  const analytics = useAsync(
    () =>
      analyticsApi.overview({
        subject_id: scope.applied.subjectId,
        chapter_id: scope.applied.chapterId,
      }),
    [scope.applied.subjectId, scope.applied.chapterId],
  );
  return { data: analytics.data, widened: scope.widened };
}

function Tile({
  href,
  icon: Icon,
  label,
  value,
  hint,
}: {
  href: string;
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <Link href={href} className={cn(CARD_LINK, "group block p-4 sm:p-5")}>
      <Icon className="text-primary h-4 w-4" aria-hidden="true" />
      <p className={cn(CAPS, "text-muted-foreground mt-3")}>{label}</p>
      <p className="font-display mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint ? <p className="text-muted-foreground mt-0.5 truncate text-xs">{hint}</p> : null}
    </Link>
  );
}

const Dash = () => <span className="text-muted-foreground">–</span>;

function StatTiles({ space }: { space: LearningSpace }) {
  const { ctx, scopedChapters, chapter } = space;
  const docs = useScopedDocuments(1);
  const materials = useScopedMaterials(1);
  const due = useDue(ctx);
  const a = due.data;
  const total = scopedChapters.length;
  const completed = scopedChapters.filter((c) => c.status === "completed").length;

  return (
    <section aria-label="At a glance" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {chapter ? (
        <Tile
          href={environmentHref(ctx, "progress")}
          icon={BookOpenCheck}
          label="Status"
          value={statusLabel(chapter.status)}
          hint="As you marked it"
        />
      ) : (
        <Tile
          href={environmentHref(ctx, "progress")}
          icon={BookOpenCheck}
          label="Chapters done"
          value={
            <>
              {completed}
              <span className="text-muted-foreground text-lg">/{total}</span>
            </>
          }
          hint={total ? "As you marked them" : "No chapters yet"}
        />
      )}
      <Tile
        href={environmentHref(ctx, "revision")}
        icon={CalendarClock}
        label="Cards to review"
        value={a ? a.due_today + a.overdue : <Dash />}
        hint={a ? `${a.overdue} overdue${due.widened ? " · whole subject" : ""}` : undefined}
      />
      <Tile
        href={environmentHref(ctx, "content")}
        icon={FileText}
        label="Documents"
        value={docs.data ? docs.data.total : <Dash />}
      />
      {chapter ? (
        <Tile
          href={environmentHref(ctx, "progress")}
          icon={Gauge}
          label="Quiz average"
          value={
            a?.average_quiz_percentage != null ? (
              `${Math.round(a.average_quiz_percentage)}%`
            ) : (
              <Dash />
            )
          }
          hint={a ? `${a.quiz_attempts} attempts` : undefined}
        />
      ) : (
        <Tile
          href={environmentHref(ctx, "content")}
          icon={Layers}
          label="Study materials"
          value={materials.data ? materials.data.total : <Dash />}
        />
      )}
    </section>
  );
}

// ── continue learning ───────────────────────────────────────────────────────

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

/** Progress ring with the real count in the middle ("1/3"), drawn in the signature colour. */
function Ring({ done, total }: { done: number; total: number }) {
  const pct = total ? done / total : 0;
  const r = 42;
  const c = 2 * Math.PI * r;
  return (
    <div
      className="relative h-28 w-28 shrink-0"
      role="img"
      aria-label={`${done} of ${total} chapters marked completed`}
    >
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          strokeWidth="8"
          className="stroke-foreground/10"
        />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          className="stroke-signature transition-[stroke-dashoffset] duration-700 ease-out"
          strokeDasharray={c}
          strokeDashoffset={c - pct * c}
        />
      </svg>
      <span className="font-display absolute inset-0 flex items-center justify-center text-2xl font-semibold tabular-nums">
        {done}
        <span className="text-muted-foreground text-base">/{total}</span>
      </span>
    </div>
  );
}

function ContinueCard({ space }: { space: LearningSpace }) {
  const { ctx, scopedChapters, chapter, folders, subject } = space;
  const mastery = useMastery(ctx);
  const total = scopedChapters.length;
  const completed = scopedChapters.filter((c) => c.status === "completed").length;
  const next = chapter ? null : nextChapter(scopedChapters);
  const chapterHref = (c: Chapter) =>
    environmentHref(
      makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, chapterId: c.id }),
    );
  const folderName = (c: Chapter) => folders.find((f) => f.id === c.folder_id)?.name;

  return (
    <section
      aria-labelledby="continue-heading"
      className={cn(CARD, "relative overflow-hidden p-6 sm:p-8")}
    >
      {/* a soft lamp-light in the corner; decoration only */}
      <div
        className="pointer-events-none absolute -top-24 -right-24 h-72 w-72 rounded-full opacity-70 blur-3xl"
        style={{ background: "var(--glow)" }}
        aria-hidden="true"
      />
      <div className="relative flex flex-col-reverse gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <h2 id="continue-heading" className={cn(CAPS, "text-primary")}>
            {chapter
              ? "Study this chapter"
              : next?.resume
                ? "Pick up where you left off"
                : "Continue learning"}
          </h2>

          {chapter ? (
            <>
              <p className="font-display mt-2 text-3xl font-semibold">{chapter.title}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                Every tool below already uses this chapter as its context.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Link href={environmentHref(ctx, "tutor")} className={CTA}>
                  <Play className="h-4 w-4" aria-hidden="true" />
                  Start studying
                </Link>
                <Link href={environmentHref(ctx, "revision")} className={PILL}>
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Revise
                </Link>
              </div>
            </>
          ) : next ? (
            <>
              <p className="font-display mt-2 truncate text-3xl font-semibold">
                {next.chapter.title}
              </p>
              <p className="text-muted-foreground mt-1 flex items-center gap-1.5 text-sm">
                {folderName(next.chapter) ? (
                  <>
                    <FolderIcon className="h-3.5 w-3.5" aria-hidden="true" />
                    {folderName(next.chapter)}
                  </>
                ) : (
                  "Next chapter"
                )}
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Link href={chapterHref(next.chapter)} className={CTA}>
                  <Play className="h-4 w-4" aria-hidden="true" />
                  {next.resume ? "Continue" : "Start"}
                </Link>
                <Link href={environmentHref(ctx, "revision")} className={PILL}>
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Revise
                </Link>
              </div>
            </>
          ) : (
            <p className="font-display mt-2 text-2xl font-semibold">
              {total === 0
                ? "Add your first chapter to get started"
                : "Every chapter here is marked completed"}
            </p>
          )}
        </div>
        {!chapter && total > 0 ? <Ring done={completed} total={total} /> : null}
      </div>

      <div className="relative mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 border-t pt-4 text-sm">
        <Link
          href={environmentHref(ctx, "intelligence")}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5"
        >
          Understanding{mastery.widened ? " (subject)" : ""}:{" "}
          <span className="text-foreground font-medium">
            {mastery.loading
              ? "…"
              : mastery.assessed
                ? `${mastery.secure} of ${mastery.assessed} concepts secure`
                : "not assessed yet"}
          </span>
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
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

// ── tools ───────────────────────────────────────────────────────────────────

const TOOL_COPY: Record<ContextTool, { title: string; text: (name: string) => string }> = {
  tutor: { title: "AI Tutor", text: (n) => `Ask anything about ${n}` },
  graph: { title: "Knowledge Graph", text: () => "Concepts and how they connect" },
  intelligence: { title: "Intelligence", text: () => "Your strengths and gaps" },
  revision: { title: "Revision", text: () => "Spaced flashcard review" },
  research: { title: "Research", text: () => "Projects, papers, evidence" },
  progress: { title: "Progress", text: () => "Scores, reviews, streaks" },
};

function ToolLauncher({ ctx, name }: { ctx: LearningContext; name: string }) {
  return (
    <section aria-labelledby="tools-heading">
      <SectionTitle id="tools-heading" hint="Each one already knows where you are.">
        Learning tools
      </SectionTitle>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(Object.keys(TOOL_COPY) as ContextTool[]).map((tool) => {
          const Icon = TAB_ICONS[tool];
          const { widened, applied } = appliedScope(tool, ctx);
          return (
            <li key={tool}>
              <Link
                href={environmentHref(ctx, tool)}
                className={cn(CARD_LINK, "group flex h-full items-start gap-4 p-5")}
              >
                <span className="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                  <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="font-display block font-semibold">{TOOL_COPY[tool].title}</span>
                  <span className="text-muted-foreground mt-0.5 block text-sm">
                    {TOOL_COPY[tool].text(name)}
                  </span>
                  {widened ? (
                    <span className={cn(CAPS, "text-muted-foreground mt-2 block text-[10px]")}>
                      Shows the {applied.scope} level
                    </span>
                  ) : null}
                </span>
                <ArrowRight
                  className="text-muted-foreground group-hover:text-foreground mt-1 h-4 w-4 shrink-0 transition group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── structure ───────────────────────────────────────────────────────────────

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
    <section aria-labelledby="structure-preview">
      <SectionTitle
        id="structure-preview"
        hint={folder ? undefined : "Open a folder or chapter to focus on it."}
        action={
          <Link
            href={environmentHref(ctx, "content")}
            className="hover:bg-muted inline-flex h-9 items-center gap-1.5 rounded-full border px-4 text-sm font-medium transition-colors"
          >
            Manage content
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        }
      >
        {folder ? "Inside this folder" : "Folders and chapters"}
      </SectionTitle>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {children.map((f) => {
          const s = statsFor(f);
          const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
          return (
            <li key={f.id}>
              <Link href={at({ folderId: f.id })} className={cn(CARD_LINK, "group block p-5")}>
                <span className="flex items-start justify-between gap-3">
                  <span className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                    <FolderIcon
                      className="text-muted-foreground h-[18px] w-[18px]"
                      aria-hidden="true"
                    />
                  </span>
                  <span className={cn(CAPS, "text-muted-foreground tabular-nums")}>
                    {s.done}/{s.total} done
                  </span>
                </span>
                <span className="font-display mt-4 block truncate text-lg font-semibold">
                  {f.name}
                </span>
                <span className="text-muted-foreground block text-sm">
                  {s.total} {s.total === 1 ? "chapter" : "chapters"}
                </span>
                <span
                  className="bg-muted mt-4 block h-1.5 overflow-hidden rounded-full"
                  aria-hidden="true"
                >
                  <span
                    className="bg-signature block h-full rounded-full transition-[width] duration-700"
                    style={{ width: `${pct}%` }}
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
              className={cn(CARD_LINK, "flex h-full items-center gap-3 p-5")}
            >
              <span className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                <FileText className="text-muted-foreground h-[18px] w-[18px]" aria-hidden="true" />
              </span>
              <span className="font-display min-w-0 flex-1 truncate font-semibold">{c.title}</span>
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
  const card = cn(CARD_LINK, "flex min-w-0 flex-1 items-center gap-3 p-5");
  return (
    <nav aria-label="Chapter navigation" className="flex flex-col gap-3 sm:flex-row">
      {prev ? (
        <Link href={href(prev)} className={card}>
          <ChevronLeft className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
          <span className="min-w-0">
            <span className={cn(CAPS, "text-muted-foreground block")}>Previous</span>
            <span className="font-display block truncate font-semibold">{prev.title}</span>
          </span>
        </Link>
      ) : (
        <span className="hidden flex-1 sm:block" />
      )}
      {next ? (
        <Link href={href(next)} className={cn(card, "justify-end text-right")}>
          <span className="min-w-0">
            <span className={cn(CAPS, "text-muted-foreground block")}>Next</span>
            <span className="font-display block truncate font-semibold">{next.title}</span>
          </span>
          <ChevronRight className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
        </Link>
      ) : null}
    </nav>
  );
}
