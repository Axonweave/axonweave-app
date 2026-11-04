import { api } from "./client";
import type { ArchivedItem } from "@/types/api";

/** Path of an archived item's own endpoint. Every segment comes from the owner-scoped list. */
function itemPath(item: ArchivedItem): string {
  const ws = `/workspaces/${item.workspace_id}`;
  switch (item.type) {
    case "workspace":
      return ws;
    case "subject":
      return `${ws}/subjects/${item.id}`;
    case "folder":
      return `${ws}/subjects/${item.subject_id}/folders/${item.id}`;
    case "chapter":
      return `${ws}/subjects/${item.subject_id}/chapters/${item.id}`;
  }
}

export const archivedApi = {
  restore: (item: ArchivedItem) => api.post<unknown>(`${itemPath(item)}/restore`),

  /** Permanent delete. Folders are deleted with cascade because the dialog states it (D-12). */
  remove: (item: ArchivedItem) =>
    api.delete<unknown>(`${itemPath(item)}${item.type === "folder" ? "?cascade=true" : ""}`),
};
