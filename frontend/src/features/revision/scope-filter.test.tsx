import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { chaptersApi } from "@/lib/api/chapters";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { ScopeFilter, type ScopeValue } from "./scope-filter";

vi.mock("@/lib/api/workspaces", () => ({ workspacesApi: { list: vi.fn() } }));
vi.mock("@/lib/api/subjects", () => ({ subjectsApi: { list: vi.fn() } }));
vi.mock("@/lib/api/chapters", () => ({ chaptersApi: { list: vi.fn() } }));

const workspaces = vi.mocked(workspacesApi);
const subjects = vi.mocked(subjectsApi);
const chapters = vi.mocked(chaptersApi);

function Harness({ onValue }: { onValue: (v: ScopeValue) => void }) {
  const [value, setValue] = useState<ScopeValue>({});
  return (
    <ScopeFilter
      value={value}
      onChange={(v) => {
        setValue(v);
        onValue(v);
      }}
    />
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  workspaces.list.mockResolvedValue({ data: [{ id: "w1", name: "Uni" }] } as never);
  subjects.list.mockResolvedValue({
    data: [{ id: "s1", name: "Biology" }],
    total: 1,
  } as never);
  chapters.list.mockResolvedValue({
    data: [{ id: "c1", title: "Cells" }],
    total: 1,
  } as never);
});

describe("ScopeFilter", () => {
  it("lists the subjects of the first workspace without asking for one", async () => {
    render(<Harness onValue={() => {}} />);
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Biology" })).toBeInTheDocument(),
    );
    expect(subjects.list).toHaveBeenCalledWith("w1", { limit: 100 });
    // one workspace: no workspace picker to clutter the form
    expect(screen.queryByLabelText("Workspace")).not.toBeInTheDocument();
  });

  it("keeps the chapter picker disabled until a subject is chosen, then loads its chapters", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    await screen.findByRole("option", { name: "Biology" });
    expect(screen.getByLabelText("Chapter")).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText("Subject"), "s1");
    expect(onValue).toHaveBeenLastCalledWith({ subject_id: "s1", chapter_id: undefined });
    await screen.findByRole("option", { name: "Cells" });
    expect(chapters.list).toHaveBeenCalledWith("w1", "s1", { limit: 100 });

    await userEvent.selectOptions(screen.getByLabelText("Chapter"), "c1");
    expect(onValue).toHaveBeenLastCalledWith({ subject_id: "s1", chapter_id: "c1" });
  });

  it("drops the chapter when the subject changes and clears everything on request", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    await screen.findByRole("option", { name: "Biology" });
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "s1");
    await screen.findByRole("option", { name: "Cells" });
    await userEvent.selectOptions(screen.getByLabelText("Chapter"), "c1");
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "");
    expect(onValue).toHaveBeenLastCalledWith({ subject_id: undefined, chapter_id: undefined });

    await userEvent.type(screen.getByLabelText("From"), "2026-11-01");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onValue).toHaveBeenLastCalledWith({});
  });

  it("limits the date range so From cannot be after To", async () => {
    render(<Harness onValue={() => {}} />);
    await screen.findByRole("option", { name: "Biology" });
    await userEvent.type(screen.getByLabelText("To"), "2026-11-10");
    expect(screen.getByLabelText("From")).toHaveAttribute("max", "2026-11-10");
  });
});
