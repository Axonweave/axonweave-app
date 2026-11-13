import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  comparisonToCsv,
  type CompareResult,
  type ResearchComparison,
  type ResearchPaper,
  type ResearchProject,
} from "@/lib/api/research";
import { ComparisonWorkspace } from "./comparison-workspace";

const api = vi.hoisted(() => ({
  listPapers: vi.fn(),
  list: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: {
    listPapers: api.listPapers,
    listComparisons: api.list,
    createComparison: api.create,
    getComparison: api.get,
    patchComparison: api.patch,
    deleteComparison: api.remove,
  },
}));

const project = { id: "p1", workspace_id: "w1", archived_at: null } as ResearchProject;
const paper = (id: string, title: string, status = "analysed") =>
  ({ id, title, analysis_status: status }) as ResearchPaper;

const result: CompareResult = {
  papers: [
    { paper_id: "a", title: "Paper A", version_number: 1 },
    { paper_id: "b", title: "Paper B", version_number: 2 },
  ],
  comparability: {
    dataset: "different",
    metrics: "unknown",
    setup: "unknown",
    methodology: "unknown",
    results_directly_comparable: false,
    warnings: ["The papers use different datasets."],
  },
  rows: [
    {
      dimension: "results",
      label: "Results",
      status: "partial",
      similarities: [],
      differences: [],
      not_reported_for: ["b"],
      directly_comparable: false,
      cells: [
        {
          paper_id: "a",
          reported: true,
          items: [
            {
              text: "Accuracy was 95 percent.",
              label: null,
              origin: "reported",
              evidence: [{ quote: "accuracy of 95%", page_number: 4, document_id: "d1" }],
            },
          ],
        },
        { paper_id: "b", reported: false, items: [] },
      ],
    },
  ],
};

const comparison = (over: Partial<ResearchComparison> = {}): ResearchComparison =>
  ({
    id: "c1",
    research_project_id: "p1",
    title: "A vs B",
    paper_ids: ["a", "b"],
    configuration: {},
    result,
    notes: {},
    ...over,
  }) as unknown as ResearchComparison;

beforeEach(() => {
  vi.clearAllMocks();
  api.listPapers.mockResolvedValue({
    data: [paper("a", "Paper A"), paper("b", "Paper B"), paper("c", "Unanalysed", "not_analysed")],
    total: 3,
  });
  api.list.mockResolvedValue({ data: [], total: 0 });
  api.create.mockResolvedValue(comparison());
  api.get.mockResolvedValue(comparison());
  api.patch.mockResolvedValue(comparison({ notes: { results: "Check" } }));
  api.remove.mockResolvedValue({});
});

describe("ComparisonWorkspace", () => {
  it("offers only analysed papers and needs a title and two papers", async () => {
    render(<ComparisonWorkspace project={project} />);
    expect(await screen.findByLabelText("Paper A")).toBeInTheDocument();
    expect(screen.queryByLabelText("Unanalysed")).not.toBeInTheDocument();
    const go = screen.getByRole("button", { name: "Compare papers" });
    expect(go).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Comparison title"), "A vs B");
    await userEvent.click(screen.getByLabelText("Paper A"));
    expect(go).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Paper B"));
    expect(go).toBeEnabled();
    await userEvent.click(go);
    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith("p1", {
        title: "A vs B",
        paper_ids: ["a", "b"],
        dimensions: null,
      }),
    );
  });

  it("says what is needed when fewer than two papers are analysed", async () => {
    api.listPapers.mockResolvedValue({ data: [paper("a", "Paper A")], total: 1 });
    render(<ComparisonWorkspace project={project} />);
    expect(await screen.findByText(/at least two papers with a completed analysis/)).toBeVisible();
  });

  it("shows the matrix with evidence, missing information and the comparability warning", async () => {
    api.list.mockResolvedValue({
      data: [{ id: "c1", title: "A vs B", paper_count: 2, created_at: "2026-11-13T00:00:00Z" }],
      total: 1,
    });
    render(<ComparisonWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Open" }));
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Accuracy was 95 percent.")).toBeInTheDocument();
    expect(within(table).getByText("Not reported.")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Open original" })).toHaveAttribute(
      "href",
      "/documents/d1?page=4",
    );
    expect(screen.getByText("The papers use different datasets.")).toBeInTheDocument();
    expect(screen.getByText(/Results are not shown as directly comparable/)).toBeInTheDocument();
  });

  it("saves notes without touching the extracted result", async () => {
    api.list.mockResolvedValue({
      data: [{ id: "c1", title: "A vs B", paper_count: 2, created_at: "2026-11-13T00:00:00Z" }],
      total: 1,
    });
    render(<ComparisonWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Open" }));
    await userEvent.type(await screen.findByLabelText("Your note on Results"), "Check");
    await userEvent.click(screen.getByRole("button", { name: "Save notes" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("c1", { notes: { results: "Check" } }),
    );
  });

  it("confirms before deleting a saved comparison", async () => {
    api.list.mockResolvedValue({
      data: [{ id: "c1", title: "A vs B", paper_count: 2, created_at: "2026-11-13T00:00:00Z" }],
      total: 1,
    });
    render(<ComparisonWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(api.remove).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("c1"));
  });

  it("is read-only for an archived project", async () => {
    render(<ComparisonWorkspace project={{ ...project, archived_at: "2026-11-01T00:00:00Z" }} />);
    await screen.findByText("No saved comparisons yet.");
    expect(screen.queryByRole("button", { name: "Compare papers" })).not.toBeInTheDocument();
  });
});

describe("comparisonToCsv", () => {
  it("exports every row with evidence, marks missing information and neutralises formulas", () => {
    const csv = comparisonToCsv(result, { results: "=HYPERLINK(1)" });
    const lines = csv.split("\n");
    expect(lines[0]).toBe('"Dimension","Paper A","Paper B","Similarities","Differences","Notes"');
    expect(lines[1]).toContain("accuracy of 95%");
    expect(lines[1]).toContain("p. 4");
    expect(lines[1]).toContain('"Not reported."');
    expect(lines[1]).toContain('"\'=HYPERLINK(1)"');
  });
});
