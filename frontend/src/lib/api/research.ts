import { api } from "./client";
import { getPaged, query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];

export type ResearchProject = S["ProjectOut"];
export type ProjectCreate = S["ProjectCreate"];
export type ProjectPatch = S["ProjectPatch"];
export type ProjectStatus = ProjectCreate["status"] & string;
export type ResearchPaper = S["PaperOut"];
export type PaperCreate = S["PaperCreate"];
export type PaperPatch = S["PaperPatch"];
export type DuplicateCandidate = S["DuplicateCandidateOut"];
export type PaperStatus = NonNullable<PaperCreate["status"]>;
export type AnalysisRun = S["PaperAnalysisRunOut"];
export type PaperAnalysis = S["PaperAnalysisOut"];
export type AnalysisSection = S["PaperSectionOut"];
export type AnalysisClaim = S["PaperClaimOut"];
export type PaperNote = S["PaperNoteOut"];
export type SectionId = AnalysisSection["section"];
export type ResearchComparison = S["ResearchComparisonOut"];
export type ComparisonSummary = S["ResearchComparisonSummary"];
export type ComparisonDimension = S["ResearchComparisonCreate"]["dimensions"] extends
  (infer D)[] | null | undefined
  ? D
  : never;

export interface CompareEvidence {
  quote: string;
  page_number: number | null;
  document_id: string | null;
}
export interface CompareItem {
  text: string;
  label: string | null;
  origin: "reported" | "ai_inferred";
  evidence: CompareEvidence[];
}
export interface CompareCell {
  paper_id: string;
  reported: boolean;
  items: CompareItem[];
}
export interface CompareRow {
  dimension: string;
  label: string;
  status: "complete" | "partial" | "not_reported";
  cells: CompareCell[];
  similarities: string[];
  differences: { paper_id: string; terms: string[] }[];
  not_reported_for: string[];
  directly_comparable: boolean | null;
}
export interface CompareResult {
  papers: { paper_id: string; title: string; version_number: number }[];
  rows: CompareRow[];
  comparability: {
    dataset: string;
    metrics: string;
    setup: string;
    methodology: string;
    results_directly_comparable: boolean;
    warnings: string[];
  };
}

export const COMPARE_DIMENSIONS: { id: ComparisonDimension; label: string }[] = [
  { id: "research_problem", label: "Research problem" },
  { id: "objectives", label: "Objectives and research questions" },
  { id: "methodology", label: "Methodology" },
  { id: "models", label: "Models and algorithms" },
  { id: "dataset", label: "Dataset" },
  { id: "sample_size", label: "Sample size" },
  { id: "metrics", label: "Evaluation metrics" },
  { id: "setup", label: "Experimental setup and evaluation" },
  { id: "results", label: "Results" },
  { id: "contributions", label: "Contributions" },
  { id: "limitations", label: "Limitations" },
  { id: "future_work", label: "Future work" },
];
export type ResearchMatrix = S["ResearchMatrixOut"];
export type MatrixSummary = S["ResearchMatrixSummary"];
export type MatrixColumn = S["ResearchMatrixColumnOut"];
export type MatrixRow = S["ResearchMatrixRowOut"];
export type MatrixCell = S["ResearchMatrixCellOut"];

export type ResearchContradiction = S["ResearchContradictionOut"];
export type ContradictionPatch = S["ResearchContradictionPatch"];

export const CONTRADICTION_CATEGORY_LABELS: Record<string, string> = {
  genuine: "Genuine conflicting findings",
  context_dependent: "Different conditions",
  metric_incompatible: "Incompatible metrics",
  insufficient_evidence: "Insufficient evidence",
};
export const CONTRADICTION_REVIEW_LABELS: Record<string, string> = {
  unreviewed: "Not reviewed",
  genuine: "Marked genuine",
  context_dependent: "Marked context-dependent",
  dismissed: "Dismissed",
};

export type ResearchCitation = S["ResearchCitationOut"];
export type CitationIssue = S["ResearchCitationIssue"];
export type Bibliography = S["ResearchBibliographyOut"];
export type CitationStyle = S["ResearchCitationGenerate"]["style"];

export const CITATION_STYLES: { value: CitationStyle; label: string }[] = [
  { value: "apa", label: "APA 7" },
  { value: "ieee", label: "IEEE" },
  { value: "mla", label: "MLA 9" },
  { value: "chicago", label: "Chicago (author-date)" },
  { value: "harvard", label: "Harvard" },
];

export type ResearchDraft = S["ResearchDraftOut"];
export type DraftSummary = S["ResearchDraftSummary"];
export type DraftVersionSummary = S["ResearchDraftVersionSummary"];
export type DraftVersion = S["ResearchDraftVersionOut"];
export type DraftCheck = S["ResearchDraftCheckOut"];
export type DraftExport = S["ResearchDraftExportOut"];
export type WritingRequest = S["ResearchWritingRequest"];
export type WritingSuggestion = S["ResearchWritingOut"];
type DraftPatchBase = S["ResearchDraftPatch"];
export type DraftPatch = Omit<DraftPatchBase, "change_source"> & {
  change_source?: DraftPatchBase["change_source"];
};

export const DRAFT_TYPE_LABELS: Record<string, string> = {
  research_paper: "Research paper",
  literature_review: "Literature review",
  proposal: "Proposal",
  report: "Report",
  notes: "Notes",
};
export const DRAFT_STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  in_review: "In review",
  final: "Final",
};
export const WRITING_ACTION_LABELS: Record<string, string> = {
  draft_section: "Draft a section from evidence",
  expand: "Expand the selected text",
  synthesis: "Literature synthesis",
  rewrite: "Rewrite the selected text",
  tone: "Improve academic tone",
  grammar: "Fix grammar",
  clarity: "Improve clarity",
  organise: "Organise paragraphs",
};
export const WRITING_SECTION_LABELS: Record<string, string> = {
  abstract: "Abstract",
  introduction: "Introduction",
  background: "Background",
  literature_review: "Literature review",
  problem_statement: "Problem statement",
  objectives: "Research objectives",
  research_questions: "Research questions",
  methodology: "Methodology",
  proposed_approach: "Proposed approach",
  results: "Results",
  discussion: "Discussion",
  limitations: "Limitations",
  conclusion: "Conclusion",
  future_work: "Future work",
};
export const CHECK_STATUS_LABELS: Record<string, string> = {
  supported_single: "Supported by one paper",
  supported_multiple: "Supported by several papers",
  citation_mismatch: "Citation does not match the sentence",
  cannot_verify: "Cited paper not analysed",
  invalid_reference: "Cites a paper outside this project",
  unsupported: "No citation for a finding-like statement",
  unmarked: "No citation (interpretation or plain text)",
};

/** The citation marker stored in a draft for a paper. */
export function citeMarker(paperId: string): string {
  return `{{cite:${paperId}}}`;
}

export type ResearchDashboard = S["ResearchDashboardOut"];
export type ConceptLink = S["ResearchConceptLinkOut"];
export type ConceptResearch = S["ResearchConceptResearchOut"];
export type ConceptLinkStatus = "suggested" | "confirmed" | "rejected";

export const CONCEPT_LINK_STATUS_LABELS: Record<string, string> = {
  suggested: "Suggested",
  confirmed: "Confirmed",
  rejected: "Rejected",
};

export type ResearchGap = S["ResearchGapOut"];
export type GapEvidence = S["ResearchGapEvidenceOut"];
export type GapPatch = S["ResearchGapPatch"];

export const GAP_CATEGORY_LABELS: Record<string, string> = {
  methodological: "Methodological",
  dataset: "Dataset",
  population: "Population",
  evaluation: "Evaluation",
  domain: "Domain",
  application: "Application",
  generalisation: "Generalisation",
  reproducibility: "Reproducibility",
  contradictory_findings: "Contradictory findings",
};
export const GAP_CONFIDENCE_LABELS: Record<string, string> = {
  strong_candidate: "Strong candidate",
  moderate_candidate: "Moderate candidate",
  preliminary_candidate: "Preliminary candidate",
  insufficient_evidence: "Insufficient evidence",
};
export const GAP_STATUS_LABELS: Record<string, string> = {
  suggested: "Suggested",
  accepted: "Accepted",
  rejected: "Rejected",
  investigating: "Investigating",
};

export const MATRIX_ORIGIN_LABELS: Record<string, string> = {
  extracted: "Extracted from the paper",
  ai_generated: "AI interpretation",
  researcher: "Your note",
};

/** CSV text of a matrix: one row per paper, one column per matrix column, in matrix order. */
export function matrixToCsv(m: ResearchMatrix): string {
  const esc = (v: string) => {
    const safe = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const lines = [m.columns.map((c) => esc(c.title)).join(",")];
  for (const row of m.rows) {
    const byCol = new Map(row.cells.map((c) => [c.column_id, c]));
    lines.push(
      m.columns
        .map((c) => {
          const cell = byCol.get(c.id);
          return esc(cell && cell.value ? cell.value : "");
        })
        .join(","),
    );
  }
  return lines.join("\n");
}

export const COMPARE_NOT_REPORTED = "Not reported.";

/** CSV text of a comparison. Cells that could be read as spreadsheet formulas are neutralised. */
export function comparisonToCsv(result: CompareResult, notes: Record<string, string>): string {
  const esc = (v: string) => {
    const safe = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const title = new Map(result.papers.map((p) => [p.paper_id, p.title]));
  const head = [
    "Dimension",
    ...result.papers.map((p) => p.title),
    "Similarities",
    "Differences",
    "Notes",
  ];
  const lines = [head.map(esc).join(",")];
  for (const row of result.rows) {
    const cells = result.papers.map((p) => {
      const cell = row.cells.find((c) => c.paper_id === p.paper_id);
      if (!cell || !cell.reported) return COMPARE_NOT_REPORTED;
      return cell.items
        .map((i) => {
          const q = i.evidence[0];
          return q
            ? `${i.text} [“${q.quote}”${q.page_number ? `, p. ${q.page_number}` : ""}]`
            : i.text;
        })
        .join(" | ");
    });
    const diffs = row.differences
      .map((d) => `${title.get(d.paper_id) ?? ""}: ${d.terms.join(", ")}`)
      .join(" | ");
    lines.push(
      [row.label, ...cells, row.similarities.join(", "), diffs, notes[row.dimension] ?? ""]
        .map(esc)
        .join(","),
    );
  }
  return lines.join("\n");
}

/** The analysis tabs, in reading order. Every section is shown even when nothing was found. */
export const ANALYSIS_SECTIONS: { id: SectionId; label: string }[] = [
  { id: "research_problem", label: "Research problem" },
  { id: "objectives", label: "Objectives" },
  { id: "methodology", label: "Methodology" },
  { id: "dataset", label: "Dataset" },
  { id: "evaluation", label: "Evaluation" },
  { id: "results", label: "Results" },
  { id: "contributions", label: "Contributions" },
  { id: "limitations", label: "Limitations" },
  { id: "future_work", label: "Future work" },
  { id: "references", label: "References" },
];

export const NOT_REPORTED = "Not reported in the available paper.";
export const ACTIVE_RUN_STATUSES = [
  "pending",
  "retrieving_sources",
  "extracting",
  "validating",
  "saving",
];
export const RUN_STATUS_LABELS: Record<string, string> = {
  pending: "Waiting to start",
  retrieving_sources: "Reading the paper",
  extracting: "Extracting sections",
  validating: "Checking quotations",
  saving: "Saving",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const PROJECT_STATUSES: { value: ProjectStatus; label: string }[] = [
  { value: "planning", label: "Planning" },
  { value: "active", label: "Active" },
  { value: "on_hold", label: "On hold" },
  { value: "completed", label: "Completed" },
];

export const STATUS_LABELS: Record<string, string> = Object.fromEntries(
  PROJECT_STATUSES.map((s) => [s.value, s.label]),
);

export interface ProjectFilters {
  workspace_id?: string;
  status?: string;
  q?: string;
  archived?: boolean;
  sort_by?: "updated_at" | "created_at" | "title" | "target_date";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export const PAPER_STATUSES: { value: PaperStatus; label: string }[] = [
  { value: "unread", label: "Unread" },
  { value: "reading", label: "Reading" },
  { value: "read", label: "Read" },
];

export const SOURCE_LABELS: Record<string, string> = {
  user_supplied: "Entered by you",
  pdf_extracted: "Extracted from the PDF",
  external_provider: "From a metadata provider",
};

export const ANALYSIS_LABELS: Record<string, string> = {
  not_analysed: "Not analysed",
  queued: "Analysis queued",
  analysing: "Analysing",
  analysed: "Analysed",
  failed: "Analysis failed",
};

export interface PaperFilters {
  q?: string;
  status?: string;
  year?: number;
  has_file?: boolean;
  archived?: boolean;
  sort_by?: "updated_at" | "created_at" | "title" | "publication_year";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

const enc = encodeURIComponent;

export const researchApi = {
  dashboard: (workspaceId?: string) =>
    api
      .get<ResearchDashboard>(`/research/dashboard${query({ workspace_id: workspaceId })}`)
      .then((r) => r.data),
  projectDashboard: (projectId: string) =>
    api
      .get<ResearchDashboard>(`/research/projects/${enc(projectId)}/dashboard`)
      .then((r) => r.data),
  listProjects: (f: ProjectFilters) =>
    getPaged<ResearchProject>(`/research/projects${query({ ...f })}`),
  createProject: (body: ProjectCreate) =>
    api.post<ResearchProject>("/research/projects", body).then((r) => r.data),
  updateProject: (id: string, body: ProjectPatch) =>
    api.patch<ResearchProject>(`/research/projects/${enc(id)}`, body).then((r) => r.data),
  archiveProject: (id: string) =>
    api.post<ResearchProject>(`/research/projects/${enc(id)}/archive`).then((r) => r.data),
  restoreProject: (id: string) =>
    api.post<ResearchProject>(`/research/projects/${enc(id)}/restore`).then((r) => r.data),
  deleteProject: (id: string) => api.delete<unknown>(`/research/projects/${enc(id)}`),

  listPapers: (projectId: string, f: PaperFilters) =>
    getPaged<ResearchPaper>(`/research/projects/${enc(projectId)}/papers${query({ ...f })}`),
  addPaper: (projectId: string, body: PaperCreate) =>
    api
      .post<ResearchPaper>(`/research/projects/${enc(projectId)}/papers`, body)
      .then((r) => r.data),
  updatePaper: (id: string, body: PaperPatch) =>
    api.patch<ResearchPaper>(`/research/papers/${enc(id)}`, body).then((r) => r.data),
  archivePaper: (id: string) =>
    api.post<ResearchPaper>(`/research/papers/${enc(id)}/archive`).then((r) => r.data),
  restorePaper: (id: string) =>
    api.post<ResearchPaper>(`/research/papers/${enc(id)}/restore`).then((r) => r.data),
  deletePaper: (id: string) => api.delete<unknown>(`/research/papers/${enc(id)}`),
  getPaper: (id: string) =>
    api.get<ResearchPaper>(`/research/papers/${enc(id)}`).then((r) => r.data),
  analysis: (paperId: string, version?: number) =>
    api
      .get<PaperAnalysis>(`/research/papers/${enc(paperId)}/analysis${query({ version })}`)
      .then((r) => r.data),
  analysisHistory: (paperId: string) =>
    getPaged<AnalysisRun>(`/research/papers/${enc(paperId)}/analyses${query({ limit: 50 })}`),
  startAnalysis: (paperId: string) =>
    api.post<AnalysisRun>(`/research/papers/${enc(paperId)}/analyses`).then((r) => r.data),
  cancelAnalysis: (paperId: string, runId: string) =>
    api
      .post<AnalysisRun>(`/research/papers/${enc(paperId)}/analyses/${enc(runId)}/cancel`)
      .then((r) => r.data),
  listNotes: (paperId: string) =>
    api.get<PaperNote[]>(`/research/papers/${enc(paperId)}/notes`).then((r) => r.data),
  addNote: (paperId: string, body: { section: SectionId | null; body: string }) =>
    api.post<PaperNote>(`/research/papers/${enc(paperId)}/notes`, body).then((r) => r.data),
  editNote: (noteId: string, body: string) =>
    api.patch<PaperNote>(`/research/notes/${enc(noteId)}`, { body }).then((r) => r.data),
  deleteNote: (noteId: string) => api.delete<unknown>(`/research/notes/${enc(noteId)}`),
  listComparisons: (projectId: string) =>
    getPaged<ComparisonSummary>(
      `/research/projects/${enc(projectId)}/comparisons${query({ limit: 50 })}`,
    ),
  createComparison: (
    projectId: string,
    body: { title: string; paper_ids: string[]; dimensions?: ComparisonDimension[] | null },
  ) =>
    api
      .post<ResearchComparison>(`/research/projects/${enc(projectId)}/comparisons`, body)
      .then((r) => r.data),
  getComparison: (id: string) =>
    api.get<ResearchComparison>(`/research/comparisons/${enc(id)}`).then((r) => r.data),
  patchComparison: (id: string, body: { title?: string; notes?: Record<string, string> }) =>
    api.patch<ResearchComparison>(`/research/comparisons/${enc(id)}`, body).then((r) => r.data),
  deleteComparison: (id: string) => api.delete<unknown>(`/research/comparisons/${enc(id)}`),
  listMatrices: (projectId: string) =>
    getPaged<MatrixSummary>(`/research/projects/${enc(projectId)}/matrices${query({ limit: 50 })}`),
  createMatrix: (
    projectId: string,
    body: { title: string; description?: string | null; paper_ids: string[] },
  ) =>
    api
      .post<ResearchMatrix>(`/research/projects/${enc(projectId)}/matrices`, body)
      .then((r) => r.data),
  getMatrix: (id: string) =>
    api.get<ResearchMatrix>(`/research/matrices/${enc(id)}`).then((r) => r.data),
  patchMatrix: (id: string, body: { title?: string; description?: string | null }) =>
    api.patch<ResearchMatrix>(`/research/matrices/${enc(id)}`, body).then((r) => r.data),
  deleteMatrix: (id: string) => api.delete<unknown>(`/research/matrices/${enc(id)}`),
  matrixAddPapers: (id: string, paper_ids: string[]) =>
    api
      .post<ResearchMatrix>(`/research/matrices/${enc(id)}/papers`, { paper_ids })
      .then((r) => r.data),
  matrixRemovePaper: (id: string, paperId: string) =>
    api
      .delete<ResearchMatrix>(`/research/matrices/${enc(id)}/papers/${enc(paperId)}`)
      .then((r) => r.data),
  matrixAddColumn: (id: string, title: string) =>
    api
      .post<ResearchMatrix>(`/research/matrices/${enc(id)}/columns`, { title })
      .then((r) => r.data),
  matrixRenameColumn: (id: string, columnId: string, title: string) =>
    api
      .patch<ResearchMatrix>(`/research/matrices/${enc(id)}/columns/${enc(columnId)}`, { title })
      .then((r) => r.data),
  matrixRemoveColumn: (id: string, columnId: string) =>
    api
      .delete<ResearchMatrix>(`/research/matrices/${enc(id)}/columns/${enc(columnId)}`)
      .then((r) => r.data),
  matrixReorder: (id: string, column_ids: string[]) =>
    api
      .put<ResearchMatrix>(`/research/matrices/${enc(id)}/columns/order`, { column_ids })
      .then((r) => r.data),
  matrixEditCell: (id: string, paperId: string, columnId: string, value: string) =>
    api
      .patch<ResearchMatrix>(
        `/research/matrices/${enc(id)}/entries/${enc(paperId)}/${enc(columnId)}`,
        { value },
      )
      .then((r) => r.data),
  matrixRefresh: (id: string) =>
    api.post<ResearchMatrix>(`/research/matrices/${enc(id)}/refresh`).then((r) => r.data),
  suggestConceptLinks: (projectId: string) =>
    api
      .post<ConceptLink[]>(`/research/projects/${enc(projectId)}/concept-links/suggest`, {})
      .then((r) => r.data),
  listConceptLinks: (projectId: string, f: { link_status?: string } = {}) =>
    getPaged<ConceptLink>(
      `/research/projects/${enc(projectId)}/concept-links${query({ ...f, limit: 100 })}`,
    ),
  reviewConceptLink: (id: string, link_status: ConceptLinkStatus) =>
    api
      .patch<ConceptLink>(`/research/concept-links/${enc(id)}`, { link_status })
      .then((r) => r.data),
  deleteConceptLink: (id: string) => api.delete<unknown>(`/research/concept-links/${enc(id)}`),
  paperConcepts: (paperId: string) =>
    api.get<ConceptLink[]>(`/research/papers/${enc(paperId)}/concepts`).then((r) => r.data),
  conceptResearch: (nodeId: string) =>
    api.get<ConceptResearch>(`/research/concepts/${enc(nodeId)}/research`).then((r) => r.data),
  listDrafts: (projectId: string) =>
    getPaged<DraftSummary>(`/research/projects/${enc(projectId)}/drafts${query({ limit: 100 })}`),
  createDraft: (
    projectId: string,
    body: { title: string; document_type?: string; content?: string; citation_style?: string },
  ) =>
    api
      .post<ResearchDraft>(`/research/projects/${enc(projectId)}/drafts`, body)
      .then((r) => r.data),
  getDraft: (id: string) =>
    api.get<ResearchDraft>(`/research/drafts/${enc(id)}`).then((r) => r.data),
  patchDraft: (id: string, body: DraftPatch) =>
    api.patch<ResearchDraft>(`/research/drafts/${enc(id)}`, body).then((r) => r.data),
  deleteDraft: (id: string) => api.delete<unknown>(`/research/drafts/${enc(id)}`),
  draftVersions: (id: string) =>
    api.get<DraftVersionSummary[]>(`/research/drafts/${enc(id)}/versions`).then((r) => r.data),
  draftVersion: (id: string, n: number) =>
    api.get<DraftVersion>(`/research/drafts/${enc(id)}/versions/${n}`).then((r) => r.data),
  restoreDraftVersion: (id: string, n: number, expected_version: number) =>
    api
      .post<ResearchDraft>(`/research/drafts/${enc(id)}/versions/${n}/restore`, {
        expected_version,
      })
      .then((r) => r.data),
  checkDraft: (id: string) =>
    api.post<DraftCheck>(`/research/drafts/${enc(id)}/check`).then((r) => r.data),
  exportDraft: (id: string) =>
    api.get<DraftExport>(`/research/drafts/${enc(id)}/export`).then((r) => r.data),
  assistDraft: (id: string, body: WritingRequest) =>
    api.post<WritingSuggestion>(`/research/drafts/${enc(id)}/assist`, body).then((r) => r.data),
  listCitations: (projectId: string, style?: CitationStyle) =>
    api
      .get<ResearchCitation[]>(`/research/projects/${enc(projectId)}/citations${query({ style })}`)
      .then((r) => r.data),
  generateCitations: (
    projectId: string,
    body: { style: CitationStyle; paper_ids?: string[]; accessed_date?: string | null },
  ) =>
    api
      .post<ResearchCitation[]>(`/research/projects/${enc(projectId)}/citations`, body)
      .then((r) => r.data),
  deleteCitation: (id: string) => api.delete<unknown>(`/research/citations/${enc(id)}`),
  bibliography: (projectId: string, style: CitationStyle, format: "text" | "bibtex") =>
    api
      .get<Bibliography>(
        `/research/projects/${enc(projectId)}/citations/bibliography${query({ style, format })}`,
      )
      .then((r) => r.data),
  listContradictions: (projectId: string, f: { category?: string; review_status?: string } = {}) =>
    getPaged<ResearchContradiction>(
      `/research/projects/${enc(projectId)}/contradictions${query({ ...f, limit: 100 })}`,
    ),
  generateContradictions: (projectId: string) =>
    api
      .post<ResearchContradiction[]>(
        `/research/projects/${enc(projectId)}/contradictions/generate`,
        {},
      )
      .then((r) => r.data),
  patchContradiction: (id: string, body: ContradictionPatch) =>
    api
      .patch<ResearchContradiction>(`/research/contradictions/${enc(id)}`, body)
      .then((r) => r.data),
  deleteContradiction: (id: string) => api.delete<unknown>(`/research/contradictions/${enc(id)}`),
  listGaps: (projectId: string, f: { category?: string; status?: string } = {}) =>
    getPaged<ResearchGap>(
      `/research/projects/${enc(projectId)}/gaps${query({ ...f, limit: 100 })}`,
    ),
  generateGaps: (projectId: string) =>
    api
      .post<ResearchGap[]>(`/research/projects/${enc(projectId)}/gaps/generate`, {})
      .then((r) => r.data),
  patchGap: (id: string, body: GapPatch) =>
    api.patch<ResearchGap>(`/research/gaps/${enc(id)}`, body).then((r) => r.data),
  deleteGap: (id: string) => api.delete<unknown>(`/research/gaps/${enc(id)}`),
  duplicates: (projectId: string) =>
    api
      .get<DuplicateCandidate[]>(`/research/projects/${enc(projectId)}/papers/duplicates`)
      .then((r) => r.data),
  resolveDuplicate: (
    projectId: string,
    body: {
      paper_id: string;
      other_id: string;
      action: "not_duplicate" | "merge";
      survivor_id?: string;
    },
  ) => api.post<unknown>(`/research/projects/${enc(projectId)}/papers/duplicates/resolve`, body),
};

/** One item per line, as typed in a textarea. */
export function linesToList(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}
