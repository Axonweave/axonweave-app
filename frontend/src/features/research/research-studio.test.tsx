import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchProject } from "@/lib/api/research";
import { ResearchStudio } from "./research-studio";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  archive: vi.fn(),
  restore: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("@/lib/api/research", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/research")>()),
  researchApi: {
    listProjects: api.list,
    createProject: api.create,
    updateProject: api.update,
    archiveProject: api.archive,
    restoreProject: api.restore,
    deleteProject: api.remove,
  },
}));
vi.mock("./research-dashboard", () => ({
  ResearchDashboardPanel: ({ projectId }: { projectId?: string }) => (
    <div>{projectId ? "Project dashboard" : "Research dashboard"}</div>
  ),
}));
vi.mock("./paper-library", () => ({ PaperLibrary: () => <div>Paper library</div> }));
vi.mock("./contradictions-workspace", () => ({
  ContradictionsWorkspace: () => <div>Contradictions</div>,
}));
vi.mock("./citations-workspace", () => ({ CitationsWorkspace: () => <div>Citations</div> }));
vi.mock("./drafts-workspace", () => ({ DraftsWorkspace: () => <div>Drafts</div> }));
vi.mock("./concept-links-workspace", () => ({
  ConceptLinksWorkspace: () => <div>Concept links</div>,
}));
vi.mock("./gaps-workspace", () => ({ GapsWorkspace: () => <div>Gaps</div> }));
vi.mock("./matrix-workspace", () => ({ MatrixWorkspace: () => <div>Matrices</div> }));
vi.mock("./comparison-workspace", () => ({ ComparisonWorkspace: () => <div>Comparisons</div> }));
vi.mock("@/lib/api/workspaces", () => ({
  workspacesApi: { list: vi.fn().mockResolvedValue({ data: [{ id: "w1", name: "Personal" }] }) },
}));

const project = (over: Partial<ResearchProject> = {}): ResearchProject =>
  ({
    id: "p1",
    workspace_id: "w1",
    title: "Protein folding review",
    description: null,
    domain: "Biochemistry",
    research_problem: "How do chaperones help folding?",
    objectives: ["Map methods"],
    research_questions: ["What limits accuracy?", "Which datasets are used?"],
    keywords: ["protein"],
    status: "active",
    start_date: null,
    target_date: null,
    archived_at: null,
    paper_count: 3,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    ...over,
  }) as ResearchProject;

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue({ data: [project()], total: 1 });
});

describe("ResearchStudio", () => {
  it("shows project cards with status, question count and last updated", async () => {
    render(<ResearchStudio />);
    expect(await screen.findByText("Protein folding review")).toBeInTheDocument();
    const card = screen.getByRole("button", { name: /Protein folding review/ });
    expect(within(card).getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/3 papers · 2 research questions/)).toBeInTheDocument();
    expect(screen.getByText(/Updated/)).toBeInTheDocument();
  });

  it("explains the empty state", async () => {
    api.list.mockResolvedValue({ data: [], total: 0 });
    render(<ResearchStudio />);
    expect(await screen.findByText(/No research projects yet/)).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    api.list.mockRejectedValue(new Error("boom"));
    render(<ResearchStudio />);
    expect((await screen.findAllByText(/Could not load/)).length).toBeGreaterThan(0);
  });

  it("filters through the backend", async () => {
    render(<ResearchStudio />);
    await screen.findByText("Protein folding review");
    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "on_hold");
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: "on_hold" })),
    );
    await userEvent.type(screen.getByLabelText("Search projects"), "fold{enter}");
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ q: "fold" })),
    );
  });

  it("creates a project from the form, one item per line", async () => {
    api.create.mockResolvedValue(project({ id: "p2", title: "New study" }));
    render(<ResearchStudio />);
    await screen.findByText("Protein folding review");
    await userEvent.click(screen.getByRole("button", { name: "New project" }));
    const submit = screen.getByRole("button", { name: "Create project" });
    expect(submit).toBeDisabled(); // a title is required
    await userEvent.type(screen.getByLabelText("Title"), "New study");
    await userEvent.type(screen.getByLabelText(/Research questions/), "Q one{enter}Q two");
    await userEvent.click(submit);
    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "w1",
          title: "New study",
          research_questions: ["Q one", "Q two"],
        }),
      ),
    );
    expect(await screen.findByRole("region", { name: "Project overview" })).toBeInTheDocument();
  });

  it("blocks a target date before the start date", async () => {
    render(<ResearchStudio />);
    await screen.findByText("Protein folding review");
    await userEvent.click(screen.getByRole("button", { name: "New project" }));
    await userEvent.type(screen.getByLabelText("Title"), "Dated project");
    await userEvent.type(screen.getByLabelText("Start date"), "2026-05-01");
    await userEvent.type(screen.getByLabelText("Target completion date"), "2026-04-01");
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be before/);
    expect(screen.getByRole("button", { name: "Create project" })).toBeDisabled();
  });

  it("opens the overview, archives, and confirms before deleting", async () => {
    api.archive.mockResolvedValue(project({ archived_at: "2026-11-03T00:00:00Z" }));
    api.remove.mockResolvedValue({});
    render(<ResearchStudio />);
    await userEvent.click(await screen.findByText("Protein folding review"));
    const overview = await screen.findByRole("region", { name: "Project overview" });
    expect(overview).toHaveTextContent("How do chaperones help folding?");
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(api.archive).toHaveBeenCalledWith("p1"));
    expect(await screen.findByRole("button", { name: "Restore" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(api.remove).not.toHaveBeenCalled(); // needs confirmation
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("p1"));
  });

  it("navigates project sections with tabs", async () => {
    render(<ResearchStudio />);
    await screen.findByText("Protein folding review");
    expect(await screen.findByText("Research dashboard")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Protein folding review"));
    expect(await screen.findByText("Project dashboard")).toBeInTheDocument();
    const tabs = screen.getByRole("tablist");
    expect(within(tabs).getAllByRole("tab")).toHaveLength(9);
    await userEvent.click(within(tabs).getByRole("tab", { name: "Research gaps" }));
    expect(await screen.findByText("Gaps")).toBeInTheDocument();
    expect(within(screen.getByRole("tabpanel")).queryByText("Citations")).toBeNull();
    await userEvent.click(within(tabs).getByRole("tab", { name: "Knowledge graph" }));
    expect(await screen.findByText("Concept links")).toBeInTheDocument();
  });
});
