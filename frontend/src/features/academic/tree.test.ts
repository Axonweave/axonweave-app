import { describe, expect, it } from "vitest";
import type { Chapter, Folder } from "@/types/api";
import {
  MAX_FOLDER_DEPTH,
  buildHierarchy,
  cascadeCounts,
  chapterFolderOptions,
  descendantIds,
  folderDepth,
  folderMoveOptions,
  folderPath,
  reorderedIds,
  subtreeHeight,
} from "./tree";

function folder(id: string, name: string, parent: string | null = null, order = 0): Folder {
  return {
    id,
    name,
    subject_id: "s",
    parent_folder_id: parent,
    description: null,
    display_order: order,
    archived_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function chapter(id: string, title: string, folderId: string | null, order: number): Chapter {
  return {
    id,
    title,
    subject_id: "s",
    folder_id: folderId,
    description: null,
    display_order: order,
    status: "not_started",
    archived_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

// A (B (C)) , D   -- chapters: x in A, y in C, z loose
const folders = [
  folder("A", "A"),
  folder("B", "B", "A"),
  folder("C", "C", "B"),
  folder("D", "D", null, 1),
];
const chapters = [chapter("x", "X", "A", 0), chapter("y", "Y", "C", 1), chapter("z", "Z", null, 2)];

describe("buildHierarchy", () => {
  it("nests folders, attaches chapters and reports real counts", () => {
    const h = buildHierarchy(folders, chapters);
    expect(h.roots.map((n) => n.folder.id)).toEqual(["A", "D"]);
    expect(h.roots[0].children[0].children[0].folder.id).toBe("C");
    expect(h.roots[0].chapters.map((c) => c.id)).toEqual(["x"]);
    expect(h.roots[0].children[0].children[0].depth).toBe(3);
    expect(h.looseChapters.map((c) => c.id)).toEqual(["z"]);
    expect(h.folderCount).toBe(4);
    expect(h.chapterCount).toBe(3);
  });

  it("is empty for an empty subject", () => {
    expect(buildHierarchy([], [])).toEqual({
      roots: [],
      looseChapters: [],
      folderCount: 0,
      chapterCount: 0,
    });
  });

  it("does not lose a folder or chapter whose parent is missing from the data", () => {
    const h = buildHierarchy([folder("Q", "Q", "gone")], [chapter("c", "C", "gone", 0)]);
    expect(h.roots.map((n) => n.folder.id)).toEqual(["Q"]);
    expect(h.looseChapters.map((c) => c.id)).toEqual(["c"]);
  });

  it("orders siblings by display_order then name", () => {
    const h = buildHierarchy([folder("1", "b", null, 0), folder("2", "a", null, 0)], []);
    expect(h.roots.map((n) => n.folder.name)).toEqual(["a", "b"]);
  });
});

describe("folder geometry", () => {
  it("descendantIds excludes the folder itself", () => {
    expect([...descendantIds(folders, "A")].sort()).toEqual(["B", "C"]);
    expect(descendantIds(folders, "C").size).toBe(0);
  });

  it("folderDepth and subtreeHeight", () => {
    expect(folderDepth(folders, "A")).toBe(1);
    expect(folderDepth(folders, "C")).toBe(3);
    expect(folderDepth(folders, null)).toBe(0);
    expect(subtreeHeight(folders, "A")).toBe(3);
    expect(subtreeHeight(folders, "D")).toBe(1);
  });

  it("folderPath runs from the top level down", () => {
    expect(folderPath(folders, "C").map((f) => f.id)).toEqual(["A", "B", "C"]);
    expect(folderPath(folders, null)).toEqual([]);
  });

  it("survives a parent cycle in bad data instead of looping forever", () => {
    const cyclic = [folder("P", "P", "Q"), folder("Q", "Q", "P")];
    expect(folderDepth(cyclic, "P")).toBeLessThanOrEqual(2);
    expect(folderPath(cyclic, "P").length).toBeLessThanOrEqual(2);
  });
});

describe("folderMoveOptions", () => {
  it("never offers the folder itself or its descendants", () => {
    const ids = folderMoveOptions(folders, "A").map((o) => o.id);
    expect(ids).not.toContain("A");
    expect(ids).not.toContain("B");
    expect(ids).not.toContain("C");
    expect(ids).toContain(null);
    expect(ids).toContain("D");
  });

  it("disables targets where the subtree would not fit in 3 levels, with a reason", () => {
    // Moving D (height 1) under C (depth 3) would be level 4.
    const underC = folderMoveOptions(folders, "D").find((o) => o.id === "C");
    expect(underC?.disabled).toBe(true);
    expect(underC?.reason).toContain(String(MAX_FOLDER_DEPTH));
    // Moving D under B (depth 2) is level 3 and fine.
    expect(folderMoveOptions(folders, "D").find((o) => o.id === "B")?.disabled).toBe(false);
  });

  it("accounts for the height of the moved subtree", () => {
    // A is 3 high, so it fits only at the top level; D (depth 1) would make it 4 high.
    const opts = folderMoveOptions([...folders], "A");
    expect(opts.find((o) => o.id === "D")?.disabled).toBe(true);
    expect(opts.find((o) => o.id === null)?.disabled).toBe(false);
  });
});

describe("chapterFolderOptions", () => {
  it("lists No folder first, then folders in tree order with depth for indentation", () => {
    const opts = chapterFolderOptions(folders);
    expect(opts.map((o) => o.label)).toEqual(["No folder", "A", "B", "C", "D"]);
    expect(opts.find((o) => o.id === "C")?.depth).toBe(3);
  });
});

describe("cascadeCounts", () => {
  it("counts subfolders and every chapter inside the folder and its subfolders", () => {
    expect(cascadeCounts(folders, chapters, "A")).toEqual({ folders: 2, chapters: 2 });
    expect(cascadeCounts(folders, chapters, "D")).toEqual({ folders: 0, chapters: 0 });
  });
});

describe("reorderedIds", () => {
  const list = [
    chapter("a1", "A1", "F", 0),
    chapter("l1", "L1", null, 1),
    chapter("a2", "A2", "F", 2),
    chapter("a3", "A3", "F", 3),
  ];

  it("swaps a chapter with the next one in the same folder, skipping other groups", () => {
    expect(reorderedIds(list, "a1", "down")).toEqual(["a2", "l1", "a1", "a3"]);
    expect(reorderedIds(list, "a3", "up")).toEqual(["a1", "l1", "a3", "a2"]);
  });

  it("returns null at the edge of its group", () => {
    expect(reorderedIds(list, "a1", "up")).toBeNull();
    expect(reorderedIds(list, "a3", "down")).toBeNull();
    expect(reorderedIds(list, "l1", "down")).toBeNull();
  });

  it("returns null for an unknown chapter and keeps every id exactly once", () => {
    expect(reorderedIds(list, "nope", "up")).toBeNull();
    const out = reorderedIds(list, "a2", "up") as string[];
    expect([...out].sort()).toEqual(list.map((c) => c.id).sort());
  });

  it("sorts by display_order first, whatever order the array arrives in", () => {
    const shuffled = [list[3], list[0], list[2], list[1]];
    expect(reorderedIds(shuffled, "a1", "down")).toEqual(["a2", "l1", "a1", "a3"]);
  });
});
