"use client";

/**
 * A study room's view state lives in the URL so it survives reloads and can be shared with
 * yourself: ?chat=<conversation>, ?chapter=<focus>, ?panel=<tool>. Ids are re-checked by the API.
 */
import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export const PANELS = [
  "files",
  "materials",
  "revision",
  "intelligence",
  "graph",
  "progress",
  "research",
  "chapters",
] as const;
export type Panel = (typeof PANELS)[number];

const ID = /^[0-9a-fA-F-]{8,64}$/;
const id = (v: string | null) => (v && ID.test(v) ? v : null);

export function useRoomState() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const chatId = id(params.get("chat"));
  const chapterId = id(params.get("chapter"));
  const rawPanel = params.get("panel");
  const panel = (PANELS as readonly string[]).includes(rawPanel ?? "") ? (rawPanel as Panel) : null;

  const set = useCallback(
    (patch: Partial<Record<"chat" | "chapter" | "panel", string | null>>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return {
    chatId,
    chapterId,
    panel,
    openChat: (c: string | null) => set({ chat: c }),
    setChapter: (c: string | null) => set({ chapter: c }),
    openPanel: (p: Panel | null) => set({ panel: p }),
  };
}
