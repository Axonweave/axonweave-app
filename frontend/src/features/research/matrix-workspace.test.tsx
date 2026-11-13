import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { matrixToCsv, type ResearchMatrix, type ResearchProject } from "@/lib/api/research";
import { MatrixWorkspace } from "./matrix-workspace";

const api = vi.hoisted(() => ({
  listPapers: vi.fn(),
  list: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  edit: vi.fn(),
  addColumn: vi.fn(),
  removeColumn: vi.fn(),
  reorder: vi.fn(),
  refresh: vi.fn(),
  addPapers: vi.fn(),
  removePaper: vi.fn(),
  renameColumn: vi.fn(),
  deleteMatrix: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: {
    listPapers: api.listPapers,
    listMatrices: api.list,
    createMatrix: api.create,
    getMatrix: api.get,
    matrixEditCell: api.edit,
    matrixAddColumn: api.addColumn,
    matrixRemoveColumn: api.removeColumn,
    matrixReorder: api.reorder,
    matrixRefresh: api.refresh,
    matrixAddPapers: api.addPapers,
    matrixRemovePaper: api.removePaper,
    matrixRenameColumn: api.renameColumn,
    deleteMatrix: api.deleteMatrix,
  },
}));
vi.mock("./download", () => ({ downloadText: vi.fn(), fileStem: (t: string) => t }));

const project = { id: "p1", archived_at: null } as ResearchProject;

const matrix = (over: Partial<ResearchMatrix> = {}): ResearchMatrix =>
  ({
    id: "m1",
    research_project_id: "p1",
    title: "Review",
    description: null,
    columns: [
      { id: "c1", column_key: "paper_title", title: "Paper title", position: 0, is_default: true },
      { id: "c2", column_key: "results", title: "Results", position: 1, is_default: true },
    ],
    rows: [
      {
        paper: { id: "a", title: "Alpha paper", authors: [], publication_year: 2020 },
        cells: [
          {
            column_id: "c1",
            value: "Alpha paper",
            origin: "extracted",
            evidence: [],
            stale_evidence: 0,
          },
          {
            column_id: "c2",
            value: "Accuracy 95%",
            origin: "extracted",
            evidence: [{ id: "e1", quote: "accuracy of 95%", page_number: 2, document_id: "d1" }],
            stale_evidence: 0,
          },
        ],
      },
      {
        paper: { id: "b", title: "Beta paper", authors: [], publication_year: 2018 },
        cells: [
          {
            column_id: "c1",
            value: "Beta paper",
            origin: "extracted",
            evidence: [],
            stale_evidence: 0,
          },
          { column_id: "c2", value: "", origin: "extracted", evidence: [], stale_evidence: 0 },
        ],
      },
    ],
    created_at: "2026-11-13T00:00:00Z",
    updated_at: "2026-11-13T00:00:00Z",
    ...over,
  }) as ResearchMatrix;

beforeEach(() => {
  vi.clearAllMocks();
  api.listPapers.mockResolvedValue({
    data: [
      { id: "a", title: "Alpha paper" },
      { id: "b", title: "Beta paper" },
      { id: "c", title: "Gamma paper" },
    ],
    total: 3,
  });
  api.list.mockResolvedValue({
    data: [{ id: "m1", title: "Review", paper_count: 2, description: null }],
    total: 1,
  });
  api.get.mockResolvedValue(matrix());
  api.create.mockResolvedValue(matrix());
  api.edit.mockResolvedValue(matrix());
  api.addColumn.mockResolvedValue(matrix());
  api.refresh.mockResolvedValue(matrix());
});

async function openMatrix() {
  render(<MatrixWorkspace project={project} />);
  await userEvent.click(await screen.findByRole("button", { name: "Open matrix" }));
  return await screen.findByRole("table");
}

describe("MatrixWorkspace", () => {
  it("creates a matrix from a title and chosen papers", async () => {
    render(<MatrixWorkspace project={project} />);
    await userEvent.type(await screen.findByLabelText("Matrix title"), "Review");
    await userEvent.click(screen.getByLabelText("Alpha paper"));
    await userEvent.click(screen.getByRole("button", { name: "Create matrix" }));
    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith("p1", { title: "Review", paper_ids: ["a"] }),
    );
  });

  it("shows cells with evidence and says Not reported for empty ones", async () => {
    const table = await openMatrix();
    expect(within(table).getByText("Accuracy 95%")).toBeInTheDocument();
    expect(within(table).getByText("Not reported.")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Open original" })).toHaveAttribute(
      "href",
      "/documents/d1?page=2",
    );
  });

  it("edits a cell and sends the researcher text", async () => {
    await openMatrix();
    await userEvent.click(screen.getByRole("button", { name: "Edit Results for Alpha paper" }));
    const box = screen.getByLabelText("Edit Results");
    await userEvent.clear(box);
    await userEvent.type(box, "My reading");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.edit).toHaveBeenCalledWith("m1", "a", "c2", "My reading"));
  });

  it("marks researcher-written cells as the user's own", async () => {
    api.get.mockResolvedValue(
      matrix({
        rows: [
          {
            paper: { id: "a", title: "Alpha paper", authors: [], publication_year: 2020 },
            cells: [
              {
                column_id: "c1",
                value: "Alpha paper",
                origin: "extracted",
                evidence: [],
                stale_evidence: 0,
              },
              {
                column_id: "c2",
                value: "Mine",
                origin: "researcher",
                evidence: [],
                stale_evidence: 1,
              },
            ],
          },
        ],
      } as Partial<ResearchMatrix>),
    );
    await openMatrix();
    expect(screen.getByText("Your note")).toBeInTheDocument();
    expect(screen.getByText(/1 linked quotation is no longer available/)).toBeInTheDocument();
  });

  it("searches, sorts and groups by year", async () => {
    const table = await openMatrix();
    await userEvent.type(screen.getByLabelText("Search matrix"), "beta");
    expect(within(table).queryByText("Alpha paper")).not.toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Search matrix"));
    await userEvent.click(screen.getByLabelText("Group by year"));
    expect(within(table).getByText("2020")).toBeInTheDocument();
    expect(within(table).getByText("2018")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sort by Results" }));
    expect(screen.getByRole("button", { name: "Sort by Results" })).toHaveTextContent("▲");
  });

  it("adds, moves and removes columns and refreshes", async () => {
    await openMatrix();
    await userEvent.type(screen.getByLabelText("New column"), "Ethics");
    await userEvent.click(screen.getByRole("button", { name: "Add column" }));
    await waitFor(() => expect(api.addColumn).toHaveBeenCalledWith("m1", "Ethics"));
    await userEvent.click(screen.getByRole("button", { name: "Move Results left" }));
    await waitFor(() => expect(api.reorder).toHaveBeenCalledWith("m1", ["c2", "c1"]));
    await userEvent.click(screen.getByRole("button", { name: "Remove Results" }));
    await waitFor(() => expect(api.removeColumn).toHaveBeenCalledWith("m1", "c2"));
    await userEvent.click(screen.getByRole("button", { name: "Refresh from analyses" }));
    await waitFor(() => expect(api.refresh).toHaveBeenCalledWith("m1"));
  });

  it("is read-only for an archived project", async () => {
    render(<MatrixWorkspace project={{ ...project, archived_at: "2026-11-01T00:00:00Z" }} />);
    await userEvent.click(await screen.findByRole("button", { name: "Open matrix" }));
    await screen.findByRole("table");
    expect(screen.queryByRole("button", { name: "Add column" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit Results/ })).not.toBeInTheDocument();
  });
});

describe("matrixToCsv", () => {
  it("keeps the matrix structure and neutralises formulas", () => {
    const csv = matrixToCsv(
      matrix({
        rows: [
          {
            paper: { id: "a", title: "A", authors: [], publication_year: null },
            cells: [
              { column_id: "c1", value: "A", origin: "extracted", evidence: [], stale_evidence: 0 },
              {
                column_id: "c2",
                value: "=SUM(1)",
                origin: "researcher",
                evidence: [],
                stale_evidence: 0,
              },
            ],
          },
        ],
      } as Partial<ResearchMatrix>),
    );
    const lines = csv.split("\n");
    expect(lines[0]).toBe('"Paper title","Results"');
    expect(lines[1]).toBe(`"A","'=SUM(1)"`);
  });
});
