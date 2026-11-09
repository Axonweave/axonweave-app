import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScopePicker } from "./scope-bar";

vi.mock("@/lib/api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn().mockResolvedValue({ data: [{ id: "w1", name: "Uni", is_default: true }] }),
  },
}));
vi.mock("@/lib/api/subjects", () => ({
  subjectsApi: { list: vi.fn().mockResolvedValue({ data: [{ id: "s1", name: "Biology" }] }) },
}));
vi.mock("@/lib/api/folders", () => ({
  foldersApi: { listAll: vi.fn().mockResolvedValue([{ id: "f1", name: "Cells" }]) },
}));
vi.mock("@/lib/api/chapters", () => ({
  chaptersApi: {
    listAll: vi.fn().mockResolvedValue({ data: [{ id: "c1", title: "Ch 1" }], total: 1 }),
  },
}));
vi.mock("@/lib/api/documents", () => ({
  documentsApi: {
    list: vi.fn().mockResolvedValue({ data: [{ id: "d1", display_name: "Notes.pdf" }], total: 1 }),
  },
}));

beforeEach(() => vi.clearAllMocks());

describe("ScopePicker", () => {
  it("defaults to general chat with no scope", () => {
    const onChange = vi.fn();
    render(<ScopePicker value={null} onChange={onChange} />);
    expect(screen.getByRole("combobox", { name: /ask about/i })).toHaveValue("general");
    expect(screen.queryByLabelText("Choose what to ask about")).toBeNull();
  });

  it("picks one document", async () => {
    const onChange = vi.fn();
    render(<ScopePicker value={null} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /ask about/i }), "document");
    const target = await screen.findByLabelText("Choose what to ask about");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Notes.pdf" })).toBeInTheDocument(),
    );
    await userEvent.selectOptions(target, "d1");
    expect(onChange).toHaveBeenLastCalledWith({ kind: "document", id: "d1" });
  });

  it.each([
    ["folder", "Cells", "f1"],
    ["chapter", "Ch 1", "c1"],
    ["subject", "Biology", "s1"],
    ["workspace", "Uni", "w1"],
  ])("picks a %s", async (kind, label, id) => {
    const onChange = vi.fn();
    render(<ScopePicker value={null} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /ask about/i }), kind);
    await waitFor(() => expect(screen.getByRole("option", { name: label })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Choose what to ask about"), id);
    expect(onChange).toHaveBeenLastCalledWith({ kind, id });
  });

  it("clears the scope when switching back to general", async () => {
    const onChange = vi.fn();
    render(<ScopePicker value={{ kind: "document", id: "d1" }} onChange={onChange} />);
    await userEvent.selectOptions(screen.getAllByRole("combobox")[0], "general");
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
});
