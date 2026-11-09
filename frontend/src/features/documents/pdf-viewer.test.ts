import { describe, expect, it } from "vitest";
import { findPages } from "./pdf-viewer";

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
