import { api } from "./client";
import { getPaged } from "./paged";

export type { Paged } from "./paged";
import type {
  ActivityItem,
  ArchivedItem,
  DashboardStats,
  RecentSubjectItem,
  WorkspaceOverviewItem,
} from "@/types/api";

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
