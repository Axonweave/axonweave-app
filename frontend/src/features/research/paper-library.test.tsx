import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchPaper, ResearchProject } from "@/lib/api/research";
import { PaperLibrary } from "./paper-library";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  add: vi.fn(),
  update: vi.fn(),
  archive: vi.fn(),
  restore: vi.fn(),
  remove: vi.fn(),
  duplicates: vi.fn(),
  resolve: vi.fn(),
  upload: vi.fn(),
  docs: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: {
    listPapers: api.list,
    addPaper: api.add,
    updatePaper: api.update,
    archivePaper: api.archive,
    restorePaper: api.restore,
    deletePaper: api.remove,
    duplicates: api.duplicates,
    resolveDuplicate: api.resolve,
  },
}));
vi.mock("@/lib/api/documents", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/documents")>()),
  documentsApi: { upload: api.upload, list: api.docs },
}));

const project = { id: "p1", workspace_id: "w1", archived_at: null } as ResearchProject;

const paper = (over: Partial<ResearchPaper> = {}): ResearchPaper =>
  ({
    id: "a1",
    research_project_id: "p1",
    document_id: null,
    document_name: null,
    processing_status: null,
    analysis_status: "not_analysed",
    title: "Attention is all you need",
    abstract: null,
    authors: ["Ashish Vaswani"],
    publication_year: 2017,
    venue: "NeurIPS",
    publisher: null,
    doi: "10.5555/3295222",
    url: null,
    keywords: [],
    volume: null,
    issue: null,
    pages: null,
    metadata_source: "user_supplied",
    metadata_verified: false,
    status: "unread",
    archived_at: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    ...over,
  }) as ResearchPaper;

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue({ data: [paper()], total: 1 });
  api.duplicates.mockResolvedValue([]);
  api.docs.mockResolvedValue({ data: [{ id: "d1", display_name: "Paper.pdf" }], total: 1 });
  api.add.mockResolvedValue(paper());
  api.update.mockResolvedValue(paper());
  api.archive.mockResolvedValue(paper());
  api.resolve.mockResolvedValue({});
  api.remove.mockResolvedValue({});
});

describe("PaperLibrary", () => {
  it("shows metadata, provenance, file and analysis status", async () => {
    api.list.mockResolvedValue({
      data: [
        paper({ document_id: "d1", document_name: "Paper.pdf", processing_status: "completed" }),
      ],
      total: 1,
    });
    render(<PaperLibrary project={project} />);
    expect(await screen.findByText("Attention is all you need")).toBeInTheDocument();
    expect(screen.getByText(/Entered by you · not yet verified/)).toBeInTheDocument();
    expect(screen.getByText(/File: Paper.pdf \(Ready\)/)).toBeInTheDocument();
    expect(screen.getByText(/Not analysed/)).toBeInTheDocument();
  });

  it("explains the empty state and the error state", async () => {
    api.list.mockResolvedValue({ data: [], total: 0 });
    const { unmount } = render(<PaperLibrary project={project} />);
    expect(await screen.findByText(/No papers yet/)).toBeInTheDocument();
    unmount();
    api.list.mockRejectedValue(new Error("boom"));
    render(<PaperLibrary project={project} />);
    expect((await screen.findAllByText(/Could not load/)).length).toBeGreaterThan(0);
  });

  it("searches and filters through the backend", async () => {
    render(<PaperLibrary project={project} />);
    await screen.findByText("Attention is all you need");
    await userEvent.selectOptions(screen.getByLabelText("Filter by reading status"), "read");
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith("p1", expect.objectContaining({ status: "read" })),
    );
    await userEvent.type(screen.getByLabelText("Search papers"), "attention{enter}");
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith("p1", expect.objectContaining({ q: "attention" })),
    );
  });

  it("adds a paper from entered details", async () => {
    render(<PaperLibrary project={project} />);
    await screen.findByText("Attention is all you need");
    await userEvent.click(screen.getByRole("button", { name: "Enter details" }));
    const submit = screen.getByRole("button", { name: "Add paper" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Title"), "A new paper");
    await userEvent.type(screen.getByLabelText("Authors (one per line)"), "A One{enter}B Two");
    await userEvent.type(screen.getByLabelText("Publication year"), "2021");
    await userEvent.click(submit);
    await waitFor(() =>
      expect(api.add).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({
          title: "A new paper",
          authors: ["A One", "B Two"],
          publication_year: 2021,
        }),
      ),
    );
  });

  it("requires a DOI for DOI entry and sends it", async () => {
    render(<PaperLibrary project={project} />);
    await screen.findByText("Attention is all you need");
    await userEvent.click(screen.getByRole("button", { name: "Add by DOI" }));
    expect(screen.getByText(/lookup is not set up/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Title"), "By DOI");
    expect(screen.getByRole("button", { name: "Add paper" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("DOI"), "10.1000/xyz");
    await userEvent.click(screen.getByRole("button", { name: "Add paper" }));
    await waitFor(() =>
      expect(api.add).toHaveBeenCalledWith("p1", expect.objectContaining({ doi: "10.1000/xyz" })),
    );
  });

  it("uploads a PDF through the document upload, then attaches it", async () => {
    api.upload.mockResolvedValue({ documents: [{ id: "d9" }], rejected: [] });
    render(<PaperLibrary project={project} />);
    await screen.findByText("Attention is all you need");
    await userEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    const file = new File(["%PDF-1.4"], "my-paper.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("PDF file"), file);
    expect(screen.getByLabelText("Title")).toHaveValue("my-paper");
    await userEvent.click(screen.getByRole("button", { name: "Add paper" }));
    await waitFor(() => expect(api.upload).toHaveBeenCalledWith([file], { workspace_id: "w1" }));
    await waitFor(() =>
      expect(api.add).toHaveBeenCalledWith("p1", expect.objectContaining({ document_id: "d9" })),
    );
  });

  it("does not add a paper when the upload is rejected", async () => {
    api.upload.mockResolvedValue({
      documents: [],
      rejected: [{ filename: "x.pdf", code: "BAD", message: "File is not a PDF" }],
    });
    render(<PaperLibrary project={project} />);
    await screen.findByText("Attention is all you need");
    await userEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    await userEvent.upload(
      screen.getByLabelText("PDF file"),
      new File(["x"], "paper-x.pdf", { type: "application/pdf" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Add paper" }));
    await waitFor(() => expect(api.upload).toHaveBeenCalled());
    expect(api.add).not.toHaveBeenCalled();
  });

  it("edits metadata and records verification", async () => {
    render(<PaperLibrary project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    await userEvent.click(screen.getByLabelText(/I have checked this metadata/));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith(
        "a1",
        expect.objectContaining({ metadata_verified: true, title: "Attention is all you need" }),
      ),
    );
  });

  it("confirms before removing and can archive", async () => {
    render(<PaperLibrary project={project} />);
    await userEvent.click(await screen.findByRole("button", { name: "Archive" }));
    await waitFor(() => expect(api.archive).toHaveBeenCalledWith("a1"));
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(api.remove).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("a1"));
  });

  it("reviews possible duplicates: never merged without a decision", async () => {
    const brief = (id: string, title: string) => ({
      id,
      title,
      authors: ["LeCun"],
      publication_year: 2015,
      doi: null,
      has_file: false,
    });
    api.duplicates.mockResolvedValue([
      {
        paper_a: brief("a1", "Deep learning"),
        paper_b: brief("b1", "Deep Learning."),
        reason: "same_title",
        score: 1,
        shared_authors: ["lecun"],
        same_year: true,
      },
    ]);
    render(<PaperLibrary project={project} />);
    await userEvent.click(await screen.findByRole("tab", { name: /Possible duplicates \(1\)/ }));
    expect(await screen.findByText(/Same title/)).toBeInTheDocument();
    expect(api.resolve).not.toHaveBeenCalled();
    await userEvent.click(screen.getAllByRole("button", { name: "Merge into this one" })[1]);
    await waitFor(() =>
      expect(api.resolve).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({ action: "merge", survivor_id: "b1" }),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "These are different papers" }));
    await waitFor(() =>
      expect(api.resolve).toHaveBeenLastCalledWith(
        "p1",
        expect.objectContaining({ action: "not_duplicate" }),
      ),
    );
  });

  it("is read-only for an archived project", async () => {
    render(<PaperLibrary project={{ ...project, archived_at: "2026-11-03T00:00:00Z" }} />);
    await screen.findByText("Attention is all you need");
    expect(screen.queryByRole("button", { name: "Enter details" })).not.toBeInTheDocument();
  });
});
