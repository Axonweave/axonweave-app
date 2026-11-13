import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import type { ExtractionJob, SubjectExtractionRun } from "@/lib/api/knowledge";
import { GenerateSubjectGraph } from "./generate-subject-graph";

const api = vi.hoisted(() => ({
  extractSubject: vi.fn(),
  extractWeb: vi.fn(),
  extractionJobs: vi.fn(),
  clearSubjectGraph: vi.fn(),
  listDocuments: vi.fn(),
}));

vi.mock("@/lib/api/knowledge", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/knowledge")>()),
  knowledgeApi: {
    extractSubject: api.extractSubject,
    extractWeb: api.extractWeb,
    extractionJobs: api.extractionJobs,
    clearSubjectGraph: api.clearSubjectGraph,
  },
}));

vi.mock("@/lib/api/documents", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/documents")>()),
  documentsApi: { list: api.listDocuments },
}));

function runOf(over: Partial<SubjectExtractionRun> = {}): SubjectExtractionRun {
  return {
    ready: 2,
    skipped: 0,
    queued: 2,
    already_running: 0,
    not_ready: 0,
    over_cap: 0,
    job_ids: ["j1", "j2"],
    ...over,
  };
}

function job(id: string, status: ExtractionJob["status"]): ExtractionJob {
  return { id, status } as ExtractionJob;
}

function renderIt(onProgress = vi.fn()) {
  render(<GenerateSubjectGraph subjectId="s1" subjectName="Biology" onProgress={onProgress} />);
  return onProgress;
}

async function start() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Generate knowledge graph" }));
  await user.click(screen.getByRole("button", { name: "Start" }));
}

describe("GenerateSubjectGraph", () => {
  beforeEach(() => {
    api.extractSubject.mockReset();
    api.extractWeb.mockReset();
    api.extractionJobs.mockReset();
    api.clearSubjectGraph.mockReset();
    api.listDocuments.mockReset();
  });

  it("asks for confirmation and does nothing until it is given", async () => {
    renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Generate knowledge graph" }));
    expect(screen.getByText(/uses your AI quota/i)).toBeInTheDocument();
    expect(api.extractSubject).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(api.extractSubject).not.toHaveBeenCalled();
  });

  it("shows real progress from the job list and reloads the graph when jobs complete", async () => {
    api.extractSubject.mockResolvedValue(runOf());
    api.extractionJobs.mockResolvedValue({
      data: [job("j1", "completed"), job("j2", "extracting")],
      total: 2,
    });
    const onProgress = renderIt();
    await start();
    expect(await screen.findByText(/1 of 2 documents done/)).toBeInTheDocument();
    expect(onProgress).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Generating..." })).toBeDisabled();
  });

  it("reports a finished run with failures", async () => {
    api.extractSubject.mockResolvedValue(runOf());
    api.extractionJobs.mockResolvedValue({
      data: [job("j1", "completed"), job("j2", "failed")],
      total: 2,
    });
    renderIt();
    await start();
    expect(await screen.findByText(/Finished: 1 of 2 documents done, 1 failed/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Generate knowledge graph" })).toBeEnabled();
  });

  it("says so when every document was already extracted", async () => {
    api.extractSubject.mockResolvedValue(runOf({ skipped: 2, queued: 0, job_ids: [] }));
    renderIt();
    await start();
    expect(await screen.findByText(/Nothing to do: 2 of 2/)).toBeInTheDocument();
    expect(api.extractionJobs).not.toHaveBeenCalled();
  });

  it("says so when the subject has no processed documents", async () => {
    api.extractSubject.mockResolvedValue(runOf({ ready: 0, queued: 0, job_ids: [] }));
    renderIt();
    await start();
    expect(await screen.findByText(/no processed documents/i)).toBeInTheDocument();
  });

  it("mentions documents left over by the batch cap", async () => {
    api.extractSubject.mockResolvedValue(runOf({ over_cap: 5 }));
    api.extractionJobs.mockResolvedValue({
      data: [job("j1", "pending"), job("j2", "pending")],
      total: 2,
    });
    renderIt();
    await start();
    expect(await screen.findByText(/5 more documents are left/)).toBeInTheDocument();
  });

  it("shows a clear message when no AI provider is configured", async () => {
    api.extractSubject.mockRejectedValue(
      new ApiRequestError("LLM_NOT_CONFIGURED", "not configured", 503),
    );
    renderIt();
    await start();
    expect(await screen.findByRole("alert")).toHaveTextContent(/No AI provider is configured/);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate knowledge graph" })).toBeEnabled(),
    );
  });

  it("clears only after an explicit warning is confirmed, then reloads the graph", async () => {
    api.clearSubjectGraph.mockResolvedValue({ concepts: 12, relationships: 20 });
    const onProgress = renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Clear graph" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be undone/i);
    expect(api.clearSubjectGraph).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete all concepts" }));
    expect(api.clearSubjectGraph).toHaveBeenCalledWith("s1");
    expect(await screen.findByText(/Cleared 12 concepts and 20 relationships/)).toBeVisible();
    expect(onProgress).toHaveBeenCalled();
  });

  it("keeps everything when the clear is declined", async () => {
    renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Clear graph" }));
    await user.click(screen.getByRole("button", { name: "Keep them" }));
    expect(api.clearSubjectGraph).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Clear graph" })).toBeEnabled();
  });

  it("explains a refused clear while an extraction is running", async () => {
    api.clearSubjectGraph.mockRejectedValue(
      new ApiRequestError("KNOWLEDGE_EXTRACTION_RUNNING", "running", 409),
    );
    renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Clear graph" }));
    await user.click(screen.getByRole("button", { name: "Delete all concepts" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/still running/i);
  });

  it("lists which documents were extracted, with live status, when asked", async () => {
    api.listDocuments.mockResolvedValue({
      data: [
        { id: "d1", display_name: "Cell biology.pdf", processing_status: "completed" },
        { id: "d2", display_name: "Genetics.pdf", processing_status: "completed" },
        { id: "d3", display_name: "Scan.png", processing_status: "extracting" },
      ],
      total: 3,
    });
    api.extractionJobs.mockResolvedValue({
      data: [
        {
          id: "j1",
          document_id: "d1",
          status: "completed",
          progress: 100,
          result_stats: { nodes_created: 8, nodes_matched: 2, edges_created: 11, edges_matched: 1 },
        },
        {
          id: "j2",
          document_id: "d2",
          status: "failed",
          progress: 40,
          error_message: "Timed out.",
        },
      ],
      total: 2,
    });
    renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "View documents" }));
    const panel = await screen.findByTestId("subject-documents");
    expect(await within(panel).findByText("Cell biology.pdf")).toBeInTheDocument();
    expect(within(panel).getByText("Extracted")).toBeInTheDocument();
    expect(within(panel).getByText("10 concepts, 12 relationships")).toBeInTheDocument();
    expect(within(panel).getByText("Failed")).toBeInTheDocument();
    expect(within(panel).getByText("Timed out.")).toBeInTheDocument();
    expect(within(panel).getByText("Not ready")).toBeInTheDocument();
    expect(within(panel).getByText(/1 of 3 documents extracted/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hide documents" }));
    expect(screen.queryByTestId("subject-documents")).not.toBeInTheDocument();
  });

  it("marks processed documents without a run as not extracted yet", async () => {
    api.listDocuments.mockResolvedValue({
      data: [{ id: "d1", display_name: "New notes.md", processing_status: "completed" }],
      total: 1,
    });
    api.extractionJobs.mockResolvedValue({ data: [], total: 0 });
    renderIt();
    await userEvent.setup().click(screen.getByRole("button", { name: "View documents" }));
    expect(await screen.findByText("Not extracted yet")).toBeInTheDocument();
    expect(screen.getByText(/0 of 1 documents extracted/)).toBeInTheDocument();
  });

  it("says the daily AI limit is used up, not that you must wait a minute", async () => {
    api.extractSubject.mockRejectedValue(
      new ApiRequestError("AI_QUOTA_EXCEEDED", "Daily AI limit reached.", 429),
    );
    renderIt();
    await start();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/daily AI usage limit/i);
    expect(alert).toHaveTextContent(/midnight UTC/i);
    expect(alert).not.toHaveTextContent(/minute/i);
  });

  it("shows the server's own message for any other refusal", async () => {
    api.extractSubject.mockRejectedValue(
      new ApiRequestError(
        "KNOWLEDGE_TOO_MANY_ACTIVE",
        "You already have extractions running.",
        429,
      ),
    );
    renderIt();
    await start();
    expect(await screen.findByRole("alert")).toHaveTextContent(/already have extractions running/);
  });
  it("builds from the web only after a warning about quota, the subject name and accuracy", async () => {
    api.extractWeb.mockResolvedValue({ id: "w1", status: "pending", source_kind: "web" });
    api.extractionJobs.mockResolvedValue({
      data: [{ id: "w1", status: "extracting", source_kind: "web", progress: 40 }],
      total: 1,
    });
    renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Build from the web" }));
    expect(screen.getByText(/sends the subject name “Biology” to a web search/)).toBeVisible();
    expect(screen.getByText(/can be wrong or biased/)).toBeVisible();
    expect(api.extractWeb).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Search the web" }));
    expect(api.extractWeb).toHaveBeenCalledWith("s1");
    expect(await screen.findByTestId("web-status")).toHaveTextContent(/Searching the web/);
    expect(screen.getByRole("button", { name: "Generating..." })).toBeDisabled();
  });

  it("reloads the graph when the web run completes", async () => {
    api.extractWeb.mockResolvedValue({ id: "w1", status: "pending", source_kind: "web" });
    api.extractionJobs.mockResolvedValue({
      data: [{ id: "w1", status: "completed", source_kind: "web", progress: 100 }],
      total: 1,
    });
    const onProgress = renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Build from the web" }));
    await user.click(screen.getByRole("button", { name: "Search the web" }));
    expect(await screen.findByText(/Web research finished/)).toBeVisible();
    await waitFor(() => expect(onProgress).toHaveBeenCalled());
  });

  it("explains when web search is not available for the key", async () => {
    api.extractWeb.mockRejectedValue(new ApiRequestError("LLM_WEB_SEARCH_UNAVAILABLE", "x", 502));
    renderIt();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Build from the web" }));
    await user.click(screen.getByRole("button", { name: "Search the web" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Web search is not available/);
  });

  it("shows the web research run as its own row in the documents list", async () => {
    api.listDocuments.mockResolvedValue({ data: [], total: 0 });
    api.extractionJobs.mockResolvedValue({
      data: [
        {
          id: "w1",
          status: "completed",
          source_kind: "web",
          document_id: null,
          progress: 100,
          result_stats: { nodes_created: 9, nodes_matched: 0, edges_created: 7, edges_matched: 0 },
        },
      ],
      total: 1,
    });
    renderIt();
    await userEvent.setup().click(screen.getByRole("button", { name: "View documents" }));
    const panel = await screen.findByTestId("subject-documents");
    expect(within(panel).getByText("Web research")).toBeInTheDocument();
    expect(within(panel).getByText("9 concepts, 7 relationships")).toBeInTheDocument();
  });
});
