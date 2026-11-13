import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LearnerDashboard, LearnerRecommendation } from "@/lib/api/learner";
import { IntelligenceView } from "./intelligence-view";

const api = vi.hoisted(() => ({
  dashboard: vi.fn(),
  recommendations: vi.fn(),
  complete: vi.fn(),
  dismiss: vi.fn(),
  state: vi.fn(),
  evidence: vi.fn(),
  misconceptions: vi.fn(),
  node: vi.fn(),
  nodeEvidence: vi.fn(),
}));

vi.mock("@/lib/api/learner", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/learner")>()),
  learnerApi: {
    dashboard: api.dashboard,
    recommendations: api.recommendations,
    completeRecommendation: api.complete,
    dismissRecommendation: api.dismiss,
    state: api.state,
    evidence: api.evidence,
    misconceptions: api.misconceptions,
  },
}));
vi.mock("@/lib/api/knowledge", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/knowledge")>()),
  knowledgeApi: { node: api.node, nodeEvidence: api.nodeEvidence },
}));
vi.mock("@/lib/api/workspaces", () => ({
  workspacesApi: { list: vi.fn().mockResolvedValue({ data: [{ id: "w1", name: "Personal" }] }) },
}));
vi.mock("@/lib/api/subjects", () => ({
  subjectsApi: {
    list: vi.fn().mockResolvedValue({ data: [{ id: "s1", name: "Biology" }], total: 1 }),
  },
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const empty = {
  weak: [],
  missing_prerequisites: [],
  misconceptions: [],
  unassessed_important: [],
  needs_revision: [],
};

function dashboard(over: Partial<LearnerDashboard> = {}): LearnerDashboard {
  return {
    overview: {
      tracked: 4,
      assessed: 2,
      sufficient_evidence: 2,
      strong: 1,
      proficient: 0,
      developing: 0,
      weak: 1,
      insufficient_evidence: 0,
      unassessed: 2,
      misconceptions: 1,
      recommendations: 1,
    },
    subjects: [
      {
        subject_id: "s1",
        subject_name: "Biology",
        total: 4,
        assessed: 2,
        distribution: { STRONG: 1, LEARNING: 1, NOT_ASSESSED: 2 },
        weak: ["Osmosis"],
        strong: ["Cells"],
        unassessed: 2,
        missing_prerequisites: 0,
      },
    ],
    concepts: [
      row("n1", "Osmosis", "LEARNING", 0.2),
      row("n2", "Cells", "STRONG", 0.9),
      row("n3", "Enzymes", "NOT_ASSESSED", null),
    ],
    gaps: {
      ...empty,
      weak: [
        {
          node_id: "n1",
          name: "Osmosis",
          subject_id: "s1",
          subject_name: "Biology",
          state: "LEARNING",
          mastery: 0.2,
          needed_for: [],
          evidence_count: 5,
        },
      ],
      misconceptions: [
        {
          id: "m1",
          node_id: "n1",
          name: "Osmosis",
          description: "Mixes it up with diffusion.",
          confidence: 0.6,
          tentative: true,
          evidence_count: 3,
          status: "suggested",
        },
      ],
    },
    note: "Counts come from your results.",
    ...over,
  } as LearnerDashboard;
}

function row(id: string, name: string, state: string, mastery: number | null) {
  return {
    node_id: id,
    name,
    subject_id: "s1",
    subject_name: "Biology",
    state,
    mastery,
    confidence: 0.5,
    evidence_count: mastery === null ? 0 : 5,
    connections: 1,
  };
}

const rec = (over: Partial<LearnerRecommendation> = {}): LearnerRecommendation =>
  ({
    id: "r1",
    recommendation_type: "revise_concept",
    knowledge_node_id: "n1",
    topic_name: "Osmosis",
    reason: "Your understanding of Osmosis is still being learned.",
    suggested_action: "Revise Osmosis.",
    priority: "high",
    score: 87,
    evidence: { rule: "revise_concept" },
    status: "pending",
    created_at: "2026-11-13T00:00:00Z",
    completed_at: null,
    ...over,
  }) as LearnerRecommendation;

beforeEach(() => {
  vi.clearAllMocks();
  api.dashboard.mockResolvedValue(dashboard());
  api.recommendations.mockResolvedValue({ items: [rec()], note: "" });
  api.complete.mockResolvedValue({});
  api.dismiss.mockResolvedValue({});
  api.state.mockResolvedValue({
    state: "LEARNING",
    mastery_estimate: 0.2,
    confidence: 0.6,
    evidence_count: 5,
    explanation: "Estimate 20% from 5 results.",
  });
  api.evidence.mockResolvedValue({ data: [], total: 0 });
  api.misconceptions.mockResolvedValue({ data: [], total: 0 });
  api.nodeEvidence.mockResolvedValue({ data: [], total: 0 });
  api.node.mockResolvedValue({
    id: "n1",
    name: "Osmosis",
    definition: "Movement of water across a membrane.",
    description: null,
    prerequisites: [],
    related: [],
  });
});

describe("IntelligenceView", () => {
  it("shows counts from the backend and keeps unassessed separate from weak", async () => {
    render(<IntelligenceView />);
    expect(await screen.findByText("Concepts tracked")).toBeInTheDocument();
    expect(screen.getByText("Not assessed").nextElementSibling).toHaveTextContent(
      "No evidence, not a weakness",
    );
    expect(screen.getByText("Weak").previousElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Not assessed").previousElementSibling).toHaveTextContent("2");
  });

  it("explains the empty state instead of showing fake data", async () => {
    api.dashboard.mockResolvedValue(
      dashboard({
        overview: { ...dashboard().overview, tracked: 0 },
        concepts: [],
        subjects: [],
      }),
    );
    render(<IntelligenceView />);
    expect(await screen.findByText(/No concepts yet/)).toBeInTheDocument();
    expect(screen.queryByText("Concepts tracked")).not.toBeInTheDocument();
  });

  it("shows an error state with retry when the dashboard fails", async () => {
    api.dashboard.mockRejectedValue(new Error("boom"));
    render(<IntelligenceView />);
    expect((await screen.findAllByText(/Could not load/)).length).toBeGreaterThan(0);
    api.dashboard.mockResolvedValue(dashboard());
    await userEvent.click((await screen.findAllByRole("button", { name: /retry|try again/i }))[0]);
    expect(await screen.findByText("Concepts tracked")).toBeInTheDocument();
  });

  it("filters by subject through the backend", async () => {
    render(<IntelligenceView />);
    await screen.findByText("Concepts tracked");
    await screen.findByRole("option", { name: "Biology" });
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "s1");
    await waitFor(() =>
      expect(api.dashboard).toHaveBeenLastCalledWith(expect.objectContaining({ subject_id: "s1" })),
    );
  });

  it("lists subject intelligence", async () => {
    render(<IntelligenceView />);
    await screen.findByText("Concepts tracked");
    await userEvent.click(screen.getByRole("tab", { name: "Subjects" }));
    expect(await screen.findByText(/4 concepts · 2 assessed · 2 not assessed/)).toBeInTheDocument();
    expect(screen.getByText(/Weak: Osmosis/)).toBeInTheDocument();
  });

  it("separates demonstrated weakness from missing evidence on the gaps tab", async () => {
    render(<IntelligenceView />);
    await screen.findByText("Concepts tracked");
    await userEvent.click(screen.getByRole("tab", { name: "Learning gaps" }));
    expect(await screen.findByText(/only mean there is no evidence yet/)).toBeInTheDocument();
    const mis = screen.getByRole("region", { name: "Repeated misconceptions" });
    expect(within(mis).getByText(/Possibly/)).toBeInTheDocument();
    expect(within(mis).getByText(/Mixes it up with diffusion/)).toBeInTheDocument();
  });

  it("filters concepts by state and search", async () => {
    render(<IntelligenceView />);
    await screen.findByText("Concepts tracked");
    await userEvent.click(screen.getByRole("tab", { name: "Concepts" }));
    await userEvent.selectOptions(screen.getByLabelText("Filter by state"), "STRONG");
    expect(screen.getByRole("button", { name: "Cells" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Osmosis" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Filter by state"), "");
    await userEvent.type(screen.getByLabelText("Search concepts"), "zzz");
    expect(screen.getByText(/No concepts match/)).toBeInTheDocument();
  });

  it("opens concept details with the mastery explanation", async () => {
    render(<IntelligenceView initialConceptId="n1" />);
    const panel = await screen.findByRole("region", { name: "Concept details" });
    expect(await within(panel).findByText("Movement of water across a membrane.")).toBeVisible();
    expect(within(panel).getByText(/Estimate 20% from 5 results/)).toBeInTheDocument();
    expect(within(panel).getByText(/No quiz or flashcard results are linked/)).toBeInTheDocument();
  });

  it("navigates recommendations to the right place and completes or dismisses them", async () => {
    render(<IntelligenceView />);
    const go = await screen.findByRole("link", { name: "Go" });
    expect(go).toHaveAttribute("href", "/study");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(api.complete).toHaveBeenCalledWith("r1"));
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(api.dismiss).toHaveBeenCalledWith("r1"));
  });

  it("routes due-card recommendations to revision", async () => {
    api.recommendations.mockResolvedValue({
      items: [rec({ recommendation_type: "review_due" })],
      note: "",
    });
    render(<IntelligenceView />);
    expect(await screen.findByRole("link", { name: "Go" })).toHaveAttribute("href", "/revision");
  });
});
