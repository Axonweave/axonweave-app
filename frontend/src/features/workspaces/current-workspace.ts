"use client";

/**
 * Which workspace the learner is "in". Taken from the URL when it names one; otherwise the last
 * one they opened (remembered in this browser only, a per-viewer convenience); otherwise their
 * default workspace. The id is only a hint: every request is re-checked by the backend.
 */
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useAsync } from "@/hooks/use-async";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import type { Subject, Workspace } from "@/types/api";

const KEY = "axonweave.current-workspace.v1";
const EVENT = "axonweave:current-workspace";
/** Fired after a study room is created, renamed or archived so lists elsewhere refresh. */
const ROOMS_EVENT = "axonweave:rooms-changed";

const ID = /^[0-9a-fA-F-]{8,64}$/;

export const workspaceHref = (workspaceId: string) => `/workspaces/${workspaceId}`;
export const roomHref = (workspaceId: string, subjectId: string) =>
  `/workspaces/${workspaceId}/rooms/${subjectId}`;

/** Workspace id named by the URL, if any. "/workspaces" alone names none. */
export function workspaceIdFromPath(pathname: string): string | null {
  const m = /^\/workspaces\/([^/]+)/.exec(pathname);
  return m && ID.test(m[1]) ? m[1] : null;
}

/** Study room (subject) id named by the URL, if any. */
export function roomIdFromPath(pathname: string): string | null {
  const m = /^\/workspaces\/[^/]+\/(?:rooms|subjects)\/([^/]+)/.exec(pathname);
  return m && ID.test(m[1]) ? m[1] : null;
}

function readStored(): string | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v && ID.test(v) ? v : null;
  } catch {
    return null;
  }
}

export function rememberWorkspace(id: string) {
  try {
    if (window.localStorage.getItem(KEY) === id) return;
    window.localStorage.setItem(KEY, id);
  } catch {
    /* storage unavailable: the switcher still works for this page */
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function notifyRoomsChanged() {
  window.dispatchEvent(new Event(ROOMS_EVENT));
}

export interface CurrentWorkspace {
  workspaces: Workspace[];
  current: Workspace | null;
  loading: boolean;
  reload: () => void;
}

export function useCurrentWorkspace(pathname: string): CurrentWorkspace {
  const stored = useSyncExternalStore(subscribe, readStored, () => null);
  const fromPath = workspaceIdFromPath(pathname);
  const list = useAsync(() => workspacesApi.list().then((r) => r.data), []);

  useEffect(() => {
    if (fromPath) rememberWorkspace(fromPath);
  }, [fromPath]);

  const active = (list.data ?? []).filter((w) => !w.archived_at);
  const wanted = fromPath ?? stored;
  const current =
    active.find((w) => w.id === wanted) ?? active.find((w) => w.is_default) ?? active[0] ?? null;

  return {
    workspaces: active,
    current,
    loading: list.loading && !list.data,
    reload: list.reload,
  };
}

/** The study rooms (subjects) of one workspace, refreshed whenever a room changes anywhere. */
export function useRooms(workspaceId: string | null | undefined) {
  const rooms = useAsync<Subject[]>(
    () =>
      workspaceId
        ? subjectsApi
            .list(workspaceId, { limit: 100, sortBy: "name", sortDir: "asc" })
            .then((r) => r.data)
        : Promise.resolve([]),
    [workspaceId],
  );
  const { reload } = rooms;
  const onChange = useCallback(() => reload(), [reload]);
  useEffect(() => {
    window.addEventListener(ROOMS_EVENT, onChange);
    return () => window.removeEventListener(ROOMS_EVENT, onChange);
  }, [onChange]);
  return rooms;
}
