import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import type { Chapter, Folder } from "@/types/api";
import { ChapterDialog } from "./chapter-dialog";
import { DeleteFolderDialog } from "./delete-folder-dialog";
import { FolderDialog } from "./folder-dialog";
import { HierarchyTree, type TreeActions } from "./hierarchy-tree";
import { buildHierarchy } from "./tree";

const api = vi.hoisted(() => ({
  folderCreate: vi.fn(),
  folderRemove: vi.fn(),
  chapterCreate: vi.fn(),
  chapterUpdate: vi.fn(),
}));

vi.mock("@/lib/api/folders", () => ({
  foldersApi: {
    create: api.folderCreate,
    update: vi.fn(),
    remove: api.folderRemove,
  },
}));
vi.mock("@/lib/api/chapters", () => ({
  chaptersApi: { create: api.chapterCreate, update: api.chapterUpdate },
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const folder = (id: string, name: string, parent: string | null = null): Folder =>
  ({
    id,
    name,
    description: null,
    parent_folder_id: parent,
    subject_id: "s1",
    archived_at: null,
  }) as unknown as Folder;

const chapter = (id: string, title: string, folderId: string | null, position: number): Chapter =>
  ({
    id,
    title,
    description: null,
    folder_id: folderId,
    status: "not_started",
    position,
    subject_id: "s1",
    archived_at: null,
  }) as unknown as Chapter;

beforeEach(() => vi.clearAllMocks());

function actions(): TreeActions {
  return {
    onAddSubfolder: vi.fn(),
    onAddChapter: vi.fn(),
    onEditFolder: vi.fn(),
    onMoveFolder: vi.fn(),
    onArchiveFolder: vi.fn(),
    onDeleteFolder: vi.fn(),
    onEditChapter: vi.fn(),
    onMoveChapter: vi.fn(),
    onArchiveChapter: vi.fn(),
    onDeleteChapter: vi.fn(),
    onReorder: vi.fn(),
  };
}

describe("HierarchyTree", () => {
  const folders = [folder("f1", "Algebra"), folder("f2", "Linear", "f1")];
  const chapters = [
    chapter("c1", "Intro", null, 0),
    chapter("c2", "Matrices", "f2", 1),
    chapter("c3", "Vectors", "f2", 2),
  ];

  function setup(a = actions()) {
    render(
      <HierarchyTree
        workspaceId="w1"
        subjectId="s1"
        hierarchy={buildHierarchy(folders, chapters)}
        chapters={chapters}
        actions={a}
      />,
    );
    return a;
  }

  it("shows folders, nested folders and chapters with links to the chapter pages", () => {
    setup();
    expect(screen.getByText("Algebra")).toBeInTheDocument();
    expect(screen.getByText("Linear")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Matrices" })).toHaveAttribute(
      "href",
      "/workspaces/w1/subjects/s1/chapters/c2",
    );
  });

  it("disables moving up at the top and down at the bottom of a group", () => {
    setup();
    expect(screen.getByRole("button", { name: "Move chapter Matrices up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move chapter Vectors down" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move chapter Matrices down" })).toBeEnabled();
  });

  it("calls onReorder from the keyboard-reachable buttons", async () => {
    const a = setup();
    await userEvent.click(screen.getByRole("button", { name: "Move chapter Matrices down" }));
    expect(a.onReorder).toHaveBeenCalledWith(expect.objectContaining({ id: "c2" }), "down");
  });

  it("offers the folder actions from its menu, and no subfolder at the maximum depth", async () => {
    const a = setup();
    await userEvent.click(screen.getByRole("button", { name: "Actions for folder Algebra" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Add subfolder" }));
    expect(a.onAddSubfolder).toHaveBeenCalledWith(expect.objectContaining({ id: "f1" }));
  });
});

describe("FolderDialog", () => {
  it("creates a folder under the given parent and trims the name", async () => {
    api.folderCreate.mockResolvedValue(folder("n", "Notes"));
    const onSaved = vi.fn();
    render(
      <FolderDialog
        open
        onOpenChange={vi.fn()}
        workspaceId="w1"
        subjectId="s1"
        parent={folder("f1", "Algebra")}
        onSaved={onSaved}
      />,
    );
    const create = screen.getByRole("button", { name: "Create folder" });
    expect(create).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Name *", { exact: true }), "  Notes  ");
    await userEvent.click(create);
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.folderCreate).toHaveBeenCalledWith(
      "w1",
      "s1",
      expect.objectContaining({ name: "Notes", parent_folder_id: "f1" }),
    );
  });

  it("shows the server's error and stays open", async () => {
    api.folderCreate.mockRejectedValue(
      new ApiRequestError("FOLDER_NAME_TAKEN", "A folder with this name already exists here.", 409),
    );
    const onSaved = vi.fn();
    render(
      <FolderDialog
        open
        onOpenChange={vi.fn()}
        workspaceId="w1"
        subjectId="s1"
        onSaved={onSaved}
      />,
    );
    await userEvent.type(screen.getByLabelText("Name *", { exact: true }), "Dup");
    await userEvent.click(screen.getByRole("button", { name: "Create folder" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A folder with this name already exists here.",
    );
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe("ChapterDialog", () => {
  it("creates a chapter in the chosen folder with the chosen status", async () => {
    api.chapterCreate.mockResolvedValue(chapter("c", "Limits", "f1", 0));
    const onSaved = vi.fn();
    render(
      <ChapterDialog
        open
        onOpenChange={vi.fn()}
        workspaceId="w1"
        subjectId="s1"
        folders={[folder("f1", "Algebra")]}
        onSaved={onSaved}
      />,
    );
    await userEvent.type(screen.getByLabelText("Title *", { exact: true }), "Limits");
    await userEvent.selectOptions(screen.getByLabelText("Folder", { exact: true }), "f1");
    await userEvent.selectOptions(screen.getByLabelText("Status", { exact: true }), "in_progress");
    await userEvent.click(screen.getByRole("button", { name: "Create chapter" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.chapterCreate).toHaveBeenCalledWith(
      "w1",
      "s1",
      expect.objectContaining({ title: "Limits", folder_id: "f1", status: "in_progress" }),
    );
  });

  it("only sends folder_id when editing changed the folder", async () => {
    api.chapterUpdate.mockResolvedValue(chapter("c1", "Intro 2", null, 0));
    render(
      <ChapterDialog
        open
        onOpenChange={vi.fn()}
        workspaceId="w1"
        subjectId="s1"
        folders={[folder("f1", "Algebra")]}
        chapter={chapter("c1", "Intro", null, 0)}
        onSaved={vi.fn()}
      />,
    );
    const title = screen.getByLabelText("Title *", { exact: true });
    await userEvent.clear(title);
    await userEvent.type(title, "Intro 2");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.chapterUpdate).toHaveBeenCalled());
    const body = api.chapterUpdate.mock.calls[0][3];
    expect(body).toMatchObject({ title: "Intro 2" });
    expect(body).not.toHaveProperty("folder_id_set");
  });
});

describe("dialog state across openings", () => {
  it("starts clean when reopened after a successful save", async () => {
    api.chapterCreate.mockResolvedValue(chapter("c", "One", null, 0));
    const props = {
      onOpenChange: vi.fn(),
      workspaceId: "w1",
      subjectId: "s1",
      folders: [] as Folder[],
      onSaved: vi.fn(),
    };
    const { rerender } = render(<ChapterDialog open {...props} />);
    await userEvent.type(screen.getByLabelText("Title *", { exact: true }), "One");
    await userEvent.click(screen.getByRole("button", { name: "Create chapter" }));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalled());

    rerender(<ChapterDialog open={false} {...props} />);
    rerender(<ChapterDialog open {...props} />);
    expect(screen.getByLabelText("Title *", { exact: true })).toHaveValue("");
    expect(screen.getByRole("button", { name: "Create chapter" })).toBeDisabled();
    expect(screen.queryByText("Saving…")).not.toBeInTheDocument();
  });
});

describe("DeleteFolderDialog", () => {
  it("falls back to a typed-name cascade confirmation on FOLDER_NOT_EMPTY", async () => {
    api.folderRemove
      .mockRejectedValueOnce(new ApiRequestError("FOLDER_NOT_EMPTY", "Folder is not empty.", 409))
      .mockResolvedValueOnce(null);
    const onDeleted = vi.fn();
    render(
      <DeleteFolderDialog
        open
        onOpenChange={vi.fn()}
        workspaceId="w1"
        subjectId="s1"
        folder={folder("f1", "Algebra")}
        counts={{ folders: 1, chapters: 2 }}
        onDeleted={onDeleted}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete folder" }));
    expect(await screen.findByText(/1 subfolder and 2 chapters/)).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: "Delete folder and everything inside" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "Algebra");
    await userEvent.click(confirm);
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(api.folderRemove).toHaveBeenLastCalledWith("w1", "s1", "f1", true);
  });
});
