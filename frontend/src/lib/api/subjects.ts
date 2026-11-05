import { api } from "./client";
import { getPaged, query } from "./paged";
import type { CreateSubjectRequest, Subject, UpdateSubjectRequest } from "@/types/api";

export type SubjectSortField = "name" | "updated_at";
export type SortDir = "asc" | "desc";

export interface ListSubjectsParams {
  q?: string;
  sortBy?: SubjectSortField;
  sortDir?: SortDir;
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}

const base = (workspaceId: string) => `/workspaces/${workspaceId}/subjects`;

export const subjectsApi = {
  list: (workspaceId: string, p: ListSubjectsParams = {}) =>
    getPaged<Subject>(
      `${base(workspaceId)}${query({
        q: p.q?.trim(),
        sort_by: p.sortBy,
        sort_dir: p.sortDir,
        limit: p.limit,
        offset: p.offset,
        include_archived: p.includeArchived || undefined,
      })}`,
    ),

  get: (workspaceId: string, id: string) =>
    api.get<Subject>(`${base(workspaceId)}/${id}`).then((r) => r.data),

  create: (workspaceId: string, data: CreateSubjectRequest) =>
    api.post<Subject>(base(workspaceId), data).then((r) => r.data),

  update: (workspaceId: string, id: string, data: UpdateSubjectRequest) =>
    api.patch<Subject>(`${base(workspaceId)}/${id}`, data).then((r) => r.data),

  archive: (workspaceId: string, id: string) =>
    api.post<Subject>(`${base(workspaceId)}/${id}/archive`).then((r) => r.data),

  restore: (workspaceId: string, id: string) =>
    api.post<Subject>(`${base(workspaceId)}/${id}/restore`).then((r) => r.data),

  /** Deletes the subject and everything inside it (D-12). */
  remove: (workspaceId: string, id: string) => api.delete<null>(`${base(workspaceId)}/${id}`),
};
