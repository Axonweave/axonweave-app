import { api, API_BASE } from "./client";
import { getPaged, query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];
export type DocumentRecord = S["DocumentOut"];
export type UploadResult = S["UploadData"];
export type ProcessingStatus = S["ProcessingStatusOut"];
export type ProcessingDetails = S["ProcessingDetailsOut"];
export type ContentChunk = S["ChunkOut"];
export type PageInfo = S["PageOut"];

/** Statuses after which nothing changes until the user acts (polling stops). */
export const TERMINAL_STATUSES = ["completed", "failed", "cancelled"] as const;
export const isTerminal = (status: string) =>
  (TERMINAL_STATUSES as readonly string[]).includes(status);

export interface DocumentFilters {
  workspace_id?: string;
  subject_id?: string;
  folder_id?: string;
  chapter_id?: string;
  status?: string;
  file_type?: string;
  q?: string;
  include_archived?: boolean;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface UploadPlacement {
  workspace_id: string;
  subject_id?: string | null;
  folder_id?: string | null;
  chapter_id?: string | null;
}

const enc = encodeURIComponent;

export const documentsApi = {
  list: (filters: DocumentFilters = {}) =>
    getPaged<DocumentRecord>(`/documents${query({ limit: 25, ...filters })}`),

  get: (id: string) => api.get<DocumentRecord>(`/documents/${enc(id)}`).then((r) => r.data),

  /** Multipart upload. The server validates everything; the browser only picks the files. */
  upload: (files: File[], placement: UploadPlacement) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    form.append("workspace_id", placement.workspace_id);
    for (const key of ["subject_id", "folder_id", "chapter_id"] as const) {
      const value = placement[key];
      if (value) form.append(key, value);
    }
    return api.postForm<UploadResult>("/documents/upload", form).then((r) => r.data);
  },

  rename: (id: string, display_name: string) =>
    api.patch<DocumentRecord>(`/documents/${enc(id)}`, { display_name }).then((r) => r.data),
  archive: (id: string) =>
    api.post<DocumentRecord>(`/documents/${enc(id)}/archive`).then((r) => r.data),
  restore: (id: string) =>
    api.post<DocumentRecord>(`/documents/${enc(id)}/restore`).then((r) => r.data),
  remove: (id: string) => api.delete<null>(`/documents/${enc(id)}`),

  status: (id: string) =>
    api.get<ProcessingStatus>(`/documents/${enc(id)}/status`).then((r) => r.data),
  processing: (id: string) =>
    api.get<ProcessingDetails>(`/documents/${enc(id)}/processing`).then((r) => r.data),
  retry: (id: string) => api.post<unknown>(`/documents/${enc(id)}/retry`),
  reprocess: (id: string) => api.post<unknown>(`/documents/${enc(id)}/reprocess`),
  cancel: (id: string) => api.post<unknown>(`/documents/${enc(id)}/cancel`),

  pages: (id: string) => api.get<PageInfo[]>(`/documents/${enc(id)}/pages`).then((r) => r.data),
  content: (id: string, opts: { page?: number; slide?: number; offset?: number } = {}) =>
    getPaged<ContentChunk>(`/documents/${enc(id)}/content${query({ limit: 20, ...opts })}`),

  /** URL of the owner-only download/inline endpoints (cookie-authenticated; never a storage URL). */
  downloadUrl: (id: string) => `${API_BASE}/documents/${enc(id)}/download`,
  inlineUrl: (id: string) => `${API_BASE}/documents/${enc(id)}/inline`,
};

/** Human wording for a processing status or stored error code. */
export const STATUS_LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  queued: "Waiting to process",
  validating: "Checking file",
  extracting: "Reading text",
  ocr_processing: "Running OCR",
  normalising: "Cleaning text",
  chunking: "Splitting into passages",
  embedding: "Indexing",
  indexing: "Indexing",
  completed: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const ERROR_MESSAGES: Record<string, string> = {
  NO_TEXT_FOUND: "No readable text was found in this file.",
  FILE_ENCRYPTED: "This file is password protected.",
  FILE_CORRUPT: "This file looks damaged and could not be read.",
  TOO_MANY_PAGES: "This file has more pages than the limit allows.",
  OCR_UNAVAILABLE: "This file needs OCR, which is not available.",
  EMBEDDING_QUOTA_EXCEEDED: "Today's AI usage limit was reached. Retry tomorrow.",
  EMBEDDING_AUTH_FAILED: "The indexing service is not set up correctly.",
};

export const errorText = (code: string | null | undefined) =>
  code ? (ERROR_MESSAGES[code] ?? "Processing failed. You can try again.") : null;
