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
