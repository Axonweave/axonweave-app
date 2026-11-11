import { api, API_BASE } from "./client";
import { getPaged, query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];
export type GenerationJob = S["GenerationJobOut"];
export type StudyMaterial = S["StudyMaterialOut"];
export type LibraryItem = S["LibraryItemOut"];
export type MaterialVersion = S["VersionOut"];
export type RegenerationPreview = S["PreviewOut"];
export type FlashcardSet = S["FlashcardSetOut"];
export type Flashcard = S["FlashcardOut"];
export type StudyPreferences = S["PreferencesOut"];
export type StudyExport = S["ExportOut"];
export type Quiz = S["QuizOut"];
export type QuizQuestion = S["QuizQuestionOut"];
export type QuizAttempt = S["AttemptOut"];
export type QuizAttemptSummary = S["AttemptSummary"];
export type QuizResult = S["ResultOut"];

export type GenerationType =
  | "summary"
  | "flashcards"
  | "quiz"
  | "study_guide"
  | "glossary"
  | "formula_sheet"
  | "question_bank";

export type SourceType = "document" | "documents" | "chapter" | "subject" | "folder" | "workspace" | "text";

export interface SourceSpec {
  type: SourceType;
  id?: string;
  ids?: string[];
  text?: string;
  workspace_id?: string;
}

export interface GenerationRequest {
  generation_type: GenerationType;
  source: SourceSpec;
  settings: Record<string, unknown>;
}

export const RESOURCE_LABELS: Record<string, string> = {
  summary: "Summary",
  flashcard_set: "Flashcards",
  flashcards: "Flashcards",
  quiz: "Quiz",
  study_guide: "Study guide",
  glossary: "Glossary",
  formula_sheet: "Formula sheet",
  question_bank: "Question bank",
};
export const resourceLabel = (type: string) => RESOURCE_LABELS[type] ?? type;

/** Statuses after which a generation job never changes again (polling stops). */
export const JOB_TERMINAL = ["completed", "failed", "cancelled"] as const;
export const isJobDone = (status: string) => (JOB_TERMINAL as readonly string[]).includes(status);

/** Plain-language text per error code. The backend message is used for anything not listed. */
export const GENERATION_ERRORS: Record<string, string> = {
  GENERATION_QUOTA_EXCEEDED: "You have reached your AI usage limit. Try again later.",
  GENERATION_TOO_MANY_ACTIVE: "You already have generations running. Wait for one to finish.",
  GENERATION_NO_SOURCES: "No readable text was found in the selected source.",
  GENERATION_SOURCE_TOO_SMALL: "The selected source is too short to generate this from.",
  GENERATION_SOURCE_TOO_LARGE: "The selected source is too large. Pick a smaller scope.",
  GENERATION_INVALID_OUTPUT: "The AI returned something unusable. Try again.",
  GENERATION_TIMEOUT: "Generation took too long. Try again or pick a smaller scope.",
  GENERATION_INTERRUPTED: "Generation was interrupted. Try again.",
  GENERATION_UNAVAILABLE: "Generation is not available right now.",
  LLM_NOT_CONFIGURED: "AI is not configured on this server.",
  GENERATION_FAILED: "Generation failed. Try again.",
};
export const explainError = (code: string | null | undefined, fallback?: string | null) =>
  (code && GENERATION_ERRORS[code]) || fallback || "Generation failed.";

export interface LibraryFilters {
  q?: string;
  resource_type?: string;
  workspace_id?: string;
  subject_id?: string;
  chapter_id?: string;
  archived?: boolean;
  sort_by?: "created_at" | "updated_at" | "title" | "resource_type";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

const enc = encodeURIComponent;
const m = (id: string) => `/study/materials/${enc(id)}`;

export const studyApi = {
  // generations
  generate: (body: GenerationRequest) =>
    api.post<GenerationJob>("/study/generations", body).then((r) => r.data),
  jobs: (opts: { status?: string; limit?: number; offset?: number } = {}) =>
    getPaged<GenerationJob>(`/study/generations${query({ limit: 20, ...opts })}`),
  job: (id: string) => api.get<GenerationJob>(`/study/generations/${enc(id)}`).then((r) => r.data),
  cancel: (id: string) =>
    api.post<GenerationJob>(`/study/generations/${enc(id)}/cancel`).then((r) => r.data),

  // library
  list: (filters: LibraryFilters = {}) =>
    getPaged<LibraryItem>(`/study/materials${query({ limit: 25, ...filters })}`),
  get: (id: string) => api.get<StudyMaterial>(m(id)).then((r) => r.data),
  edit: (id: string, expected_version: number, payload: Record<string, unknown>) =>
    api.patch<StudyMaterial>(m(id), { expected_version, payload }).then((r) => r.data),
  remove: (id: string) => api.delete<null>(m(id)),
  duplicate: (id: string) =>
    api.post<StudyMaterial>(`${m(id)}/duplicate`).then((r) => r.data),
  archive: (id: string) => api.post<StudyMaterial>(`${m(id)}/archive`).then((r) => r.data),
  unarchive: (id: string) => api.post<StudyMaterial>(`${m(id)}/unarchive`).then((r) => r.data),

  // versions and regeneration
  versions: (id: string) => api.get<MaterialVersion[]>(`${m(id)}/versions`).then((r) => r.data),
  version: (id: string, n: number) =>
    api.get<MaterialVersion>(`${m(id)}/versions/${n}`).then((r) => r.data),
  restore: (id: string, expected_version: number, version: number) =>
    api.post<StudyMaterial>(`${m(id)}/restore`, { expected_version, version }).then((r) => r.data),
  regenerate: (id: string, body: { section_index?: number; settings?: Record<string, unknown> }) =>
    api.post<GenerationJob>(`${m(id)}/regenerate`, body).then((r) => r.data),
  preview: (jobId: string) =>
    api.get<RegenerationPreview>(`/study/generations/${enc(jobId)}/preview`).then((r) => r.data),
  applyPreview: (jobId: string) =>
    api.post<StudyMaterial>(`/study/generations/${enc(jobId)}/preview/apply`).then((r) => r.data),
  discardPreview: (jobId: string) => api.delete<null>(`/study/generations/${enc(jobId)}/preview`),

  // glossary / bank read helpers
  glossary: (id: string, p: { q?: string; topic?: string; order?: "asc" | "desc" } = {}) =>
    getPaged<GlossaryTerm>(`${m(id)}/glossary${query(p)}`),
  questions: (
    id: string,
    p: { q?: string; topic?: string; difficulty?: string; question_type?: string } = {},
  ) => getPaged<BankQuestion>(`${m(id)}/questions${query(p)}`),

  // flashcards (the deck id equals the set id; found through the material)
  deck: (setId: string) => api.get<FlashcardSet>(`/study/flashcards/${enc(setId)}`).then((r) => r.data),
  addCard: (
    setId: string,
    body: { front: string; back: string; explanation?: string | null },
  ) => api.post<Flashcard>(`/study/flashcards/${enc(setId)}/cards`, body).then((r) => r.data),
  editCard: (
    cardId: string,
    body: Partial<Pick<Flashcard, "front" | "back" | "explanation" | "is_favourite">>,
  ) => api.patch<Flashcard>(`/study/flashcards/cards/${enc(cardId)}`, body).then((r) => r.data),
  deleteCard: (cardId: string) => api.delete<null>(`/study/flashcards/cards/${enc(cardId)}`),
  reorderCards: (setId: string, card_ids: string[]) =>
    api.put<Flashcard[]>(`/study/flashcards/${enc(setId)}/order`, { card_ids }).then((r) => r.data),
  regenerateCards: (setId: string, card_ids: string[]) =>
    api
      .post<GenerationJob>(`/study/flashcards/${enc(setId)}/regenerate`, { card_ids })
      .then((r) => r.data),
  applyCardPreview: (setId: string, jobId: string) =>
    api
      .post<Flashcard[]>(`/study/flashcards/${enc(setId)}/regenerate/${enc(jobId)}/apply`)
      .then((r) => r.data),

  // preferences
  preferences: () => api.get<StudyPreferences>("/study/preferences").then((r) => r.data),
  savePreferences: (body: StudyPreferences) =>
    api.put<StudyPreferences>("/study/preferences", body).then((r) => r.data),

  // exports
  requestExport: (id: string, format: "pdf" | "csv" | "md" | "docx") =>
    api.post<StudyExport>(`${m(id)}/export`, { format }).then((r) => r.data),
  exportStatus: (exportId: string) =>
    api.get<StudyExport>(`/study/exports/${enc(exportId)}`).then((r) => r.data),
  /** The download is an authenticated GET; the browser navigates to it with the session cookie. */
  downloadUrl: (exportId: string) => `${API_BASE}/study/exports/${enc(exportId)}/download`,

  // quizzes
  quiz: (id: string) => api.get<Quiz>(`/study/quizzes/${enc(id)}`).then((r) => r.data),
  startAttempt: (quizId: string) =>
    api.post<QuizAttempt>(`/study/quizzes/${enc(quizId)}/attempts`).then((r) => r.data),
  attempts: (quizId: string) =>
    api.get<QuizAttemptSummary[]>(`/study/quizzes/${enc(quizId)}/attempts`).then((r) => r.data),
  attempt: (quizId: string, attemptId: string) =>
    api
      .get<QuizAttempt>(`/study/quizzes/${enc(quizId)}/attempts/${enc(attemptId)}`)
      .then((r) => r.data),
  saveAnswers: (quizId: string, attemptId: string, answers: AnswerInput[]) =>
    api
      .put<QuizAttempt>(`/study/quizzes/${enc(quizId)}/attempts/${enc(attemptId)}/answers`, {
        answers,
      })
      .then((r) => r.data),
  submit: (quizId: string, attemptId: string, answers?: AnswerInput[]) =>
    api
      .post<QuizAttempt>(
        `/study/quizzes/${enc(quizId)}/attempts/${enc(attemptId)}/submit`,
        answers ? { answers } : undefined,
      )
      .then((r) => r.data),
  result: (quizId: string, attemptId: string) =>
    api
      .get<QuizResult>(`/study/quizzes/${enc(quizId)}/results/${enc(attemptId)}`)
      .then((r) => r.data),
};

export interface AnswerInput {
  question_id: string;
  answer: string[];
  flagged?: boolean;
}

export interface GlossaryTerm {
  term: string;
  definition: string;
  explanation?: string;
  example?: string;
  topic?: string;
  related_terms?: string[];
  source_refs?: number[];
}

export interface BankQuestion {
  question: string;
  question_type: string;
  difficulty: string;
  options?: { id: string; text: string }[];
  topic?: string;
  source_refs?: number[];
}

/** Material content as stored: { payload, sources, coverage }. */
export interface MaterialSource {
  rank: number;
  kind: "chunk" | "text";
  document_id?: string;
  chunk_id?: string;
  page_number?: number | null;
  slide_number?: number | null;
}
export function materialParts<T>(material: StudyMaterial): {
  payload: T;
  sources: MaterialSource[];
  coverage: Record<string, unknown> | null;
} {
  const c = material.content as Record<string, unknown>;
  return {
    payload: (c.payload ?? {}) as T,
    sources: (Array.isArray(c.sources) ? c.sources : []) as MaterialSource[],
    coverage: (c.coverage as Record<string, unknown> | undefined) ?? null,
  };
}
