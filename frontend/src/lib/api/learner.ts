import { api } from "./client";
import { getPaged, query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];

export type LearnerDashboard = S["LearnerDashboardOut"];
export type LearnerOverview = S["LearnerOverviewOut"];
export type LearnerSubject = S["LearnerSubjectOut"];
export type LearnerConceptRow = S["LearnerConceptRowOut"];
export type GapConcept = S["LearnerGapConceptOut"];
export type GapMisconception = S["LearnerGapMisconceptionOut"];
export type ConceptState = S["ConceptStateOut"];
export type LearnerEvidence = S["LearnerEvidenceOut"];
export type Misconception = S["MisconceptionOut"];
export type LearnerRecommendation = S["LearnerRecommendationOut"];

const enc = encodeURIComponent;

export const STATE_LABELS: Record<string, string> = {
  NOT_ASSESSED: "Not assessed",
  INSUFFICIENT_EVIDENCE: "Not enough evidence",
  LEARNING: "Weak (still learning)",
  DEVELOPING: "Developing",
  PROFICIENT: "Proficient",
  STRONG: "Strong",
};

export const STATE_ORDER = [
  "STRONG",
  "PROFICIENT",
  "DEVELOPING",
  "LEARNING",
  "INSUFFICIENT_EVIDENCE",
  "NOT_ASSESSED",
] as const;

export const learnerApi = {
  /** Recommendations are synced on read; fetch them first so the dashboard count is current. */
  recommendations: () =>
    api
      .get<{ items: LearnerRecommendation[]; note: string }>("/recommendations/learner")
      .then((r) => r.data),
  dashboard: (f: { workspace_id?: string; subject_id?: string }) =>
    api.get<LearnerDashboard>(`/knowledge/learner/dashboard${query({ ...f })}`).then((r) => r.data),
  state: (nodeId: string) =>
    api.get<ConceptState>(`/knowledge/learner/states/${enc(nodeId)}`).then((r) => r.data),
  evidence: (nodeId: string, limit = 10) =>
    getPaged<LearnerEvidence>(`/knowledge/learner/evidence${query({ node_id: nodeId, limit })}`),
  misconceptions: (nodeId: string) =>
    getPaged<Misconception>(
      `/knowledge/learner/misconceptions${query({ node_id: nodeId, limit: 20 })}`,
    ),
  completeRecommendation: (id: string) =>
    api.post<LearnerRecommendation>(`/recommendations/learner/${enc(id)}/complete`),
  dismissRecommendation: (id: string) =>
    api.post<LearnerRecommendation>(`/recommendations/learner/${enc(id)}/dismiss`),
};

/** Where a recommendation takes the learner. Concept-level advice opens the concept view. */
export function recommendationHref(r: LearnerRecommendation): string {
  switch (r.recommendation_type) {
    case "review_due":
      return "/revision";
    case "revise_concept":
    case "practise_concept":
    case "assess_concept":
      return "/study";
    case "revisit_chapter":
      return "/knowledge";
    default:
      return r.knowledge_node_id ? `/insights?concept=${enc(r.knowledge_node_id)}` : "/insights";
  }
}
