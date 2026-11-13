import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import type {
  DraftSummary,
  ResearchDraft,
  ResearchProject,
  WritingSuggestion,
} from "@/lib/api/research";
import { DraftsWorkspace } from "./drafts-workspace";

const api = vi.hoisted(() => ({
  listDrafts: vi.fn(),
  listPapers: vi.fn(),
  createDraft: vi.fn(),
  getDraft: vi.fn(),
  patchDraft: vi.fn(),
  deleteDraft: vi.fn(),
  draftVersions: vi.fn(),
  draftVersion: vi.fn(),
  restoreDraftVersion: vi.fn(),
  checkDraft: vi.fn(),
  exportDraft: vi.fn(),
  assistDraft: vi.fn(),
}));
const download = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: api,
}));
vi.mock("./download", () => ({ downloadText: download, fileStem: (t: string) => t }));

const project = { id: "p1", archived_at: null } as ResearchProject;
const PAPER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

const summary = (): DraftSummary =>
  ({
    id: "d1",
    research_project_id: "p1",
    title: "My draft",
    document_type: "research_paper",
    status: "draft",
    citation_style: "apa",
    version_number: 1,
    word_count: 3,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }) as DraftSummary;

const draft = (over: Partial<ResearchDraft> = {}): ResearchDraft =>
  ({ ...summary(), content: "First version.", ...over }) as ResearchDraft;

const suggestion = (over: Partial<WritingSuggestion> = {}): WritingSuggestion =>
  ({
    action: "draft_section",
    text: `Chloroplasts convert light {{cite:${PAPER}}}. Yield rose by 40%.`,
    notes: "Only one source.",
    sources: [
      {
        paper_id: PAPER,
        paper_title: "Alpha paper",
        section: "results",
        claim_text: "Chloroplasts turn light into energy.",
        quote: "light energy",
      },
    ],
    invalid_markers: 1,
    checks: [
      { text: "Chloroplasts convert light.", status: "supported_single", paper_ids: [PAPER] },
      { text: "Yield rose by 40%.", status: "unsupported", paper_ids: [] },
    ],
    summary: {},
    unsupported_count: 1,
    ...over,
  }) as WritingSuggestion;

async function openDraft() {
  render(<DraftsWorkspace project={project} />);
  await userEvent.click(await screen.findByRole("button", { name: "Open" }));
  return screen.findByLabelText("Draft editor");
}

beforeEach(() => {
  vi.resetAllMocks();
  api.listDrafts.mockResolvedValue({ data: [summary()], total: 1 });
  api.listPapers.mockResolvedValue({ data: [{ id: PAPER, title: "Alpha paper" }], total: 1 });
  api.getDraft.mockResolvedValue(draft());
});

describe("DraftsWorkspace", () => {
  it("creates a draft and opens it", async () => {
    api.createDraft.mockResolvedValue(draft());
    render(<DraftsWorkspace project={project} />);
    await userEvent.type(await screen.findByLabelText("New draft title"), "My draft");
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(api.createDraft).toHaveBeenCalledWith("p1", {
        title: "My draft",
        document_type: "research_paper",
      }),
    );
    expect(await screen.findByLabelText("Draft editor")).toBeInTheDocument();
  });

  it("saves an edit against the version being edited", async () => {
    api.patchDraft.mockResolvedValue(draft({ content: "First version. More.", version_number: 2 }));
    const editor = await openDraft();
    await userEvent.type(within(editor).getByLabelText(/^Content/), " More.");
    await userEvent.click(within(editor).getByRole("button", { name: "Save new version" }));
    await waitFor(() =>
      expect(api.patchDraft).toHaveBeenCalledWith(
        "d1",
        expect.objectContaining({
          content: "First version. More.",
          expected_version: 1,
          change_source: "manual",
        }),
      ),
    );
    expect(await within(editor).findByRole("button", { name: "Saved" })).toBeDisabled();
  });

  it("explains a version conflict and keeps the unsaved text", async () => {
    api.patchDraft.mockRejectedValue(
      new ApiRequestError(
        "RESEARCH_DRAFT_VERSION_CONFLICT",
        "The draft was changed elsewhere.",
        409,
      ),
    );
    const editor = await openDraft();
    await userEvent.type(within(editor).getByLabelText(/^Content/), " Mine.");
    await userEvent.click(within(editor).getByRole("button", { name: "Save new version" }));
    expect(await within(editor).findByRole("alert")).toHaveTextContent(/changed elsewhere/);
    expect(within(editor).getByLabelText(/^Content/)).toHaveValue("First version. Mine.");
  });

  it("inserts a citation marker for the chosen paper", async () => {
    const editor = await openDraft();
    await userEvent.selectOptions(within(editor).getByLabelText("Insert a citation"), PAPER);
    await userEvent.click(within(editor).getByRole("button", { name: "Insert citation" }));
    expect((within(editor).getByLabelText(/^Content/) as HTMLTextAreaElement).value).toContain(
      `{{cite:${PAPER}}}`,
    );
    expect(within(editor).getByText("Alpha paper", { selector: "li" })).toBeInTheDocument();
  });

  it("shows an AI suggestion apart from the draft, flags unsupported claims, and saves accepted text as an AI version", async () => {
    api.assistDraft.mockResolvedValue(suggestion());
    api.patchDraft.mockResolvedValue(draft({ version_number: 2 }));
    const editor = await openDraft();
    await userEvent.click(within(editor).getByRole("button", { name: "Ask AI" }));
    const box = await within(editor).findByLabelText("AI suggestion");
    expect(within(box).getByText(/not yet part of your draft/)).toBeInTheDocument();
    expect(within(box).getByRole("alert")).toHaveTextContent(/No citation for a finding-like/);
    expect(within(box).getByText(/did not match any source/)).toBeInTheDocument();
    expect(within(editor).getByLabelText(/^Content/)).toHaveValue("First version.");
    await userEvent.click(within(box).getByRole("button", { name: "Add to the end" }));
    await waitFor(() =>
      expect(api.patchDraft).toHaveBeenCalledWith(
        "d1",
        expect.objectContaining({
          change_source: "ai_suggestion",
          expected_version: 1,
          content: expect.stringContaining(`{{cite:${PAPER}}}`),
        }),
      ),
    );
  });

  it("discarding a suggestion changes nothing", async () => {
    api.assistDraft.mockResolvedValue(suggestion());
    const editor = await openDraft();
    await userEvent.click(within(editor).getByRole("button", { name: "Ask AI" }));
    await userEvent.click(await within(editor).findByRole("button", { name: "Discard" }));
    expect(within(editor).queryByLabelText("AI suggestion")).not.toBeInTheDocument();
    expect(api.patchDraft).not.toHaveBeenCalled();
  });

  it("checks evidence, exports Markdown and restores a version", async () => {
    api.checkDraft.mockResolvedValue({
      checks: [{ text: "Yield rose by 40%.", status: "unsupported", paper_ids: [] }],
      summary: { unsupported: 1 },
      invalid_references: [],
    });
    api.exportDraft.mockResolvedValue({
      format: "markdown",
      filename: "My_draft.md",
      content: "# My draft",
      cited_count: 0,
      invalid_references: [],
    });
    api.draftVersions.mockResolvedValue([
      {
        version_number: 2,
        title: "My draft",
        change_summary: "Edited",
        change_source: "manual",
        characters: 5,
        created_at: "2026-01-02T00:00:00Z",
      },
      {
        version_number: 1,
        title: "My draft",
        change_summary: "Draft created",
        change_source: "created",
        characters: 5,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    api.getDraft.mockResolvedValue(draft({ version_number: 2, content: "Edited." }));
    api.restoreDraftVersion.mockResolvedValue(draft({ version_number: 3 }));
    const editor = await openDraft();
    await userEvent.click(within(editor).getByRole("button", { name: "Check evidence" }));
    expect(await within(editor).findByLabelText("Evidence check")).toHaveTextContent(
      /No citation for a finding-like statement: Yield rose by 40%\./,
    );
    await userEvent.click(within(editor).getByRole("button", { name: "Export Markdown" }));
    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(
        "My_draft.md",
        "# My draft",
        "text/markdown;charset=utf-8",
      ),
    );
    await userEvent.click(within(editor).getByRole("button", { name: "Version history" }));
    const history = await within(editor).findByLabelText("Version history");
    expect(within(history).getAllByRole("button", { name: "Restore" })).toHaveLength(1);
    await userEvent.click(within(history).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(api.restoreDraftVersion).toHaveBeenCalledWith("d1", 1, 2));
    expect(await within(editor).findByLabelText(/^Content/)).toHaveValue("First version.");
  });

  it("is read-only for an archived project", async () => {
    render(<DraftsWorkspace project={{ ...project, archived_at: "2026-01-01T00:00:00Z" }} />);
    await userEvent.click(await screen.findByRole("button", { name: "Open" }));
    const editor = await screen.findByLabelText("Draft editor");
    expect(within(editor).getByLabelText(/^Content/)).toHaveAttribute("readonly");
    expect(
      within(editor).queryByRole("button", { name: "Save new version" }),
    ).not.toBeInTheDocument();
    expect(within(editor).queryByLabelText("AI writing assistance")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create draft" })).not.toBeInTheDocument();
  });
});
