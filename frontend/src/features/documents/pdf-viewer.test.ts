import { describe, expect, it } from "vitest";
import { findPages, regionsOnPage } from "./pdf-viewer";

const doc = (pages: string[]) => ({
  numPages: pages.length,
  getPage: async (n: number) => ({
    getTextContent: async () => ({ items: pages[n - 1].split(" ").map((str) => ({ str })) }),
  }),
});

describe("findPages", () => {
  it("returns the pages containing the term, case-insensitively", async () => {
    const d = doc(["Light reactions", "Calvin cycle", "More LIGHT here"]);
    expect(await findPages(d, "light")).toEqual([1, 3]);
  });

  it("returns nothing for an empty or absent term", async () => {
    const d = doc(["abc"]);
    expect(await findPages(d, "  ")).toEqual([]);
    expect(await findPages(d, "zzz")).toEqual([]);
  });
});

describe("regionsOnPage", () => {
  it("keeps only well-formed rectangles on the shown page", () => {
    const r = [
      { page: 1, bbox: [1, 2, 3, 4] },
      { page: 2, bbox: [1, 2, 3, 4] },
      { page: 1, bbox: [1, 2] },
    ];
    expect(regionsOnPage(r, 1)).toEqual([{ page: 1, bbox: [1, 2, 3, 4] }]);
    expect(regionsOnPage([], 1)).toEqual([]);
  });
});
