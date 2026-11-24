/**
 * Recently opened learning contexts, kept in this browser only (a per-viewer convenience for the
 * context switcher and command palette). Labels are cached names for display; ids are re-checked
 * by the backend whenever a context is opened, so a stale or edited entry just leads to a 404 page.
 */
import { makeContext, type LearningContext } from "@/lib/learning-context";

export interface RecentContext {
  ctx: LearningContext;
  label: string;
  /** "Workspace / Subject" — where the context lives. */
  trail: string;
  colour?: string | null;
  at: number;
}

const KEY = "axonweave.recent-contexts.v1";
const MAX = 8;
const EVENT = "axonweave:recent-contexts";

const keyOf = (c: LearningContext) =>
  [c.workspaceId, c.subjectId, c.folderId, c.chapterId].map((x) => x ?? "").join("|");

export function readRecentContexts(): RecentContext[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (r): r is RecentContext =>
          !!r &&
          typeof r === "object" &&
          typeof (r as RecentContext).label === "string" &&
          typeof (r as RecentContext).ctx?.workspaceId === "string",
      )
      .map((r) => ({ ...r, ctx: makeContext(r.ctx) }))
      .slice(0, MAX);
  } catch {
    return [];
  }
}

export function rememberContext(entry: Omit<RecentContext, "at">): void {
  try {
    const list = readRecentContexts().filter((r) => keyOf(r.ctx) !== keyOf(entry.ctx));
    list.unshift({ ...entry, at: Date.now() });
    window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)));
    window.dispatchEvent(new Event(EVENT));
  } catch {
    // storage unavailable (private window, blocked): the switcher simply shows no history
  }
}

export function forgetRecentContexts(): void {
  try {
    window.localStorage.removeItem(KEY);
    window.dispatchEvent(new Event(EVENT));
  } catch {
    // ignore
  }
}

export function subscribeRecentContexts(cb: () => void): () => void {
  const onStorage = (e: StorageEvent) => e.key === KEY && cb();
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", onStorage);
  };
}
