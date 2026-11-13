import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisRun, PaperAnalysis, ResearchPaper } from "@/lib/api/research";
import { PaperAnalysisView } from "./paper-analysis";

const api = vi.hoisted(() => ({
  getPaper: vi.fn(),
  analysis: vi.fn(),
  history: vi.fn(),
  start: vi.fn(),
  cancel: vi.fn(),
  listNotes: vi.fn(),
  addNote: vi.fn(),
  editNote: vi.fn(),
  deleteNote: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: {
    getPaper: api.getPaper,
    analysis: api.analysis,
    analysisHistory: api.history,
    startAnalysis: api.start,
    cancelAnalysis: api.cancel,
    listNotes: api.listNotes,
    addNote: api.addNote,
    editNote: api.editNote,
    deleteNote: api.deleteNote,
  },
}));

const SECTIONS = [
  "research_problem",
  "objectives",
  "methodology",
  "dataset",
  "evaluation",
  "results",
  "contributions",
  "limitations",
  "future_work",
  "references",
] as const;

const paper = (over: Partial<ResearchPaper> = {}): ResearchPaper =>
  ({
    id: "a1",
    title: "Cell energy paper",
    authors: ["A. Author"],
    publication_year: 2020,
    venue: null,
    doi: null,
    document_id: "d1",
    document_name: "paper.pdf",
    metadata_source: "user_supplied",
    metadata_verified: false,
    analysis_status: "not_analysed",
    archived_at: null,
    ...over,
  }) as ResearchPaper;

const run = (over: Partial<AnalysisRun> = {}): AnalysisRun =>
  ({
    id: "r1",
    research_paper_id: "a1",
    version_number: 1,
    status: "completed",
    progress: 100,
    model_identifier: "fake-model",
    error_code: null,
    error_message: null,
    result_stats: { claims: 1, dropped: 2 },
    completed_at: "2026-11-13T10:00:00Z",
    ...over,
  }) as AnalysisRun;

const result = (over: Partial<PaperAnalysis> = {}): PaperAnalysis =>
  ({
    run: run(),
    active: null,
    sections: SECTIONS.map((section) => ({
      section,
      items:
        section === "results"
          ? [
              {
                index: 0,
                label: "Main finding",
                text: "Chloroplasts turn light into chemical energy.",
                origin: "reported",
                confidence: 0.9,
                evidence: [
                  {
                    id: "e1",
                    document_id: "d1",
                    chunk_id: "c1",
                    page_number: 3,
                    quote: "light energy into chemical",
                  },
                ],
              },
            ]
          : section === "limitations"
            ? [
                {
                  index: 0,
                  label: null,
                  text: "Only plants were studied.",
                  origin: "ai_inferred",
                  confidence: 0.5,
                  evidence: [],
                },
              ]
            : [],
    })),
    ...over,
  }) as PaperAnalysis;

beforeEach(() => {
  vi.clearAllMocks();
  api.getPaper.mockResolvedValue(paper());
  api.analysis.mockResolvedValue(result());
  api.history.mockResolvedValue({ data: [run()], total: 1 });
  api.listNotes.mockResolvedValue([]);
  api.start.mockResolvedValue(run({ status: "pending", progress: 0 }));
  api.addNote.mockResolvedValue({});
  api.cancel.mockResolvedValue(run({ status: "cancelled" }));
});

describe("PaperAnalysisView", () => {
  it("shows claims with their quotation, page and a link to the original", async () => {
    render(<PaperAnalysisView paperId="a1" />);
    await userEvent.click(await screen.findByRole("tab", { name: "Results" }));
    expect(screen.getByText("Chloroplasts turn light into chemical energy.")).toBeInTheDocument();
    expect(screen.getByText(/light energy into chemical/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open original at page 3/ })).toHaveAttribute(
      "href",
      "/documents/d1?page=3",
    );
    expect(screen.getByText("Stated in the paper")).toBeInTheDocument();
  });

  it("says plainly when a section is not reported, and never fills it in", async () => {
    render(<PaperAnalysisView paperId="a1" />);
    await userEvent.click(await screen.findByRole("tab", { name: "Methodology" }));
    expect(screen.getByText("Not reported in the available paper.")).toBeInTheDocument();
  });

  it("marks AI-inferred items as not stated by the authors", async () => {
    render(<PaperAnalysisView paperId="a1" />);
    await userEvent.click(await screen.findByRole("tab", { name: "Limitations" }));
    expect(screen.getByText("AI-inferred, not stated by the authors")).toBeInTheDocument();
  });

  it("lists every section on the overview and counts dropped claims", async () => {
    render(<PaperAnalysisView paperId="a1" />);
    expect(await screen.findByText(/2 dropped because they could not be confirmed/)).toBeVisible();
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getAllByText("1 item").length).toBe(2);
    expect(within(panel).getAllByText("Not reported in the available paper.").length).toBe(8);
  });

  it("lists all evidence on the Evidence tab", async () => {
    render(<PaperAnalysisView paperId="a1" />);
    await userEvent.click(await screen.findByRole("tab", { name: "Evidence" }));
    expect(screen.getByText(/light energy into chemical/)).toBeInTheDocument();
  });

  it("starts an analysis", async () => {
    api.analysis.mockResolvedValueOnce({ run: null, active: null, sections: [] });
    render(<PaperAnalysisView paperId="a1" />);
    expect(await screen.findByText(/has not been analysed yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Analyse paper" }));
    await waitFor(() => expect(api.start).toHaveBeenCalledWith("a1"));
  });

  it("cannot analyse a paper with no file", async () => {
    api.getPaper.mockResolvedValue(paper({ document_id: null, document_name: null }));
    api.analysis.mockResolvedValue({ run: null, active: null, sections: [] });
    render(<PaperAnalysisView paperId="a1" />);
    expect(await screen.findByText(/Attach a PDF/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse paper" })).toBeDisabled();
  });

  it("shows progress while running and can cancel", async () => {
    api.analysis.mockResolvedValue(
      result({ run: null, active: run({ status: "extracting", progress: 40 }) }),
    );
    render(<PaperAnalysisView paperId="a1" />);
    expect(await screen.findByText(/Extracting sections… 40%/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse paper" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Cancel analysis" }));
    await waitFor(() => expect(api.cancel).toHaveBeenCalledWith("a1", "r1"));
  });

  it("reports a failed re-run and keeps the earlier result visible", async () => {
    api.history.mockResolvedValue({
      data: [
        run({
          id: "r2",
          version_number: 2,
          status: "failed",
          error_message: "The AI reply could not be used.",
        }),
        run(),
      ],
      total: 2,
    });
    render(<PaperAnalysisView paperId="a1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The AI reply could not be used.");
    expect(screen.getByRole("tab", { name: "Results" })).toBeInTheDocument();
  });

  it("adds a note to a section", async () => {
    render(<PaperAnalysisView paperId="a1" />);
    await userEvent.click(await screen.findByRole("tab", { name: "Results" }));
    await userEvent.type(screen.getByLabelText("New note"), "Check sample size");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));
    await waitFor(() =>
      expect(api.addNote).toHaveBeenCalledWith("a1", {
        section: "results",
        body: "Check sample size",
      }),
    );
  });

  it("is read-only for an archived paper", async () => {
    api.getPaper.mockResolvedValue(paper({ archived_at: "2026-11-01T00:00:00Z" }));
    render(<PaperAnalysisView paperId="a1" />);
    await screen.findByRole("tab", { name: "Results" });
    expect(screen.getByRole("button", { name: "Analyse again" })).toBeDisabled();
    expect(screen.queryByLabelText("New note")).not.toBeInTheDocument();
  });
});
