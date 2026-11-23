"use client";

/**
 * Overview of a subject, folder or chapter, laid out as three calm rows:
 *   1. what to do next (continue learning) beside what is due today,
 *   2. the learning tools, colour-coded,
 *   3. what is inside (folders and chapters) or the previous/next chapter.
 * Every figure comes from the API or from the learner's own chapter labels; nothing is estimated.
 */
import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  FileText,
  Folder as FolderIcon,
  Play,
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
import { DEFAULT_SUBJECT_COLOUR, TAB_ICONS } from "./environment-shell";
import { useScopedDocuments, useScopedMaterials } from "./scoped-materials";
import { useLearningSpace, type LearningSpace } from "./space-provider";
import { TONES } from "./tones";
import type { Chapter, Folder } from "@/types/api";

export function OverviewTab() {
  const space = useLearningSpace();
  return (
    <div className="space-y-8">
      <div className="grid gap-5 lg:grid-cols-3">
        <ContinueCard space={space} />
        <TodayCard space={space} />
      </div>
      <ToolLauncher ctx={space.ctx} name={scopeName(space)} />
      {space.chapter ? <ChapterNeighbours space={space} /> : <StructurePreview space={space} />}
    </div>
  );
}

const scopeName = (s: LearningSpace) => s.chapter?.title ?? s.folder?.name ?? s.subject.name;
const colourOf = (s: LearningSpace) => s.subject.colour ?? DEFAULT_SUBJECT_COLOUR;

function SectionTitle({
  id,
  children,
  action,
}: {
  id: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 id={id} className="text-base font-semibold tracking-tight">
        {children}
      </h2>
      {action}
    </div>
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

/** Circular progress; the number in the middle is the real share of chapters marked completed. */
function Ring({ pct, colour }: { pct: number; colour: string }) {
  const r = 30;
  const c = 2 * Math.PI * r;
  return (
    <div
      className="relative h-20 w-20 shrink-0"
      role="img"
      aria-label={`${pct}% of chapters marked completed`}
    >
      <svg viewBox="0 0 72 72" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle
          cx="36"
          cy="36"
          r={r}
          fill="none"
          strokeWidth="7"
          className="stroke-black/5 dark:stroke-white/10"
        />
        <circle
          cx="36"
          cy="36"
          r={r}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          stroke={colour}
          strokeDasharray={c}
          strokeDashoffset={c - (pct / 100) * c}
          className="transition-[stroke-dashoffset] duration-700"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-lg font-bold tabular-nums">
        {pct}%
      </span>
    </div>
  );
}

function ContinueCard({ space }: { space: LearningSpace }) {
  const { ctx, scopedChapters, chapter, folders, subject } = space;
  const colour = colourOf(space);
  const mastery = useMastery(ctx);
  const total = scopedChapters.length;
  const completed = scopedChapters.filter((c) => c.status === "completed").length;
  const pct = total ? Math.round((completed / total) * 100) : 0;
  const next = chapter ? null : nextChapter(scopedChapters);
  const chapterHref = (c: Chapter) =>
    environmentHref(
      makeContext({ workspaceId: ctx.workspaceId, subjectId: subject.id, chapterId: c.id }),
    );
  const folderName = (c: Chapter) => folders.find((f) => f.id === c.folder_id)?.name;

  return (
    <section
      aria-labelledby="continue-heading"
      className="relative overflow-hidden rounded-3xl border p-6 shadow-sm lg:col-span-2"
      style={{
        backgroundImage: `linear-gradient(135deg, color-mix(in oklch, ${colour} 14%, var(--card)) 0%, var(--card) 70%)`,
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2 id="continue-heading" className="text-muted-foreground text-sm font-medium">
            {chapter
              ? "Study this chapter"
              : next?.resume
                ? "Pick up where you left off"
                : "Continue learning"}
          </h2>

          {chapter ? (
            <>
              <p className="mt-1 text-xl font-semibold tracking-tight">{chapter.title}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                Every tool below already uses this chapter as its context.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  href={environmentHref(ctx, "tutor")}
                  className={buttonVariants({ size: "lg" })}
                >
                  <Play aria-hidden="true" />
                  Start studying
                </Link>
                <Link
                  href={environmentHref(ctx, "revision")}
                  className={buttonVariants({ variant: "outline", size: "lg" })}
                >
                  Revise
                </Link>
              </div>
            </>
          ) : next ? (
            <>
              <p className="mt-1 truncate text-xl font-semibold tracking-tight">
                {next.chapter.title}
              </p>
              {folderName(next.chapter) ? (
                <p className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-sm">
                  <FolderIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  {folderName(next.chapter)}
                </p>
              ) : null}
              <Link
                href={chapterHref(next.chapter)}
                className={cn(buttonVariants({ size: "lg" }), "mt-4")}
              >
                <Play aria-hidden="true" />
                {next.resume ? "Continue" : "Start"}
              </Link>
            </>
          ) : (
            <p className="mt-2 text-sm">
              {total === 0
                ? "Add your first chapter from the Content tab to get started."
                : "Every chapter here is marked completed. Revise to keep it fresh."}
            </p>
          )}
        </div>
        {!chapter && total > 0 ? <Ring pct={pct} colour={colour} /> : null}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-black/5 pt-4 text-sm dark:border-white/10">
        {!chapter && total > 0 ? (
          <span className="text-muted-foreground">
            <span className="text-foreground font-semibold tabular-nums">
              {completed}/{total}
            </span>{" "}
            chapters marked completed
          </span>
        ) : null}
        <Link
          href={environmentHref(ctx, "intelligence")}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5"
        >
          Understanding{mastery.widened ? " (subject)" : ""}:{" "}
          <span className="text-foreground font-semibold">
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

// ── Today ────────────────────────────────────────────────────────────────────

function TodayCard({ space }: { space: LearningSpace }) {
  const { ctx } = space;
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
  const a = analytics.data;
  const due = a ? a.due_today + a.overdue : null;

  return (
    <section
      aria-labelledby="today-heading"
      className="bg-card flex flex-col rounded-3xl border p-6 shadow-sm"
    >
      <h2 id="today-heading" className="text-muted-foreground text-sm font-medium">
        Today{progressScope.widened ? " · whole subject" : ""}
      </h2>
      <div className="mt-2 flex items-center gap-3">
        <span
          className={cn(
            "flex h-11 w-11 items-center justify-center rounded-2xl",
            TONES.revision.chip,
          )}
        >
          <CalendarClock className={cn("h-5 w-5", TONES.revision.icon)} aria-hidden="true" />
        </span>
        <div>
          <p className="text-3xl font-bold tabular-nums">{due ?? "–"}</p>
          <p className="text-muted-foreground text-xs">
            {a ? `cards to review · ${a.overdue} overdue` : "cards to review"}
          </p>
        </div>
      </div>
      <Link
        href={environmentHref(ctx, "revision")}
        className={cn(buttonVariants({ variant: "secondary" }), "mt-4 w-full")}
      >
        {due ? "Revise now" : "Open revision"}
      </Link>

      <dl className="mt-auto grid grid-cols-2 gap-3 pt-5 text-sm">
        <Mini
          href={environmentHref(ctx, "content")}
          icon={FileText}
          tone={TONES.content}
          label="Documents"
          value={docs.data?.total}
        />
        <Mini
          href={environmentHref(ctx, "content")}
          icon={Sparkles}
          tone={TONES.tutor}
          label="Materials"
          value={materials.data?.total}
        />
      </dl>
      {space.chapter && a?.average_quiz_percentage != null ? (
        <p className="text-muted-foreground mt-3 text-xs">
          Average quiz score here:{" "}
          <span className="text-foreground font-semibold">
            {Math.round(a.average_quiz_percentage)}%
          </span>{" "}
          over {a.quiz_attempts} attempts
        </p>
      ) : null}
    </section>
  );
}

function Mini({
  href,
  icon: Icon,
  tone,
  label,
  value,
}: {
  href: string;
  icon: React.ElementType;
  tone: (typeof TONES)[keyof typeof TONES];
  label: string;
  value: number | undefined;
}) {
  return (
    <Link
      href={href}
      className="hover:bg-muted/60 -m-1 flex items-center gap-2 rounded-xl p-1 transition-colors"
    >
      <span className={cn("flex h-8 w-8 items-center justify-center rounded-lg", tone.chip)}>
        <Icon className={cn("h-4 w-4", tone.icon)} aria-hidden="true" />
      </span>
      <span>
        <dt className="text-muted-foreground text-xs">{label}</dt>
        <dd className="font-semibold tabular-nums">{value ?? "–"}</dd>
      </span>
    </Link>
  );
}

// ── Tools ────────────────────────────────────────────────────────────────────

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
      <SectionTitle id="tools-heading">Learning tools</SectionTitle>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(Object.keys(TOOL_COPY) as ContextTool[]).map((tool) => {
          const Icon = TAB_ICONS[tool];
          const tone = TONES[tool];
          const { widened, applied } = appliedScope(tool, ctx);
          return (
            <li key={tool}>
              <Link
                href={environmentHref(ctx, tool)}
                className={cn(
                  "group bg-card focus-visible:ring-ring flex h-full items-center gap-3 rounded-2xl border bg-gradient-to-br to-transparent p-4 transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:outline-none",
                  tone.wash,
                )}
              >
                <span
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
                    tone.chip,
                  )}
                >
                  <Icon className={cn("h-5 w-5", tone.icon)} aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold">{TOOL_COPY[tool].title}</span>
                  <span className="text-muted-foreground block truncate text-sm">
                    {TOOL_COPY[tool].text(name)}
                  </span>
                  {widened ? (
                    <span className="text-muted-foreground mt-0.5 block text-[11px]">
                      Shows the {applied.scope} level
                    </span>
                  ) : null}
                </span>
                <ArrowRight
                  className="text-muted-foreground h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5"
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

// ── Structure ────────────────────────────────────────────────────────────────

function StructurePreview({ space }: { space: LearningSpace }) {
  const { ctx, subject, folders, chapters, folder } = space;
  const colour = colourOf(space);
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
        action={
          <Link
            href={environmentHref(ctx, "content")}
            className="text-primary text-sm font-medium hover:underline"
          >
            Manage content
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
              <Link
                href={at({ folderId: f.id })}
                className="bg-card focus-visible:ring-ring group block rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="flex items-center gap-3">
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                    style={{ backgroundColor: `color-mix(in oklch, ${colour} 14%, transparent)` }}
                  >
                    <FolderIcon className="h-5 w-5" style={{ color: colour }} aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-semibold">{f.name}</span>
                    <span className="text-muted-foreground block text-xs">
                      {s.total} {s.total === 1 ? "chapter" : "chapters"} · {s.done} completed
                    </span>
                  </span>
                </span>
                <span
                  className="bg-muted mt-3 block h-1.5 overflow-hidden rounded-full"
                  aria-hidden="true"
                >
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${pct}%`, backgroundColor: colour }}
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
              className="bg-card focus-visible:ring-ring flex items-center gap-3 rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:outline-none"
            >
              <span
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                  TONES.content.chip,
                )}
              >
                <FileText className={cn("h-5 w-5", TONES.content.icon)} aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1 truncate font-semibold">{c.title}</span>
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
    "bg-card focus-visible:ring-ring flex min-w-0 flex-1 items-center gap-3 rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:outline-none";
  return (
    <nav aria-label="Chapter navigation" className="flex flex-col gap-3 sm:flex-row">
      {prev ? (
        <Link href={href(prev)} className={card}>
          <ChevronLeft className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
          <span className="min-w-0">
            <span className="text-muted-foreground block text-xs">Previous chapter</span>
            <span className="block truncate font-semibold">{prev.title}</span>
          </span>
        </Link>
      ) : (
        <span className="hidden flex-1 sm:block" />
      )}
      {next ? (
        <Link href={href(next)} className={cn(card, "justify-end text-right")}>
          <span className="min-w-0">
            <span className="text-muted-foreground block text-xs">Next chapter</span>
            <span className="block truncate font-semibold">{next.title}</span>
          </span>
          <ChevronRight className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
        </Link>
      ) : null}
    </nav>
  );
}
