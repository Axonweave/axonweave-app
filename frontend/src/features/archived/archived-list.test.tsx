import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { archivedApi } from "@/lib/api/archived";
import { dashboardApi } from "@/lib/api/dashboard";
import { ArchivedList, deleteWarning } from "./archived-list";
import type { ArchivedItem } from "@/types/api";

vi.mock("@/lib/api/dashboard", () => ({ dashboardApi: { archived: vi.fn() } }));
vi.mock("@/lib/api/archived", () => ({ archivedApi: { restore: vi.fn(), remove: vi.fn() } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

const list = vi.mocked(dashboardApi.archived);
const archived = vi.mocked(archivedApi);

const item = (over: Partial<ArchivedItem> = {}): ArchivedItem => ({
  type: "folder",
  id: "f1",
  name: "Algebra",
  archived_at: "2026-11-04T10:00:00Z",
  workspace_id: "w1",
  workspace_name: "Uni",
  subject_id: "s1",
  subject_name: "Maths",
  ...over,
});

beforeEach(() => vi.resetAllMocks());

describe("ArchivedList", () => {
  it("shows the empty state", async () => {
    list.mockResolvedValue({ total: 0, data: [] });
    render(<ArchivedList />);
    expect(await screen.findByText("Nothing archived")).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    list.mockRejectedValue(new Error("x"));
    render(<ArchivedList />);
    expect(await screen.findByText("Could not load this section.")).toBeInTheDocument();
  });

  it("lists items with a restore button that calls the API and reloads", async () => {
    list.mockResolvedValue({ total: 1, data: [item()] });
    archived.restore.mockResolvedValue({ success: true, data: null });
    render(<ArchivedList />);
    await userEvent.click(await screen.findByRole("button", { name: "Restore folder Algebra" }));
    await waitFor(() => expect(archived.restore).toHaveBeenCalledWith(item()));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("asks for confirmation, stating the cascade, before deleting", async () => {
    list.mockResolvedValue({ total: 1, data: [item()] });
    archived.remove.mockResolvedValue({ success: true, data: null });
    render(<ArchivedList />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete folder Algebra" }));
    expect(archived.remove).not.toHaveBeenCalled();
    expect(await screen.findByText(/everything inside it/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(archived.remove).toHaveBeenCalledWith(item()));
  });

  it("does not delete when the dialog is cancelled", async () => {
    list.mockResolvedValue({ total: 1, data: [item()] });
    render(<ArchivedList />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete folder Algebra" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(archived.remove).not.toHaveBeenCalled();
  });
});

describe("deleteWarning", () => {
  it("states what each type takes with it", () => {
    expect(deleteWarning(item({ type: "workspace" }))).toMatch(/every subject, folder and chapter/);
    expect(deleteWarning(item({ type: "subject" }))).toMatch(/every folder and chapter/);
    expect(deleteWarning(item({ type: "chapter" }))).not.toMatch(/inside/);
  });
});
