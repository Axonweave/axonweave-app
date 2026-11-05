import type { Chapter, Folder } from "@/types/api";

/** D-14: folders nest at most this deep (a top-level folder is depth 1). */
export const MAX_FOLDER_DEPTH = 3;

export interface FolderNode {
  folder: Folder;
  /** 1 = top level. */
  depth: number;
  children: FolderNode[];
  chapters: Chapter[];
}

export interface Hierarchy {
  roots: FolderNode[];
  /** Chapters that are not inside any folder. */
  looseChapters: Chapter[];
  folderCount: number;
  chapterCount: number;
}

const byOrderThenName = (a: Folder, b: Folder) =>
  a.display_order - b.display_order || a.name.localeCompare(b.name);
const byOrder = (a: Chapter, b: Chapter) =>
  a.display_order - b.display_order || a.title.localeCompare(b.title);

/**
 * Builds the folder tree and attaches chapters. Counts come from the data given, never invented.
 * A folder whose parent is missing from `folders` is treated as top level so nothing disappears.
 */
export function buildHierarchy(folders: Folder[], chapters: Chapter[]): Hierarchy {
  const ids = new Set(folders.map((f) => f.id));
  const childrenOf = new Map<string | null, Folder[]>();
  for (const f of folders) {
    const parent = f.parent_folder_id && ids.has(f.parent_folder_id) ? f.parent_folder_id : null;
    childrenOf.set(parent, [...(childrenOf.get(parent) ?? []), f]);
  }

  const chaptersIn = new Map<string | null, Chapter[]>();
  for (const c of chapters) {
    const key = c.folder_id && ids.has(c.folder_id) ? c.folder_id : null;
    chaptersIn.set(key, [...(chaptersIn.get(key) ?? []), c]);
  }

  const build = (parent: string | null, depth: number): FolderNode[] =>
    (childrenOf.get(parent) ?? []).sort(byOrderThenName).map((folder) => ({
      folder,
      depth,
      chapters: (chaptersIn.get(folder.id) ?? []).sort(byOrder),
      children: build(folder.id, depth + 1),
    }));

  return {
    roots: build(null, 1),
    looseChapters: (chaptersIn.get(null) ?? []).sort(byOrder),
    folderCount: folders.length,
    chapterCount: chapters.length,
  };
}

/** Ids of every folder below `folderId` (not including itself). */
export function descendantIds(folders: Folder[], folderId: string): Set<string> {
  const found = new Set<string>();
  let frontier = [folderId];
  while (frontier.length > 0) {
    const next = folders
      .filter((f) => f.parent_folder_id !== null && frontier.includes(f.parent_folder_id))
      .map((f) => f.id)
      .filter((id) => !found.has(id));
    next.forEach((id) => found.add(id));
    frontier = next;
  }
  return found;
}

/** Depth of a folder: 1 for top level. Unknown ids count as 0. */
export function folderDepth(folders: Folder[], folderId: string | null): number {
  let depth = 0;
  let current = folderId;
  const seen = new Set<string>();
  while (current && !seen.has(current)) {
    seen.add(current);
    const folder = folders.find((f) => f.id === current);
    if (!folder) break;
    depth += 1;
    current = folder.parent_folder_id;
  }
  return depth;
}

/** Levels in the subtree rooted at `folderId` (a folder with no subfolders = 1). */
export function subtreeHeight(folders: Folder[], folderId: string): number {
  let height = 1;
  let frontier = [folderId];
  for (;;) {
    frontier = folders
      .filter((f) => f.parent_folder_id !== null && frontier.includes(f.parent_folder_id))
      .map((f) => f.id);
    if (frontier.length === 0) return height;
    height += 1;
  }
}

/** Ancestors from the top level down to (and including) the folder itself. */
export function folderPath(folders: Folder[], folderId: string | null): Folder[] {
  const path: Folder[] = [];
  let current = folderId;
  const seen = new Set<string>();
  while (current && !seen.has(current)) {
    seen.add(current);
    const folder = folders.find((f) => f.id === current);
    if (!folder) break;
    path.unshift(folder);
    current = folder.parent_folder_id;
  }
  return path;
}

export interface FolderOption {
  /** null = top level / no folder. */
  id: string | null;
  label: string;
  depth: number;
  disabled: boolean;
  /** Why the option cannot be chosen, shown next to it. */
  reason?: string;
}

/** Folders in tree order with indentation depth, for select lists. */
function orderedFolders(folders: Folder[]): Array<{ folder: Folder; depth: number }> {
  const out: Array<{ folder: Folder; depth: number }> = [];
  const walk = (nodes: FolderNode[]) => {
    for (const n of nodes) {
      out.push({ folder: n.folder, depth: n.depth });
      walk(n.children);
    }
  };
  walk(buildHierarchy(folders, []).roots);
  return out;
}

/** Options for choosing a folder for a chapter ("No folder" plus every folder). */
export function chapterFolderOptions(folders: Folder[]): FolderOption[] {
  return [
    { id: null, label: "No folder", depth: 0, disabled: false },
    ...orderedFolders(folders).map(({ folder, depth }) => ({
      id: folder.id,
      label: folder.name,
      depth,
      disabled: false,
    })),
  ];
}

/**
 * Options for moving a folder. Itself and its descendants are left out entirely (never valid);
 * places where the folder and its subfolders would not fit in MAX_FOLDER_DEPTH levels are listed
 * but disabled with the reason, so the person sees why. The server re-checks everything.
 */
export function folderMoveOptions(folders: Folder[], movingId: string): FolderOption[] {
  const excluded = descendantIds(folders, movingId);
  excluded.add(movingId);
  const height = subtreeHeight(folders, movingId);
  const options: FolderOption[] = [{ id: null, label: "Top level", depth: 0, disabled: false }];
  for (const { folder, depth } of orderedFolders(folders)) {
    if (excluded.has(folder.id)) continue;
    const tooDeep = depth + height > MAX_FOLDER_DEPTH;
    options.push({
      id: folder.id,
      label: folder.name,
      depth,
      disabled: tooDeep,
      reason: tooDeep ? `Would exceed ${MAX_FOLDER_DEPTH} levels` : undefined,
    });
  }
  return options;
}

/**
 * Counts of what deleting a folder with cascade would remove (D-12): the folder's subfolders and
 * every chapter inside it or them. Chapters are counted from `chapters` as loaded.
 */
export function cascadeCounts(
  folders: Folder[],
  chapters: Chapter[],
  folderId: string,
): { folders: number; chapters: number } {
  const inside = descendantIds(folders, folderId);
  inside.add(folderId);
  return {
    folders: inside.size - 1,
    chapters: chapters.filter((c) => c.folder_id !== null && inside.has(c.folder_id)).length,
  };
}

/**
 * New full order of chapter ids after moving one chapter up or down among the chapters that share
 * its folder. Returns null when it is already first/last in its group. `chapters` must be in
 * current display order for the whole subject; other groups keep their positions.
 */
export function reorderedIds(
  chapters: Chapter[],
  chapterId: string,
  direction: "up" | "down",
): string[] | null {
  const ordered = [...chapters].sort(byOrder);
  const index = ordered.findIndex((c) => c.id === chapterId);
  if (index === -1) return null;
  const folderId = ordered[index].folder_id;
  const step = direction === "up" ? -1 : 1;
  let swapWith = index + step;
  while (swapWith >= 0 && swapWith < ordered.length && ordered[swapWith].folder_id !== folderId) {
    swapWith += step;
  }
  if (swapWith < 0 || swapWith >= ordered.length) return null;
  const ids = ordered.map((c) => c.id);
  [ids[index], ids[swapWith]] = [ids[swapWith], ids[index]];
  return ids;
}
