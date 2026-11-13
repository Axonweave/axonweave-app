import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchDashboard } from "@/lib/api/research";
import { ResearchDashboardPanel } from "./research-dashboard";

const api = vi.hoisted(() => ({ dashboard: vi.fn(), projectDashboard: vi.fn() }));
vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: api,
}));

const data = (over: Partial<ResearchDashboard> = {}): ResearchDashboard =>
  ({
    counts: {
      active_projects: 2,
      papers: 5,
      papers_analysed: 3,
      papers_awaiting: 1,
      papers_failed: 1,
      comparisons: 1,
      matrices: 0,
      candidate_gaps: 4,
      contradictions_to_review: 2,
      drafts_in_progress: 1,
    },
    recent: [
      {
        kind: "paper_added",
        title: "Paper A",
        research_project_id: "p1",
        project_title: "Proj",
        at: "2026-11-01T00:00:00Z",
      },
    ],
    ...over,
  }) as ResearchDashboard;

beforeEach(() => vi.clearAllMocks());

describe("ResearchDashboardPanel", () => {
  it("shows the counts from the backend and recent activity", async () => {
    api.dashboard.mockResolvedValue(data());
    render(<ResearchDashboardPanel workspaceId="w1" />);
    expect(await screen.findByText("Candidate research gaps")).toBeInTheDocument();
    expect(screen.getByText("Active projects").nextSibling).toHaveTextContent("2");
    expect(screen.getByText("Contradictions to review").nextSibling).toHaveTextContent("2");
    expect(screen.getByText(/Paper A/)).toBeInTheDocument();
    expect(screen.getByText(/1 paper could not be analysed/)).toBeInTheDocument();
    expect(api.dashboard).toHaveBeenCalledWith("w1");
  });

  it("shows an empty state without inventing activity", async () => {
    api.projectDashboard.mockResolvedValue(
      data({
        recent: [],
        counts: { ...data().counts, active_projects: null, papers_failed: 0, papers: 0 },
      }),
    );
    render(<ResearchDashboardPanel projectId="p1" />);
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
    expect(screen.queryByText("Active projects")).toBeNull();
  });
});
