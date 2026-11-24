"use client";

/**
 * Context manager for a subject and everything below it.
 *
 * Mounted once by the subject route layout, so the subject, its folders and its chapters are
 * fetched a single time and shared by the environment shell, every tab and the folder/chapter
 * environments nested under the subject. The deepest id in the URL decides the scope.
 */
import { createContext, useContext, useEffect, useMemo } from "react";
import { useParams } from "next/navigation";
import { useAsync } from "@/hooks/use-async";
import { ApiRequestError } from "@/lib/api/client";
import { chaptersApi } from "@/lib/api/chapters";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { makeContext, type LearningContext } from "@/lib/learning-context";
import { descendantIds, folderPath } from "@/features/academic/tree";
import { rememberContext } from "./recent-contexts";
import type { Chapter, Folder, Subject, Workspace } from "@/types/api";

interface SubjectData {
  workspace: Workspace;
  subject: Subject;
  folders: Folder[];
  chapters: Chapter[];
  chapterTotal: number;
}

export interface LearningSpace extends SubjectData {
  ctx: LearningContext;
  /** The folder whose environment is open, if any. */
  folder: Folder | null;
  /** The chapter whose environment is open, if any. */
  chapter: Chapter | null;
  /** Folders from the top level down to the open folder (or the open chapter's folder). */
  path: Folder[];
  /** Chapters inside the current scope (the whole subject, a folder subtree, or one chapter). */
  scopedChapters: Chapter[];
  /** Folders inside the current scope (below the open folder, or all for a subject). */
  scopedFolders: Folder[];
  /** Re-fetch everything, e.g. after a chapter was created or moved. */
  reload: () => void;
  /** True while a reload is running (the previous data stays on screen). */
  refreshing: boolean;
}

type Loaded =
  { notFound: true } | ({ notFound: false } & SubjectData & { chapter: Chapter | null });

type SpaceState =
  | { status: "loading" }
  | { status: "error"; retry: () => void }
  | { status: "not-found"; what: "subject" | "folder" | "chapter" }
  | { status: "ready"; space: LearningSpace };

const SpaceContext = createContext<SpaceState | null>(null);

export function LearningSpaceProvider({ children }: { children: React.ReactNode }) {
  const params = useParams<{
    workspaceId: string;
    subjectId: string;
    folderId?: string;
    chapterId?: string;
  }>();
  const { workspaceId, subjectId } = params;
  const folderId = params.folderId;
  const chapterId = params.chapterId;

  const state = useAsync<Loaded>(async () => {
    try {
      const [workspace, subject, folders, chapters] = await Promise.all([
        workspacesApi.get(workspaceId).then((r) => r.data),
        subjectsApi.get(workspaceId, subjectId),
        foldersApi.listAll(workspaceId, subjectId),
        chaptersApi.listAll(workspaceId, subjectId),
      ]);
      // A chapter past the listing limit is still reachable by its own URL.
      let chapter: Chapter | null = null;
      if (chapterId) {
        chapter =
          chapters.data.find((c) => c.id === chapterId) ??
          (await chaptersApi.get(workspaceId, subjectId, chapterId));
      }
      return {
        notFound: false,
        workspace,
        subject,
        folders,
        chapters: chapters.data,
        chapterTotal: chapters.total,
        chapter,
      };
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) return { notFound: true };
      throw err;
    }
    // folderId is resolved from the already loaded folder list, no refetch needed
  }, [workspaceId, subjectId, chapterId]);

  const value = useMemo<SpaceState>(() => {
    const data = state.data;
    if (!data) {
      return state.error ? { status: "error", retry: state.reload } : { status: "loading" };
    }
    if (data.notFound) return { status: "not-found", what: chapterId ? "chapter" : "subject" };
    // Navigated to another subject or chapter: the previous data is not this page's data.
    if (data.subject.id !== subjectId || (chapterId && data.chapter?.id !== chapterId)) {
      return { status: "loading" };
    }

    const folder = folderId ? (data.folders.find((f) => f.id === folderId) ?? null) : null;
    if (folderId && !folder) return { status: "not-found", what: "folder" };

    const chapter = data.chapter;
    const ctx = makeContext({ workspaceId, subjectId, folderId, chapterId });
    const path = folderPath(data.folders, chapter ? chapter.folder_id : (folder?.id ?? null));

    let scopedFolders = data.folders;
    let scopedChapters = data.chapters;
    if (chapter) {
      scopedFolders = [];
      scopedChapters = [chapter];
    } else if (folder) {
      const inside = descendantIds(data.folders, folder.id);
      scopedFolders = data.folders.filter((f) => inside.has(f.id));
      inside.add(folder.id);
      scopedChapters = data.chapters.filter((c) => c.folder_id && inside.has(c.folder_id));
    }

    return {
      status: "ready",
      space: {
        workspace: data.workspace,
        subject: data.subject,
        folders: data.folders,
        chapters: data.chapters,
        chapterTotal: data.chapterTotal,
        ctx,
        folder,
        chapter,
        path,
        scopedChapters,
        scopedFolders,
        reload: state.reload,
        refreshing: state.loading,
      },
    };
  }, [
    state.data,
    state.error,
    state.loading,
    state.reload,
    workspaceId,
    subjectId,
    folderId,
    chapterId,
  ]);

  // Remember where the learner has been, for the context switcher and the command palette.
  const ready = value.status === "ready" ? value.space : null;
  useEffect(() => {
    if (!ready) return;
    const { ctx, subject, folder, chapter, workspace } = ready;
    rememberContext({
      ctx,
      label: chapter?.title ?? folder?.name ?? subject.name,
      trail: [workspace.name, ...(folder || chapter ? [subject.name] : [])].join(" / "),
      colour: subject.colour,
    });
  }, [ready]);

  return <SpaceContext.Provider value={value}>{children}</SpaceContext.Provider>;
}

/** Raw provider state, for the shell that renders loading and not-found screens. */
export function useSpaceState(): SpaceState {
  const v = useContext(SpaceContext);
  if (!v) throw new Error("useSpaceState must be used inside LearningSpaceProvider");
  return v;
}

/** The loaded learning space. Only call below the environment shell (it renders when ready). */
export function useLearningSpace(): LearningSpace {
  const v = useSpaceState();
  if (v.status !== "ready") throw new Error("Learning space is not loaded yet");
  return v.space;
}

/** The space if one is mounted and loaded, otherwise null (tools used on global pages). */
export function useOptionalLearningSpace(): LearningSpace | null {
  const v = useContext(SpaceContext);
  return v?.status === "ready" ? v.space : null;
}
