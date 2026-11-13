import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConceptLink, ConceptResearch, ResearchProject } from "@/lib/api/research";
import { ConceptLinksWorkspace } from "./concept-links-workspace";
import { ConceptResearchSection } from "./concept-research";
import { PaperConcepts } from "./paper-concepts";

const api = vi.hoisted(() => ({
  listConceptLinks: vi.fn(),
  suggestConceptLinks: vi.fn(),
  reviewConceptLink: vi.fn(),
  deleteConceptLink: vi.fn(),
  paperConcepts: vi.fn(),
  conceptResearch: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: api,
}));

const link = (over: Partial<ConceptLink> = {}): ConceptLink =>
  ({
    id: "l1",
    research_project_id: "p1",
    paper: { id: "pp1", title: "Paper A" },
    node: { id: "n1", name: "Chloroplasts", node_type: "concept" },
    match_kind: "name",
    matched_text: "chloroplasts",
    link_status: "suggested",
    claim_type: "result",
    claim_text: "Chloroplasts store energy.",
    evidence_id: "e1",
    document_id: "d1",
    page_number: 2,
    mention_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  }) as ConceptLink;

const open = { id: "p1", archived_at: null } as ResearchProject;

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
});

describe("ConceptLinksWorkspace", () => {
  it("shows an empty state and suggests links", async () => {
    api.listConceptLinks.mockResolvedValue({ data: [], total: 0 });
    api.suggestConceptLinks.mockResolvedValue([link()]);
    render(<ConceptLinksWorkspace project={open} />);
    expect(await screen.findByText(/No links yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Find concept links" }));
    await waitFor(() => expect(api.suggestConceptLinks).toHaveBeenCalledWith("p1"));
  });

  it("confirms a suggested link and links to the knowledge page", async () => {
    api.listConceptLinks.mockResolvedValue({ data: [link()], total: 1 });
    api.reviewConceptLink.mockResolvedValue(link({ link_status: "confirmed" }));
    render(<ConceptLinksWorkspace project={open} />);
    const node = await screen.findByRole("link", { name: "Chloroplasts" });
    expect(node).toHaveAttribute("href", "/knowledge?node=n1");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(api.reviewConceptLink).toHaveBeenCalledWith("l1", "confirmed"));
  });

  it("is read-only when the project is archived", async () => {
    api.listConceptLinks.mockResolvedValue({ data: [link()], total: 1 });
    render(<ConceptLinksWorkspace project={{ ...open, archived_at: "2026-01-02T00:00:00Z" }} />);
    await screen.findByRole("link", { name: "Chloroplasts" });
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Find concept links" })).toBeNull();
  });
});

describe("PaperConcepts", () => {
  it("lists related concepts", async () => {
    api.paperConcepts.mockResolvedValue([link()]);
    render(<PaperConcepts paperId="pp1" />);
    expect(await screen.findByRole("link", { name: "Chloroplasts" })).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    api.paperConcepts.mockResolvedValue([]);
    render(<PaperConcepts paperId="pp1" />);
    expect(await screen.findByText(/No concepts are linked/)).toBeInTheDocument();
  });
});

describe("ConceptResearchSection", () => {
  const claim = {
    paper_id: "pp1",
    paper_title: "Paper A",
    claim_text: "Finding one",
    page_number: 3,
  };

  it("shows findings and gaps for confirmed links", async () => {
    api.conceptResearch.mockResolvedValue({
      node: { id: "n1", name: "Chloroplasts", node_type: "concept" },
      papers: [
        {
          link_id: "l1",
          paper_id: "pp1",
          paper_title: "Paper A",
          research_project_id: "p1",
          project_title: "Proj",
          link_status: "confirmed",
          matched_text: "chloroplasts",
        },
      ],
      findings: [claim],
      methods: [],
      datasets: [],
      metrics: [],
      gaps: [{ id: "g1", title: "Open question", category: "limitation" }],
    } as unknown as ConceptResearch);
    render(<ConceptResearchSection nodeId="n1" />);
    expect(await screen.findByText(/Finding one/)).toBeInTheDocument();
    expect(screen.getByText(/Open question/)).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    api.conceptResearch.mockResolvedValue({
      node: { id: "n1", name: "X", node_type: "concept" },
      papers: [],
      findings: [],
      methods: [],
      datasets: [],
      metrics: [],
      gaps: [],
    } as unknown as ConceptResearch);
    render(<ConceptResearchSection nodeId="n1" />);
    expect(await screen.findByText(/No research papers are linked/)).toBeInTheDocument();
  });
});
