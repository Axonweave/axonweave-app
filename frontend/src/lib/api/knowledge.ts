import { api } from "./client";
import { getPaged, query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];
export type KnowledgeNode = S["NodeOut"];
export type KnowledgeNodeDetail = S["NodeDetailOut"];
export type KnowledgeEdge = S["EdgeOut"];
export type KnowledgeGraph = S["GraphOut"];
export type KnowledgeOverview = S["GraphOverviewOut"];
export type KnowledgeEvidence = S["EvidenceOut"];
export type DuplicateCandidate = S["CandidateOut"];
export type NodeCreate = S["NodeCreate"];
export type NodePatch = S["NodePatch"];
export type EdgeCreate = S["EdgeCreate"];
export type NodeType = NodeCreate["node_type"];
export type RelationshipType = EdgeCreate["relationship_type"];
export type CandidateAction = S["CandidateResolve"]["action"];

export const NODE_TYPES: NodeType[] = [
  "concept",
  "topic",
  "subtopic",
  "term",
  "algorithm",
  "method",
  "formula",
  "model",
  "theory",
  "principle",
  "entity",
  "example",
  "application",
];

export const RELATIONSHIP_TYPES: RelationshipType[] = [
  "IS_A",
  "PART_OF",
  "PREREQUISITE_OF",
  "DEPENDS_ON",
  "RELATED_TO",
  "CONTRASTS_WITH",
  "USES",
  "APPLIED_IN",
  "EXAMPLE_OF",
];

export const RELATIONSHIP_LABELS: Record<string, string> = {
  IS_A: "is a",
  PART_OF: "part of",
  PREREQUISITE_OF: "prerequisite of",
  DEPENDS_ON: "depends on",
  RELATED_TO: "related to",
  CONTRASTS_WITH: "contrasts with",
  USES: "uses",
  APPLIED_IN: "applied in",
  EXAMPLE_OF: "example of",
};

export interface GraphFilters {
  workspace_id?: string;
  subject_id?: string;
  node_type?: string;
  q?: string;
  limit?: number;
}

const enc = encodeURIComponent;

/** Appends repeated relationship_types params to a path that may or may not have a query. */
function withRel(path: string, types?: string[]): string {
  if (!types?.length) return path;
  const sep = path.includes("?") ? "&" : "?";
  return path + sep + types.map((t) => `relationship_types=${enc(t)}`).join("&");
}

export const knowledgeApi = {
  graph: (f: GraphFilters, relationshipTypes?: string[]) =>
    api
      .get<KnowledgeGraph>(withRel(`/knowledge/graph${query({ ...f })}`, relationshipTypes))
      .then((r) => r.data),
  overview: (f: Pick<GraphFilters, "workspace_id" | "subject_id">) =>
    api.get<KnowledgeOverview>(`/knowledge/graph/overview${query({ ...f })}`).then((r) => r.data),
  expand: (nodeId: string, depth = 1, limit = 60, relationshipTypes?: string[]) =>
    api
      .get<KnowledgeGraph>(
        withRel(
          `/knowledge/graph/expand?node_id=${enc(nodeId)}&depth=${depth}&limit=${limit}`,
          relationshipTypes,
        ),
      )
      .then((r) => r.data),
  listNodes: (
    f: Omit<GraphFilters, "limit"> & { archived?: boolean; limit?: number; offset?: number },
  ) => getPaged<KnowledgeNode>(`/knowledge/nodes${query({ ...f })}`),
  node: (id: string) =>
    api.get<KnowledgeNodeDetail>(`/knowledge/nodes/${enc(id)}`).then((r) => r.data),
  createNode: (body: NodeCreate) =>
    api.post<KnowledgeNode>("/knowledge/nodes", body).then((r) => r.data),
  updateNode: (id: string, body: NodePatch) =>
    api.patch<KnowledgeNode>(`/knowledge/nodes/${enc(id)}`, body).then((r) => r.data),
  archiveNode: (id: string) => api.post<null>(`/knowledge/nodes/${enc(id)}/archive`),
  restoreNode: (id: string) =>
    api.post<KnowledgeNode>(`/knowledge/nodes/${enc(id)}/restore`).then((r) => r.data),
  deleteNode: (id: string) => api.delete<null>(`/knowledge/nodes/${enc(id)}`),
  mergeNodes: (survivorId: string, mergedId: string) =>
    api
      .post<KnowledgeNode>("/knowledge/nodes/merge", {
        survivor_id: survivorId,
        merged_id: mergedId,
      })
      .then((r) => r.data),
  nodeEvidence: (id: string, limit = 20, offset = 0) =>
    getPaged<KnowledgeEvidence>(`/knowledge/nodes/${enc(id)}/evidence${query({ limit, offset })}`),
  createEdge: (body: EdgeCreate) =>
    api.post<KnowledgeEdge>("/knowledge/relationships", body).then((r) => r.data),
  deleteEdge: (id: string) => api.delete<null>(`/knowledge/relationships/${enc(id)}`),
  duplicates: (workspaceId?: string, limit = 20, offset = 0) =>
    getPaged<DuplicateCandidate>(
      `/knowledge/duplicates${query({ workspace_id: workspaceId, limit, offset })}`,
    ),
  resolveDuplicate: (id: string, action: CandidateAction, survivorId?: string) =>
    api
      .post<unknown>(`/knowledge/duplicates/${enc(id)}/resolve`, {
        action,
        survivor_id: survivorId ?? null,
      })
      .then((r) => r.data),
};

/** Viewer deep link for one piece of evidence (document viewer opens at the page/chunk). */
export function evidenceHref(ev: KnowledgeEvidence): string {
  return `/documents/${ev.document_id}${query({
    page: ev.page_number ?? ev.slide_number ?? undefined,
    chunk: ev.chunk_id ?? undefined,
  })}`;
}
