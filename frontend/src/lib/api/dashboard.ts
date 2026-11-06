import { api } from "./client";
import type {
  ActivityItem,
  ArchivedItem,
  DashboardStats,
  RecentSubjectItem,
  WorkspaceOverviewItem,
} from "@/types/api";

export interface Paged<T> {
  data: T[];
  total: number;
}

// The list endpoints return { success, data: [...], total } so the client's `data` is the array;
// `total` sits beside it. Re-read the raw envelope for those via this helper.
async function getPaged<T>(path: string): Promise<Paged<T>> {
  const res = await api.get<T[]>(path);
  const total = (res as unknown as { total?: number }).total ?? res.data.length;
  return { data: res.data, total };
}

export const dashboardApi = {
  stats: () => api.get<DashboardStats>("/dashboard/stats").then((r) => r.data),

  workspaces: (limit = 6) =>
    getPaged<WorkspaceOverviewItem>(`/dashboard/workspaces?limit=${limit}`),

  recentSubjects: (limit = 5) =>
    api.get<RecentSubjectItem[]>(`/dashboard/recent-subjects?limit=${limit}`).then((r) => r.data),

  activity: (limit = 20, offset = 0) =>
    getPaged<ActivityItem>(`/dashboard/activity?limit=${limit}&offset=${offset}`),

  archived: (limit = 20, offset = 0) =>
    getPaged<ArchivedItem>(`/dashboard/archived?limit=${limit}&offset=${offset}`),
};
