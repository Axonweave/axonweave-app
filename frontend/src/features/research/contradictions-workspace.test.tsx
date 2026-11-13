import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchContradiction, ResearchProject } from "@/lib/api/research";
import { ContradictionsWorkspace } from "./contradictions-workspace";

const api = vi.hoisted(() => ({
  listContradictions: vi.fn(),
  generateContradictions: vi.fn(),
  patchContradiction: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: api,
}));

const project = { id: "p1", archived_at: null } as ResearchProject;

const side = (paper: string, text: string) => ({
  paper_id: paper,
  paper_title: `Paper ${paper}`,
  claim_type: "results",
  claim_text: text,
  evidence_id: "e",
  quote: "a verified quote",
  page_number: 4,
});

const item = (over: Partial<ResearchContradiction> = {}): ResearchContradiction =>
  ({
    id: "c1",
    research_project_id: "p1",
    claim_a: side("a", "Light conversion improves yield."),
    claim_b: side("b", "Light conversion decreases yield."),
    conditions: {
      dataset: { comparison: "different", shared: [], only_a: ["plants"], only_b: ["algae"] },
      metrics: { comparison: "same", shared: ["accuracy"], only_a: [], only_b: [] },
      setup: { comparison: "unknown", shared: [], only_a: [], only_b: [] },
    },
    category: "context_dependent",
    explanation: "The papers use different datasets.",
    confidence_label: "low",
    review_status: "unreviewed",
    researcher_explanation: null,
    analysis_version: "c1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  }) as ResearchContradiction;

beforeEach(() => {
  vi.resetAllMocks();
  api.listContradictions.mockResolvedValue({ data: [item()], total: 1 });
});

describe("ContradictionsWorkspace", () => {
  it("shows both claims with quotations, the label and the compared conditions", async () => {
    render(<ContradictionsWorkspace project={project} />);
    expect(await screen.findByText("Light conversion improves yield.")).toBeInTheDocument();
    expect(screen.getByText("Light conversion decreases yield.")).toBeInTheDocument();
    expect(screen.getAllByText(/a verified quote/)).toHaveLength(2);
    expect(screen.getByText("Different conditions", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Dataset")).toBeInTheDocument();
    expect(screen.getByText("Different")).toBeInTheDocument();
    expect(screen.getByText("Not described")).toBeInTheDocument();
  });

  it("marks, dismisses and saves an explanation", async () => {
    api.patchContradiction.mockResolvedValue(item());
    render(<ContradictionsWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Mark genuine" }));
    await waitFor(() =>
      expect(api.patchContradiction).toHaveBeenCalledWith("c1", { review_status: "genuine" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() =>
      expect(api.patchContradiction).toHaveBeenCalledWith("c1", { review_status: "dismissed" }),
    );
    await userEvent.type(screen.getByLabelText("Your explanation"), "Other cohort");
    await userEvent.click(screen.getByRole("button", { name: "Save explanation" }));
    await waitFor(() =>
      expect(api.patchContradiction).toHaveBeenCalledWith("c1", {
        researcher_explanation: "Other cohort",
      }),
    );
  });

  it("generates candidates", async () => {
    api.generateContradictions.mockResolvedValue([item()]);
    render(<ContradictionsWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Find contradictions" }));
    await waitFor(() => expect(api.generateContradictions).toHaveBeenCalledWith("p1"));
  });

  it("hides write controls for an archived project", async () => {
    render(
      <ContradictionsWorkspace project={{ ...project, archived_at: "2026-01-01T00:00:00Z" }} />,
    );
    await screen.findByText("Light conversion improves yield.");
    expect(screen.queryByRole("button", { name: "Mark genuine" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Find contradictions" })).not.toBeInTheDocument();
  });
});
