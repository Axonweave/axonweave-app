import { api } from "./client";
import { getPaged, query } from "./paged";
import type { Paged } from "./paged";
import type { Chapter, CreateChapterRequest, UpdateChapterRequest } from "@/types/api";

export type ChapterSortField = "display_order" | "title" | "updated_at";
export type SortDir = "asc" | "desc";

export interface ListChaptersParams {
  folderId?: string;
  q?: string;
  sortBy?: ChapterSortField;
  sortDir?: SortDir;
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}

/** The server accepts at most this many ids in one reorder call. */
export const REORDER_LIMIT = 500;
const PAGE = 200;

const base = (workspaceId: string, subjectId: string) =>
  `/workspaces/${workspaceId}/subjects/${subjectId}/chapters`;

export const chaptersApi = {
  list: (workspaceId: string, subjectId: string, p: ListChaptersParams = {}) =>
    getPaged<Chapter>(
      `${base(workspaceId, subjectId)}${query({
        folder_id: p.folderId,
        q: p.q?.trim(),
        sort_by: p.sortBy,
        sort_dir: p.sortDir,
        limit: p.limit,
        offset: p.offset,
        include_archived: p.includeArchived || undefined,
      })}`,
    ),

  /**
   * All chapters of the subject in display order, fetched page by page up to REORDER_LIMIT.
   * `total` is the real count on the server, so the caller can say when the list is truncated.
   */
  listAll: async (workspaceId: string, subjectId: string): Promise<Paged<Chapter>> => {
    const items: Chapter[] = [];
    let total = 0;
    while (items.length < REORDER_LIMIT) {
      const page = await chaptersApi.list(workspaceId, subjectId, {
        sortBy: "display_order",
        sortDir: "asc",
        limit: PAGE,
        offset: items.length,
      });
      total = page.total;
      items.push(...page.data);
      if (page.data.length === 0 || items.length >= page.total) break;
    }
    return { data: items.slice(0, REORDER_LIMIT), total };
  },

  get: (workspaceId: string, subjectId: string, id: string) =>
    api.get<Chapter>(`${base(workspaceId, subjectId)}/${id}`).then((r) => r.data),

  create: (workspaceId: string, subjectId: string, data: CreateChapterRequest) =>
    api.post<Chapter>(base(workspaceId, subjectId), data).then((r) => r.data),

  update: (workspaceId: string, subjectId: string, id: string, data: UpdateChapterRequest) =>
    api.patch<Chapter>(`${base(workspaceId, subjectId)}/${id}`, data).then((r) => r.data),

  /** folderId null moves the chapter out of any folder. */
  move: (workspaceId: string, subjectId: string, id: string, folderId: string | null) =>
    api
      .patch<Chapter>(`${base(workspaceId, subjectId)}/${id}`, {
        folder_id: folderId,
        folder_id_set: true,
      })
      .then((r) => r.data),

  /** Sends the full desired order of the subject's chapters (D-15). */
  reorder: (workspaceId: string, subjectId: string, chapterIds: string[]) =>
    api.post<null>(`${base(workspaceId, subjectId)}/reorder`, { chapter_ids: chapterIds }),

  archive: (workspaceId: string, subjectId: string, id: string) =>
    api.post<Chapter>(`${base(workspaceId, subjectId)}/${id}/archive`).then((r) => r.data),

  restore: (workspaceId: string, subjectId: string, id: string) =>
    api.post<Chapter>(`${base(workspaceId, subjectId)}/${id}/restore`).then((r) => r.data),

  remove: (workspaceId: string, subjectId: string, id: string) =>
    api.delete<null>(`${base(workspaceId, subjectId)}/${id}`),
};
