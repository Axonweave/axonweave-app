"use client";

/**
 * Renders one tab of a learning environment. Each tool receives the learning context instead of
 * asking for a subject again. Where a tool's API cannot narrow to the current level, it shows the
 * nearest level it supports and says so (no silent widening, no invented filtering).
 */
import { Info } from "lucide-react";
import { notFound } from "next/navigation";
import { KnowledgeExplorer } from "@/features/knowledge/knowledge-explorer";
import { IntelligenceView } from "@/features/knowledge/intelligence-view";
import { ResearchStudio } from "@/features/research/research-studio";
import { ProgressView } from "@/features/revision/progress-view";
import { RevisionCentre } from "@/features/revision/revision-centre";
import {
  ENVIRONMENT_TABS,
  SCOPE_LABELS,
  appliedScope,
  environmentHref,
  type ContextTool,
  type EnvironmentTab as Tab,
} from "@/lib/learning-context";
import { ChapterContent } from "./chapter-content";
import { ContentTab } from "./content-tab";
import { OverviewTab } from "./overview-tab";
import { ScopedMaterials } from "./scoped-materials";
import { useLearningSpace, type LearningSpace } from "./space-provider";
import { TutorTab } from "./tutor-tab";

export const isEnvironmentTab = (t: string): t is Tab => ENVIRONMENT_TABS.some((x) => x.id === t);

/** Maps a URL segment (e.g. "graph") to its tab, or null for an unknown segment. */
export function tabFromSegment(segment: string): Tab | null {
  return ENVIRONMENT_TABS.find((t) => t.segment === segment && segment !== "")?.id ?? null;
}

export function EnvironmentTabBySegment({ segment }: { segment: string }) {
  const tab = tabFromSegment(segment);
  if (!tab) notFound();
  return <EnvironmentTab tab={tab} />;
}

export function EnvironmentTab({ tab }: { tab: Tab }) {
  const space = useLearningSpace();
  switch (tab) {
    case "overview":
      return <OverviewTab />;
    case "content":
      return space.chapter ? (
        <ChapterContent />
      ) : (
        <div className="space-y-8">
          <ContentTab />
          <section aria-labelledby="materials-heading" className="space-y-3">
            <h2 id="materials-heading" className="text-lg font-semibold">
              Learning materials
            </h2>
            <ScopedMaterials />
          </section>
        </div>
      );
    case "tutor":
      return <TutorTab />;
    default:
      return <ToolTab tool={tab} space={space} />;
  }
}

function ToolTab({ tool, space }: { tool: ContextTool; space: LearningSpace }) {
  const { ctx, subject } = space;
  const { applied, widened } = appliedScope(tool, ctx);
  const here = space.chapter?.title ?? space.folder?.name ?? subject.name;
  const shownName = applied.scope === "workspace" ? space.workspace.name : subject.name;
  // A remount per context keeps each tool's internal state (filters, selection) from leaking.
  const key = `${tool}:${applied.workspaceId}:${applied.subjectId ?? ""}:${applied.chapterId ?? ""}`;

  return (
    <div className="space-y-4">
      {widened ? (
        <p
          className="border-border bg-muted/40 text-muted-foreground flex items-start gap-2 rounded-lg border px-3 py-2 text-sm"
          role="note"
        >
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {TOOL_NAMES[tool]} can’t be narrowed to a single {ctx.scope} yet, so this shows the
            whole {SCOPE_LABELS[applied.scope].toLowerCase()}{" "}
            <span className="text-foreground font-medium">{shownName}</span> rather than just{" "}
            <span className="text-foreground font-medium">{here}</span>.
          </span>
        </p>
      ) : null}
      <div key={key}>{renderTool(tool, space, applied)}</div>
    </div>
  );
}

const TOOL_NAMES: Record<ContextTool, string> = {
  tutor: "The AI Tutor",
  graph: "The knowledge graph",
  intelligence: "Learner intelligence",
  revision: "Revision",
  research: "Research Studio",
  progress: "Progress",
};

function renderTool(
  tool: ContextTool,
  space: LearningSpace,
  applied: ReturnType<typeof appliedScope>["applied"],
) {
  const { subject } = space;
  switch (tool) {
    case "graph":
      return (
        <KnowledgeExplorer
          scope={{ workspaceId: applied.workspaceId, subjectId: applied.subjectId }}
        />
      );
    case "intelligence":
      return (
        <IntelligenceView
          scope={{ workspaceId: applied.workspaceId, subjectId: applied.subjectId }}
          progressHref={environmentHref(space.ctx, "progress")}
        />
      );
    case "revision":
      return (
        <RevisionCentre
          scope={{
            subject_id: subject.id,
            chapter_id: applied.chapterId,
            label: applied.chapterId ? (space.chapter?.title ?? subject.name) : subject.name,
            // sessions can only be narrowed to a subject, so be explicit at chapter level
            sessionLabel: applied.chapterId
              ? `Start a ${subject.name} session`
              : `Revise ${subject.name}`,
          }}
        />
      );
    case "research":
      return <ResearchStudio workspaceId={applied.workspaceId} />;
    case "progress":
      return (
        <ProgressView
          locked={{
            workspace_id: applied.workspaceId,
            subject_id: applied.subjectId,
            chapter_id: applied.chapterId,
          }}
        />
      );
    default:
      return null;
  }
}
