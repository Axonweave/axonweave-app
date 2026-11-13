import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchCitation, ResearchProject } from "@/lib/api/research";
import { CitationsWorkspace } from "./citations-workspace";

const api = vi.hoisted(() => ({
  listCitations: vi.fn(),
  generateCitations: vi.fn(),
  deleteCitation: vi.fn(),
  bibliography: vi.fn(),
}));
const download = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: api,
}));
vi.mock("./download", () => ({ downloadText: download, fileStem: (t: string) => t }));

const project = { id: "p1", archived_at: null } as ResearchProject;

const citation = (over: Partial<ResearchCitation> = {}): ResearchCitation =>
  ({
    id: "c1",
    research_project_id: "p1",
    research_paper_id: "a",
    paper_title: "Deep learning for cells",
    citation_style: "apa",
    formatted_citation: "Smith, J. (2020). Deep learning for cells.",
    in_text_citation: "(Smith, 2020)",
    metadata: {},
    issues: [
      {
        field: "venue",
        severity: "missing",
        code: "MISSING_VENUE",
        message: "No journal recorded.",
      },
      { field: "pages", severity: "info", code: "MISSING_PAGES", message: "No pages recorded." },
    ],
    complete: false,
    metadata_changed: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  }) as ResearchCitation;

beforeEach(() => {
  vi.resetAllMocks();
  api.listCitations.mockResolvedValue([citation()]);
});

describe("CitationsWorkspace", () => {
  it("shows the citation, the in-text form and missing metadata", async () => {
    render(<CitationsWorkspace project={project} />);
    expect(await screen.findByText(/Smith, J\. \(2020\)/)).toBeInTheDocument();
    expect(screen.getByText("(Smith, 2020)")).toBeInTheDocument();
    expect(screen.getByText("No journal recorded.")).toBeInTheDocument();
    expect(screen.getByText("No pages recorded.")).toBeInTheDocument();
  });

  it("warns when the paper's details changed and regenerates that paper only", async () => {
    api.listCitations.mockResolvedValue([citation({ metadata_changed: true })]);
    api.generateCitations.mockResolvedValue([citation()]);
    render(<CitationsWorkspace project={project} />);
    expect(await screen.findByText(/details changed after this citation/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() =>
      expect(api.generateCitations).toHaveBeenCalledWith("p1", { style: "apa", paper_ids: ["a"] }),
    );
  });

  it("changes style and generates for all papers", async () => {
    api.generateCitations.mockResolvedValue([]);
    render(<CitationsWorkspace project={project} />);
    await screen.findByText(/Smith, J\./);
    await userEvent.selectOptions(screen.getByLabelText("Style"), "ieee");
    await waitFor(() => expect(api.listCitations).toHaveBeenLastCalledWith("p1", "ieee"));
    await userEvent.click(screen.getByRole("button", { name: "Generate for all papers" }));
    await waitFor(() =>
      expect(api.generateCitations).toHaveBeenCalledWith("p1", { style: "ieee" }),
    );
  });

  it("exports the bibliography as a file", async () => {
    api.bibliography.mockResolvedValue({
      style: "apa",
      format: "text",
      filename: "bibliography-apa.txt",
      count: 1,
      content: "Smith, J. (2020).",
    });
    render(<CitationsWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Export bibliography" }));
    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(
        "bibliography-apa.txt",
        "Smith, J. (2020).",
        "text/plain;charset=utf-8",
      ),
    );
  });

  it("hides write controls for an archived project", async () => {
    render(<CitationsWorkspace project={{ ...project, archived_at: "2026-01-01T00:00:00Z" }} />);
    await screen.findByText(/Smith, J\./);
    expect(
      screen.queryByRole("button", { name: "Generate for all papers" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy citation" })).toBeInTheDocument();
  });
});
