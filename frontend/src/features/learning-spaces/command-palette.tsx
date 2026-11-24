"use client";

/**
 * Ctrl/⌘ K: jump to any subject, folder or chapter (its learning environment) or any tool.
 * Names come from the API; nothing is listed that the backend did not return for this user.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Clock,
  CornerDownLeft,
  FileText,
  Folder as FolderIcon,
  Search,
  type LucideIcon,
} from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { chaptersApi } from "@/lib/api/chapters";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { environmentHref, makeContext } from "@/lib/learning-context";
import { roomHref } from "@/features/workspaces/current-workspace";
import { cn } from "@/lib/utils";
import { primaryNav } from "@/components/layout/app-sidebar";
import { onOpenCommandPalette } from "./command-palette-events";
import { useRecentContexts } from "./use-recent-contexts";
import type { Folder, Subject, Workspace } from "@/types/api";

interface Item {
  id: string;
  group: string;
  label: string;
  hint?: string;
  href: string;
  icon: LucideIcon | React.ElementType;
  colour?: string | null;
}

/** Subjects searched for folder and chapter names per query (keeps the request count bounded). */
const MAX_SUBJECTS_DEEP = 25;
const MAX_PER_GROUP = 8;

const norm = (s: string) => s.toLocaleLowerCase();

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);
  const [catalog, setCatalog] = useState<{ workspaces: Workspace[]; subjects: Subject[] } | null>(
    null,
  );
  // folder and chapter matches, tagged with the query they answer so stale results never show
  const [deepResult, setDeepResult] = useState<{ query: string; items: Item[] }>({
    query: "",
    items: [],
  });
  const wantsDeep = open && !!catalog && debounced.length >= 2;
  const deep = useMemo(
    () => (wantsDeep && deepResult.query === debounced ? deepResult.items : []),
    [wantsDeep, deepResult, debounced],
  );
  const searching = wantsDeep && deepResult.query !== debounced;
  const folderCache = useRef(new Map<string, Folder[]>());
  const listRef = useRef<HTMLUListElement>(null);
  const recent = useRecentContexts();

  // keyboard shortcut + programmatic open
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    const off = onOpenCommandPalette(() => setOpen(true));
    return () => {
      window.removeEventListener("keydown", onKey);
      off();
    };
  }, []);

  // load workspaces and subjects the first time the palette opens
  useEffect(() => {
    if (!open || catalog) return;
    let cancelled = false;
    (async () => {
      try {
        const workspaces = (await workspacesApi.list()).data;
        const lists = await Promise.all(
          workspaces.map((w) => subjectsApi.list(w.id, { limit: 100 }).then((r) => r.data)),
        );
        if (!cancelled) setCatalog({ workspaces, subjects: lists.flat() });
      } catch {
        if (!cancelled) setCatalog({ workspaces: [], subjects: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, catalog]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  // folders and chapters: searched on demand
  useEffect(() => {
    if (!open || !catalog || debounced.length < 2) return;
    let cancelled = false;
    const needle = norm(debounced);
    const subjects = catalog.subjects.slice(0, MAX_SUBJECTS_DEEP);
    (async () => {
      const results = await Promise.all(
        subjects.map(async (s) => {
          const items: Item[] = [];
          try {
            let folders = folderCache.current.get(s.id);
            if (!folders) {
              folders = await foldersApi.listAll(s.workspace_id, s.id);
              folderCache.current.set(s.id, folders);
            }
            for (const f of folders) {
              if (norm(f.name).includes(needle)) {
                items.push({
                  id: `f-${f.id}`,
                  group: "Folders",
                  label: f.name,
                  hint: s.name,
                  icon: FolderIcon,
                  colour: s.colour,
                  href: environmentHref(
                    makeContext({ workspaceId: s.workspace_id, subjectId: s.id, folderId: f.id }),
                  ),
                });
              }
            }
            const chapters = await chaptersApi.list(s.workspace_id, s.id, {
              q: debounced,
              limit: 5,
            });
            for (const c of chapters.data) {
              items.push({
                id: `c-${c.id}`,
                group: "Chapters",
                label: c.title,
                hint: s.name,
                icon: FileText,
                colour: s.colour,
                href: environmentHref(
                  makeContext({ workspaceId: s.workspace_id, subjectId: s.id, chapterId: c.id }),
                ),
              });
            }
          } catch {
            // one subject failing should not hide the others
          }
          return items;
        }),
      );
      if (!cancelled) setDeepResult({ query: debounced, items: results.flat() });
    })();
    return () => {
      cancelled = true;
    };
  }, [open, catalog, debounced]);

  const items = useMemo<Item[]>(() => {
    const needle = norm(q.trim());
    const match = (s: string) => !needle || norm(s).includes(needle);
    const wsName = new Map(catalog?.workspaces.map((w) => [w.id, w.name]));

    const recentItems: Item[] = needle
      ? []
      : recent.map((r) => ({
          id: `r-${r.ctx.workspaceId}-${r.ctx.subjectId}-${r.ctx.folderId}-${r.ctx.chapterId}`,
          group: "Recent",
          label: r.label,
          hint: r.trail,
          icon: Clock,
          colour: r.colour,
          href: environmentHref(r.ctx),
        }));

    const subjectItems: Item[] = (catalog?.subjects ?? [])
      .filter((s) => match(s.name))
      .slice(0, MAX_PER_GROUP)
      .map((s) => ({
        id: `s-${s.id}`,
        group: "Subjects",
        label: s.name,
        hint: wsName.get(s.workspace_id),
        icon: BookOpen,
        colour: s.colour,
        href: roomHref(s.workspace_id, s.id),
      }));

    const byGroup = (g: string) => deep.filter((d) => d.group === g).slice(0, MAX_PER_GROUP);

    const pages: Item[] = primaryNav
      .filter((n) => match(n.label))
      .map((n) => ({
        id: `p-${n.href}`,
        group: "Go to",
        label: n.label,
        icon: n.icon,
        href: n.href,
      }));

    return [
      ...recentItems,
      ...subjectItems,
      ...byGroup("Folders"),
      ...byGroup("Chapters"),
      ...pages,
    ];
  }, [q, catalog, deep, recent]);

  const go = useCallback(
    (item: Item | undefined) => {
      if (!item) return;
      setOpen(false);
      setQ("");
      router.push(item.href);
    },
    [router],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(items[active]);
    }
  };

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  let lastGroup = "";
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setQ("");
      }}
    >
      <DialogContent
        showCloseButton={false}
        className="top-[15vh] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl"
      >
        <DialogTitle className="sr-only">Search subjects, folders, chapters and pages</DialogTitle>
        <div className="border-border flex items-center gap-2 border-b px-3">
          <Search className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden="true" />
          <input
            autoFocus
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={items[active] ? `cmd-${items[active].id}` : undefined}
            aria-label="Search subjects, folders, chapters and pages"
            placeholder="Jump to a subject, folder, chapter or tool…"
            className="placeholder:text-muted-foreground h-12 min-w-0 flex-1 bg-transparent text-sm outline-none"
            value={q}
            maxLength={100}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          <kbd className="text-muted-foreground rounded border px-1.5 text-[10px]">Esc</kbd>
        </div>
        <ul
          id="command-palette-list"
          ref={listRef}
          role="listbox"
          aria-label="Results"
          className="max-h-[55vh] overflow-y-auto p-2"
        >
          {!catalog ? (
            <li className="text-muted-foreground px-3 py-6 text-center text-sm">Loading…</li>
          ) : items.length === 0 ? (
            <li className="text-muted-foreground px-3 py-6 text-center text-sm">
              {searching ? "Searching…" : "Nothing matches."}
            </li>
          ) : (
            items.map((item, i) => {
              const header = item.group !== lastGroup;
              lastGroup = item.group;
              const Icon = item.icon;
              return (
                <li key={item.id} role="presentation">
                  {header && (
                    <p className="text-muted-foreground px-2 pt-2 pb-1 text-[11px] font-semibold tracking-wider uppercase">
                      {item.group}
                    </p>
                  )}
                  <div
                    id={`cmd-${item.id}`}
                    role="option"
                    aria-selected={i === active}
                    data-index={i}
                    onMouseMove={() => setActive(i)}
                    onClick={() => go(item)}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm",
                      i === active ? "bg-accent text-accent-foreground" : "text-foreground",
                    )}
                  >
                    <span
                      className="bg-muted flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
                      style={
                        item.colour
                          ? {
                              backgroundColor: `color-mix(in oklch, ${item.colour} 18%, transparent)`,
                            }
                          : undefined
                      }
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.hint && (
                      <span className="text-muted-foreground max-w-[40%] truncate text-xs">
                        {item.hint}
                      </span>
                    )}
                    {i === active && (
                      <CornerDownLeft
                        className="text-muted-foreground h-3.5 w-3.5"
                        aria-hidden="true"
                      />
                    )}
                  </div>
                </li>
              );
            })
          )}
          {searching && items.length > 0 && (
            <li className="text-muted-foreground px-3 py-2 text-xs" role="presentation">
              Searching folders and chapters…
            </li>
          )}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
