/**
 * Learning context: the one place that decides "what am I studying right now".
 *
 * A context is a position in the academic hierarchy (workspace > subject > folder > chapter).
 * Every learning tool (AI Tutor, Knowledge Graph, Learner Intelligence, Revision, Research Studio,
 * Progress) receives a context instead of asking the learner to pick a subject again.
 *
 * Ids here only select what to show. Authorization always happens in the backend; a context built
 * from a URL the user edited can never reach data the user does not own (the API answers 404).
 */
import type { ConversationScope } from "@/lib/api/ai";

export type LearningScope = "workspace" | "subject" | "folder" | "chapter";

export interface LearningContext {
  workspaceId: string;
  subjectId?: string;
  folderId?: string;
  chapterId?: string;
  scope: LearningScope;
}

/** The tabs every learning environment offers. */
export type EnvironmentTab =
  | "overview"
  | "content"
  | "graph"
  | "intelligence"
  | "tutor"
  | "revision"
  | "research"
  | "progress";

export const ENVIRONMENT_TABS: { id: EnvironmentTab; label: string; segment: string }[] = [
  { id: "overview", label: "Overview", segment: "" },
  { id: "content", label: "Content", segment: "content" },
  { id: "tutor", label: "AI Tutor", segment: "tutor" },
  { id: "graph", label: "Knowledge Graph", segment: "graph" },
  { id: "intelligence", label: "Intelligence", segment: "intelligence" },
  { id: "revision", label: "Revision", segment: "revision" },
  { id: "research", label: "Research", segment: "research" },
  { id: "progress", label: "Progress", segment: "progress" },
];

export const SCOPE_LABELS: Record<LearningScope, string> = {
  workspace: "Workspace",
  subject: "Folder",
  folder: "Sub-folder",
  chapter: "Chapter",
};

/** Builds a context from whatever ids are known; the deepest id decides the scope. */
export function makeContext(ids: {
  workspaceId: string;
  subjectId?: string | null;
  folderId?: string | null;
  chapterId?: string | null;
}): LearningContext {
  const subjectId = ids.subjectId || undefined;
  const folderId = subjectId ? ids.folderId || undefined : undefined;
  const chapterId = subjectId ? ids.chapterId || undefined : undefined;
  const scope: LearningScope = chapterId
    ? "chapter"
    : folderId
      ? "folder"
      : subjectId
        ? "subject"
        : "workspace";
  return { workspaceId: ids.workspaceId, subjectId, folderId, chapterId, scope };
}

/** Base URL of a context's learning environment. Workspace scope has no environment page. */
export function environmentBase(ctx: LearningContext): string | null {
  if (!ctx.subjectId) return null;
  const subject = `/workspaces/${ctx.workspaceId}/subjects/${ctx.subjectId}`;
  if (ctx.chapterId) return `${subject}/chapters/${ctx.chapterId}`;
  if (ctx.folderId) return `${subject}/folders/${ctx.folderId}`;
  return subject;
}

/** Where a workspace-level tool lives (the global pages reachable from the sidebar). */
const GLOBAL_TOOL_HREF: Record<EnvironmentTab, string> = {
  overview: "/dashboard",
  content: "/subjects",
  graph: "/knowledge",
  intelligence: "/insights",
  tutor: "/ai-tutor",
  revision: "/revision",
  research: "/research",
  progress: "/progress",
};

/** URL of one tab of the context's environment (or the global tool for workspace scope). */
export function environmentHref(ctx: LearningContext, tab: EnvironmentTab = "overview"): string {
  const base = environmentBase(ctx);
  if (!base) {
    const href = GLOBAL_TOOL_HREF[tab];
    return tab === "content" ? `${href}?workspace=${ctx.workspaceId}` : href;
  }
  const segment = ENVIRONMENT_TABS.find((t) => t.id === tab)?.segment ?? "";
  return segment ? `${base}/${segment}` : base;
}

/** The tab a pathname shows, given the environment base it belongs to. */
export function activeTab(pathname: string, base: string): EnvironmentTab {
  const rest = pathname.startsWith(base) ? pathname.slice(base.length).replace(/^\/+/, "") : "";
  const first = rest.split("/")[0];
  return ENVIRONMENT_TABS.find((t) => t.segment && t.segment === first)?.id ?? "overview";
}

/** What the AI Tutor may read for this context: the deepest level is the primary context. */
export function toConversationScope(ctx: LearningContext): ConversationScope {
  if (ctx.chapterId) return { kind: "chapter", id: ctx.chapterId };
  if (ctx.folderId) return { kind: "folder", id: ctx.folderId };
  if (ctx.subjectId) return { kind: "subject", id: ctx.subjectId };
  return { kind: "workspace", id: ctx.workspaceId };
}

// ── URL hand-off ─────────────────────────────────────────────────────────────
// Global tool pages accept a context in the query string, so "Open in AI Tutor" from a chapter
// lands in the tutor with that chapter already selected.

export function contextQuery(ctx: LearningContext): string {
  const p = new URLSearchParams({ ws: ctx.workspaceId });
  if (ctx.subjectId) p.set("subject", ctx.subjectId);
  if (ctx.folderId) p.set("folder", ctx.folderId);
  if (ctx.chapterId) p.set("chapter", ctx.chapterId);
  return p.toString();
}

const UUIDISH = /^[0-9a-fA-F-]{8,64}$/;

/** Reads a context from query parameters; ignores anything that is not id-shaped. */
export function contextFromQuery(params: Pick<URLSearchParams, "get">): LearningContext | null {
  const pick = (k: string) => {
    const v = params.get(k);
    return v && UUIDISH.test(v) ? v : undefined;
  };
  const workspaceId = pick("ws");
  if (!workspaceId) return null;
  return makeContext({
    workspaceId,
    subjectId: pick("subject"),
    folderId: pick("folder"),
    chapterId: pick("chapter"),
  });
}

// ── Capabilities ─────────────────────────────────────────────────────────────
// Not every backend endpoint can narrow to every level yet. Rather than pretend, each tool says
// the deepest scope it can filter by, and the UI tells the learner when it shows a wider scope.

export type ContextTool = Exclude<EnvironmentTab, "overview" | "content">;

const DEPTH: Record<LearningScope, number> = { workspace: 0, subject: 1, folder: 2, chapter: 3 };

/** Deepest scope each tool's API can filter by, per level the learner can be at. */
const SUPPORT: Record<ContextTool, (scope: LearningScope) => LearningScope> = {
  tutor: (s) => s, // conversations can be scoped to any level
  graph: (s) => (DEPTH[s] >= 1 ? "subject" : "workspace"),
  intelligence: (s) => (DEPTH[s] >= 1 ? "subject" : "workspace"),
  research: () => "workspace",
  // revision lists and analytics filter by subject and chapter, not folder
  revision: (s) => (s === "folder" ? "subject" : s),
  progress: (s) => (s === "folder" ? "subject" : s),
};

export interface AppliedScope {
  /** The context the tool will actually filter by. */
  applied: LearningContext;
  /** True when the tool shows a wider scope than the one the learner is in. */
  widened: boolean;
}

export function appliedScope(tool: ContextTool, ctx: LearningContext): AppliedScope {
  const scope = SUPPORT[tool](ctx.scope);
  if (scope === ctx.scope) return { applied: ctx, widened: false };
  const applied = makeContext({
    workspaceId: ctx.workspaceId,
    subjectId: DEPTH[scope] >= 1 ? ctx.subjectId : undefined,
    folderId: scope === "folder" ? ctx.folderId : undefined,
    chapterId: scope === "chapter" ? ctx.chapterId : undefined,
  });
  return { applied, widened: true };
}
