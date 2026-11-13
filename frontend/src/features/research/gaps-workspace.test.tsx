import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchGap, ResearchProject } from "@/lib/api/research";
import { GapsWorkspace } from "./gaps-workspace";

const api = vi.hoisted(() => ({
  listGaps: vi.fn(),
  listPapers: vi.fn(),
  generateGaps: vi.fn(),
  patchGap: vi.fn(),
  deleteGap: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: api,
}));

const project = { id: "p1", archived_at: null } as ResearchProject;

const gap = (over: Partial<ResearchGap> = {}): ResearchGap =>
  ({
    id: "g1",
    research_project_id: "p1",
    title: "Dataset limitations reported across the collection",
    description:
      "Within the 2 analysed papers currently included in this research project, 2 state a limitation.",
    category: "dataset",
    rationale:
      "Stated by: Alpha, Beta. 1 statement in the collection describe work that addresses the same subject.",
    confidence_label: "moderate_candidate",
    limitations: "It does not show that no other research exists on the topic.",
    suggested_direction: "Consider evaluating on additional datasets.",
    validation_status: "suggested",
    analysis_version: "g1",
    edited_by_user: false,
    researcher_notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    evidence: [
      {
        id: "e1",
        research_paper_id: "a",
        research_evidence_id: "x",
        evidence_role: "supporting",
        claim_type: "limitations",
        claim_text: "The dataset is small.",
      },
      {
        id: "e2",
        research_paper_id: "b",
        research_evidence_id: null,
        evidence_role: "counter_evidence",
        claim_type: "contributions",
        claim_text: "We release a large public dataset.",
      },
    ],
    ...over,
  }) as ResearchGap;

beforeEach(() => {
  vi.resetAllMocks();
  api.listGaps.mockResolvedValue({ data: [gap()], total: 1 });
  api.listPapers.mockResolvedValue({
    data: [
      { id: "a", title: "Alpha paper" },
      { id: "b", title: "Beta paper" },
    ],
    total: 2,
  });
});

describe("GapsWorkspace", () => {
  it("shows a candidate with labels, scope wording, supporting and counter evidence", async () => {
    render(<GapsWorkspace project={project} />);
    expect(await screen.findByText(/Dataset limitations reported/)).toBeInTheDocument();
    expect(screen.getByText("Moderate candidate")).toBeInTheDocument();
    expect(screen.getByText(/does not show that no other research exists/)).toBeInTheDocument();
    expect(screen.getByText("Supporting evidence (1)")).toBeInTheDocument();
    expect(screen.getByText("Counter-evidence (1)")).toBeInTheDocument();
    expect(screen.getByText(/We release a large public dataset/)).toBeInTheDocument();
    expect(await screen.findByText(/Beta paper \(contributions\)/)).toBeInTheDocument();
  });

  it("changes the validation status", async () => {
    api.patchGap.mockResolvedValue(gap({ validation_status: "accepted" }));
    render(<GapsWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept" }));
    await waitFor(() =>
      expect(api.patchGap).toHaveBeenCalledWith("g1", { validation_status: "accepted" }),
    );
  });

  it("generates candidates and filters by category", async () => {
    api.generateGaps.mockResolvedValue([gap()]);
    render(<GapsWorkspace project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Generate gap candidates" }));
    await waitFor(() => expect(api.generateGaps).toHaveBeenCalledWith("p1"));
    await userEvent.selectOptions(screen.getByLabelText("Category"), "population");
    await waitFor(() =>
      expect(api.listGaps).toHaveBeenLastCalledWith("p1", {
        category: "population",
        status: undefined,
      }),
    );
  });

  it("hides write controls for an archived project", async () => {
    render(<GapsWorkspace project={{ ...project, archived_at: "2026-01-01T00:00:00Z" }} />);
    await screen.findByText(/Dataset limitations reported/);
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Generate gap candidates" }),
    ).not.toBeInTheDocument();
  });
});
