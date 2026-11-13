import { api } from "./client";
import { getPaged, query } from "./paged";
import type { components } from "@/types/api.generated";

type S = components["schemas"];

export type ResearchProject = S["ProjectOut"];
export type ProjectCreate = S["ProjectCreate"];
export type ProjectPatch = S["ProjectPatch"];
export type ProjectStatus = ProjectCreate["status"] & string;

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
};

/** One item per line, as typed in a textarea. */
export function linesToList(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}
