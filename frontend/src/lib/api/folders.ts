import { api } from "./client";
import { query } from "./paged";
import type { CreateFolderRequest, Folder, UpdateFolderRequest } from "@/types/api";

const base = (workspaceId: string, subjectId: string) =>
  `/workspaces/${workspaceId}/subjects/${subjectId}/folders`;

export const foldersApi = {
  /** Every folder of the subject, flat (all levels); the caller builds the tree. */
  listAll: (workspaceId: string, subjectId: string, includeArchived = false) =>
    api
      .get<Folder[]>(
        `${base(workspaceId, subjectId)}${query({
          all_levels: true,
          include_archived: includeArchived || undefined,
        })}`,
      )
      .then((r) => r.data),

  get: (workspaceId: string, subjectId: string, id: string) =>
    api.get<Folder>(`${base(workspaceId, subjectId)}/${id}`).then((r) => r.data),

  create: (workspaceId: string, subjectId: string, data: CreateFolderRequest) =>
    api.post<Folder>(base(workspaceId, subjectId), data).then((r) => r.data),

  update: (workspaceId: string, subjectId: string, id: string, data: UpdateFolderRequest) =>
    api.patch<Folder>(`${base(workspaceId, subjectId)}/${id}`, data).then((r) => r.data),

  /** parentId null moves the folder to the top level. The server validates depth and cycles. */
  move: (workspaceId: string, subjectId: string, id: string, parentId: string | null) =>
    api
      .patch<Folder>(`${base(workspaceId, subjectId)}/${id}`, {
        parent_folder_id: parentId,
        parent_folder_id_set: true,
      })
      .then((r) => r.data),

  archive: (workspaceId: string, subjectId: string, id: string) =>
    api.post<Folder>(`${base(workspaceId, subjectId)}/${id}/archive`).then((r) => r.data),

  restore: (workspaceId: string, subjectId: string, id: string) =>
    api.post<Folder>(`${base(workspaceId, subjectId)}/${id}/restore`).then((r) => r.data),

  /** Without cascade the API answers 409 when the folder is not empty (D-12). */
  remove: (workspaceId: string, subjectId: string, id: string, cascade = false) =>
    api.delete<null>(`${base(workspaceId, subjectId)}/${id}${cascade ? "?cascade=true" : ""}`),
};
