"use client";

import { useAsync } from "@/hooks/use-async";
import { chaptersApi } from "@/lib/api/chapters";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import type { LearningContext } from "@/lib/learning-context";

/**
 * Display name of a context received from a URL (e.g. "Open in AI Tutor"). Names are always
 * fetched from the API, never taken from the URL, so a crafted link cannot show a fake label.
 * Resolves to null when the context does not exist or is not the user's.
 */
export function useContextLabel(ctx: LearningContext | null) {
  const key = ctx ? [ctx.workspaceId, ctx.subjectId, ctx.folderId, ctx.chapterId].join("|") : "";
  return useAsync(async () => {
    if (!ctx) return null;
    try {
      const { workspaceId: ws, subjectId: sub } = ctx;
      if (ctx.chapterId && sub) return (await chaptersApi.get(ws, sub, ctx.chapterId)).title;
      if (ctx.folderId && sub) return (await foldersApi.get(ws, sub, ctx.folderId)).name;
      if (sub) return (await subjectsApi.get(ws, sub)).name;
      return (await workspacesApi.get(ws)).data.name;
    } catch {
      return null;
    }
  }, [key]);
}
