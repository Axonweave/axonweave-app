import { api } from "./client";
import type { CreateWorkspaceRequest, UpdateWorkspaceRequest, Workspace } from "@/types/api";

interface WorkspaceListData {
  data: Workspace[];
  total: number;
}

export const workspacesApi = {
  list: (includeArchived = false) =>
    api.get<WorkspaceListData>(
      `/workspaces${includeArchived ? "?include_archived=true" : ""}`,
    ),

  get: (id: string) => api.get<Workspace>(`/workspaces/${id}`),

  create: (data: CreateWorkspaceRequest) =>
    api.post<Workspace>("/workspaces", data),

  update: (id: string, data: UpdateWorkspaceRequest) =>
    api.patch<Workspace>(`/workspaces/${id}`, data),

  setDefault: (id: string) =>
    api.post<Workspace>(`/workspaces/${id}/set-default`),

  archive: (id: string) =>
    api.post<Workspace>(`/workspaces/${id}/archive`),

  restore: (id: string) =>
    api.post<Workspace>(`/workspaces/${id}/restore`),

  delete: (id: string) =>
    api.delete<null>(`/workspaces/${id}`),
};
