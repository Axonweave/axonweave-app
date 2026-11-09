import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { documentsApi, type DocumentRecord } from "@/lib/api/documents";
import { Library, deleteWarning } from "./library";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock("@/lib/api/workspaces", () => ({
  workspacesApi: { list: vi.fn().mockResolvedValue({ data: [{ id: "w1", name: "Uni" }] }) },
}));
vi.mock("@/lib/api/subjects", () => ({
  subjectsApi: { list: vi.fn().mockResolvedValue({ data: [], total: 0 }) },
}));
vi.mock("@/lib/api/documents", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/documents")>();
  return {
    ...actual,
    documentsApi: {
      list: vi.fn(),
      upload: vi.fn(),
      retry: vi.fn(),
      remove: vi.fn(),
    },
  };
});

const api = vi.mocked(documentsApi);
const doc = (over: Partial<DocumentRecord> = {}): DocumentRecord =>
  ({
    id: "d1",
    workspace_id: "w1",
    subject_id: null,
    folder_id: null,
    chapter_id: null,
    display_name: "Cells.pdf",
    original_filename: "Cells.pdf",
    file_type: "pdf",
    mime_type: "application/pdf",
    file_size: 2048,
    processing_status: "completed",
    active_version: 1,
    latest_version: 1,
    archived_at: null,
    created_at: "2026-11-09T10:00:00Z",
    updated_at: "2026-11-09T10:00:00Z",
    ...over,
  }) as DocumentRecord;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Library", () => {
  it("shows the empty state", async () => {
    api.list.mockResolvedValue({ data: [], total: 0 });
    render(<Library />);
    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    api.list.mockRejectedValue(new Error("x"));
    render(<Library />);
    expect(await screen.findByText("Could not load")).toBeInTheDocument();
  });

  it("lists documents with their real status", async () => {
    api.list.mockResolvedValue({
      data: [
        doc(),
        doc({ id: "d2", display_name: "Slides.pptx", processing_status: "extracting" }),
      ],
      total: 2,
    });
    render(<Library />);
    expect(await screen.findByText("Cells.pdf")).toBeInTheDocument();
    expect(screen.getByText("Ready", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Reading text")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cells.pdf" })).toHaveAttribute(
      "href",
      "/documents/d1",
    );
  });

  it("offers retry only for failed documents and calls the API", async () => {
    api.list.mockResolvedValue({
      data: [doc({ processing_status: "failed" }), doc({ id: "d2", display_name: "Ok.pdf" })],
      total: 2,
    });
    api.retry.mockResolvedValue({ success: true, data: null });
    render(<Library />);
    const retry = await screen.findByRole("button", { name: "Retry processing Cells.pdf" });
    expect(screen.queryByRole("button", { name: "Retry processing Ok.pdf" })).toBeNull();
    await userEvent.click(retry);
    await waitFor(() => expect(api.retry).toHaveBeenCalledWith("d1"));
  });

  it("confirms before deleting and states the consequence", async () => {
    api.list.mockResolvedValue({ data: [doc()], total: 1 });
    api.remove.mockResolvedValue({ success: true, data: null });
    render(<Library />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Cells.pdf" }));
    expect(api.remove).not.toHaveBeenCalled();
    expect(await screen.findByText(/cannot be undone/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("d1"));
  });

  it("does not delete when cancelled", async () => {
    api.list.mockResolvedValue({ data: [doc()], total: 1 });
    render(<Library />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Cells.pdf" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(api.remove).not.toHaveBeenCalled();
  });

  it("uploads chosen files with the workspace", async () => {
    api.list.mockResolvedValue({ data: [], total: 0 });
    api.upload.mockResolvedValue({ documents: [doc()], rejected: [] });
    render(<Library />);
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    const input = await screen.findByLabelText("Choose files to upload");
    await waitFor(() => expect(screen.getByLabelText("Workspace")).toHaveValue("w1"));
    await userEvent.upload(input, file);
    await waitFor(() =>
      expect(api.upload).toHaveBeenCalledWith(
        [file],
        expect.objectContaining({ workspace_id: "w1" }),
      ),
    );
  });
});

describe("deleteWarning", () => {
  it("names the document and the effect on citations", () => {
    expect(deleteWarning(doc())).toMatch(/Cells\.pdf/);
    expect(deleteWarning(doc())).toMatch(/only its name and page/);
  });
});
