"use client";

import { GenerateButton } from "@/features/study/generate-button";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Archive, FolderPlus, Pencil, Plus, Search, Sparkles, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { chaptersApi, REORDER_LIMIT } from "@/lib/api/chapters";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { ChapterDialog } from "@/features/academic/chapter-dialog";
import { DeleteFolderDialog } from "@/features/academic/delete-folder-dialog";
import { DestructiveDialog } from "@/features/academic/destructive-dialog";
import { FolderDialog } from "@/features/academic/folder-dialog";
import { HierarchyTree } from "@/features/academic/hierarchy-tree";
import { MoveDialog } from "@/features/academic/move-dialog";
import { PageBreadcrumbs } from "@/features/academic/page-breadcrumbs";
import { RowActions } from "@/features/academic/row-actions";
import { StatusBadge } from "@/features/academic/status";
import { SubjectDialog } from "@/features/academic/subject-dialog";
import {
  buildHierarchy,
  cascadeCounts,
  chapterFolderOptions,
  folderMoveOptions,
  folderPath,
  reorderedIds,
} from "@/features/academic/tree";
import type { Chapter, Folder, Subject, Workspace } from "@/types/api";

type Loaded =
  | { notFound: true }
  | {
      notFound: false;
      workspace: Workspace;
      subject: Subject;
      folders: Folder[];
      chapters: Chapter[];
      chapterTotal: number;
    };

type DialogState =
  | { kind: "subject-edit" }
  | { kind: "subject-delete" }
  | { kind: "folder-new"; parent: Folder | null }
  | { kind: "folder-edit"; folder: Folder }
  | { kind: "folder-move"; folder: Folder }
  | { kind: "folder-delete"; folder: Folder }
  | { kind: "chapter-new"; folderId: string | null }
  | { kind: "chapter-edit"; chapter: Chapter }
  | { kind: "chapter-move"; chapter: Chapter }
  | { kind: "chapter-delete"; chapter: Chapter }
  | null;

export default function SubjectDetailPage() {
  const { workspaceId, subjectId } = useParams<{ workspaceId: string; subjectId: string }>();
  const router = useRouter();
  const { toast } = useToast();
  const [dialog, setDialog] = useState<DialogState>(null);
  const [announcement, setAnnouncement] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const pendingFocus = useRef<{ id: string; direction: "up" | "down" } | null>(null);

  const state = useAsync<Loaded>(async () => {
    try {
      const [workspace, subject, folders, chapters] = await Promise.all([
        workspacesApi.get(workspaceId).then((r) => r.data),
        subjectsApi.get(workspaceId, subjectId),
        foldersApi.listAll(workspaceId, subjectId),
        chaptersApi.listAll(workspaceId, subjectId),
      ]);
      return {
        notFound: false,
        workspace,
        subject,
        folders,
        chapters: chapters.data,
        chapterTotal: chapters.total,
      };
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) return { notFound: true };
      throw err;
    }
  }, [workspaceId, subjectId]);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  const search = useAsync(
    async () =>
      debouncedQuery
        ? chaptersApi.list(workspaceId, subjectId, { q: debouncedQuery, limit: 50 })
        : null,
    [workspaceId, subjectId, debouncedQuery, state.data],
  );

  // After a reorder the list re-renders; put keyboard focus back on the button that was used.
  useEffect(() => {
    const pending = pendingFocus.current;
    if (!pending || state.loading) return;
    pendingFocus.current = null;
    const other = pending.direction === "up" ? "down" : "up";
    for (const dir of [pending.direction, other]) {
      const el = document.getElementById(`move-${pending.id}-${dir}`) as HTMLButtonElement | null;
      if (el && !el.disabled) {
        el.focus();
        return;
      }
    }
  }, [state.data, state.loading]);

  const data = state.data;

  if (!data) {
    if (state.error) return <ErrorDisplay message={state.error} onRetry={state.reload} />;
    return (
      <div className="flex min-h-[40vh] items-center justify-center" aria-busy="true">
        <LoadingSpinner />
      </div>
    );
  }

  if (data.notFound) {
    return (
      <EmptyState
        title="Subject not found"
        description="It may have been deleted, or it is not in your account."
        action={
          <Link href="/subjects" className="text-primary underline underline-offset-4">
            Back to subjects
          </Link>
        }
      />
    );
  }

  const { workspace, subject, folders, chapters, chapterTotal } = data;
  const hierarchy = buildHierarchy(folders, chapters);
  const truncated = chapterTotal > chapters.length;
  const close = () => setDialog(null);
  const reload = () => state.reload();
  const subjectsHref = `/subjects?workspace=${workspace.id}`;

  const archiveFolder = async (folder: Folder) => {
    try {
      await foldersApi.archive(workspaceId, subjectId, folder.id);
      toast({
        title: `Folder “${folder.name}” archived`,
        description: "Restore it from Archived items.",
      });
      reload();
    } catch (err) {
      toast({
        title: "Could not archive folder",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  };

  const archiveChapter = async (chapter: Chapter) => {
    try {
      await chaptersApi.archive(workspaceId, subjectId, chapter.id);
      toast({
        title: `Chapter “${chapter.title}” archived`,
        description: "Restore it from Archived items.",
      });
      reload();
    } catch (err) {
      toast({
        title: "Could not archive chapter",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  };

  const reorder = async (chapter: Chapter, direction: "up" | "down") => {
    const ids = reorderedIds(chapters, chapter.id, direction);
    if (!ids) return;
    try {
      await chaptersApi.reorder(workspaceId, subjectId, ids);
      pendingFocus.current = { id: chapter.id, direction };
      setAnnouncement(`Moved chapter ${chapter.title} ${direction}.`);
      reload();
    } catch (err) {
      toast({
        title: "Could not reorder",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  };

  const archiveSubject = async () => {
    try {
      await subjectsApi.archive(workspaceId, subject.id);
      toast({ title: `Subject “${subject.name}” archived` });
      router.push(subjectsHref);
    } catch (err) {
      toast({
        title: "Could not archive subject",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  };

  const searching = debouncedQuery.length > 0;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageBreadcrumbs
        crumbs={[
          { label: workspace.name, href: subjectsHref },
          { label: "Subjects", href: subjectsHref },
          { label: subject.name },
        ]}
      />

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className="mt-1.5 h-4 w-4 shrink-0 rounded-full"
            style={{ backgroundColor: subject.colour ?? "#6b7280" }}
            aria-hidden="true"
          />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold break-words">
              {subject.icon ? `${subject.icon} ` : ""}
              {subject.name}
            </h1>
            {subject.description && (
              <p className="text-muted-foreground mt-1 text-sm break-words">
                {subject.description}
              </p>
            )}
            <p className="text-muted-foreground mt-2 text-sm">
              Workspace: <span className="text-foreground">{workspace.name}</span>
              {" · "}
              {hierarchy.folderCount} {hierarchy.folderCount === 1 ? "folder" : "folders"}
              {" · "}
              {chapterTotal} {chapterTotal === 1 ? "chapter" : "chapters"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/library?workspace=${workspaceId}&subject=${subjectId}`}
            className={buttonVariants({ variant: "outline" })}
          >
            Upload documents
          </Link>
          <GenerateButton preset={{ type: "subject", id: subjectId, label: subject.name }} />
          <Button variant="outline" onClick={() => setDialog({ kind: "folder-new", parent: null })}>
            <FolderPlus className="mr-2 h-4 w-4" aria-hidden="true" />
            New folder
          </Button>
          <Button onClick={() => setDialog({ kind: "chapter-new", folderId: null })}>
            <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
            New chapter
          </Button>
          <RowActions
            name={`subject ${subject.name}`}
            actions={[
              {
                label: "Edit subject",
                icon: <Pencil />,
                onSelect: () => setDialog({ kind: "subject-edit" }),
              },
              { label: "Archive subject", icon: <Archive />, onSelect: archiveSubject },
              {
                label: "Delete subject",
                icon: <Trash2 />,
                destructive: true,
                separated: true,
                onSelect: () => setDialog({ kind: "subject-delete" }),
              },
            ]}
          />
        </div>
      </header>

      <section aria-labelledby="structure-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="structure-heading" className="text-lg font-semibold">
            Folders and chapters
          </h2>
          <div className="relative w-full sm:w-64">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-2.5 left-2.5 h-4 w-4"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search chapter titles"
              aria-label="Search chapters by title"
              className="pl-8"
              maxLength={255}
            />
          </div>
        </div>

        <p className="sr-only" role="status" aria-live="polite">
          {announcement}
        </p>

        {searching ? (
          <SearchResults
            workspaceId={workspaceId}
            subjectId={subjectId}
            query={debouncedQuery}
            loading={search.loading}
            error={search.error}
            result={search.data}
            folders={folders}
            onRetry={search.reload}
          />
        ) : hierarchy.folderCount === 0 && hierarchy.chapterCount === 0 ? (
          <EmptyState
            title="Nothing here yet"
            description="Create a folder to group your material, or add a chapter straight away."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button
                  variant="outline"
                  onClick={() => setDialog({ kind: "folder-new", parent: null })}
                >
                  New folder
                </Button>
                <Button onClick={() => setDialog({ kind: "chapter-new", folderId: null })}>
                  New chapter
                </Button>
              </div>
            }
          />
        ) : (
          <>
            <HierarchyTree
              workspaceId={workspaceId}
              subjectId={subjectId}
              hierarchy={hierarchy}
              chapters={chapters}
              actions={{
                onAddSubfolder: (folder) => setDialog({ kind: "folder-new", parent: folder }),
                onAddChapter: (folderId) => setDialog({ kind: "chapter-new", folderId }),
                onEditFolder: (folder) => setDialog({ kind: "folder-edit", folder }),
                onMoveFolder: (folder) => setDialog({ kind: "folder-move", folder }),
                onArchiveFolder: archiveFolder,
                onDeleteFolder: (folder) => setDialog({ kind: "folder-delete", folder }),
                onEditChapter: (chapter) => setDialog({ kind: "chapter-edit", chapter }),
                onMoveChapter: (chapter) => setDialog({ kind: "chapter-move", chapter }),
                onArchiveChapter: archiveChapter,
                onDeleteChapter: (chapter) => setDialog({ kind: "chapter-delete", chapter }),
                onReorder: reorder,
              }}
            />
            {truncated && (
              <p className="text-muted-foreground text-sm">
                Showing the first {REORDER_LIMIT} of {chapterTotal} chapters. Use search to find the
                others.
              </p>
            )}
          </>
        )}
        <p className="text-muted-foreground text-xs">
          Archived folders and chapters are kept under{" "}
          <Link href="/archived" className="text-primary underline underline-offset-4">
            Archived items
          </Link>
          , where you can restore them.
        </p>
      </section>

      <section
        aria-labelledby="soon-heading"
        className="border-border bg-muted/30 rounded-lg border border-dashed p-4"
      >
        <h2 id="soon-heading" className="flex items-center gap-2 text-base font-semibold">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          AI summaries and progress
          <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs font-medium">
            Coming soon
          </span>
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Summaries of this subject and progress overviews will appear here in a later phase.
          Nothing is calculated or shown yet.
        </p>
      </section>

      {/* ── Dialogs ─────────────────────────────────────────────────────────── */}
      <SubjectDialog
        open={dialog?.kind === "subject-edit"}
        onOpenChange={(o) => !o && close()}
        workspaceId={workspaceId}
        subject={subject}
        onSaved={() => {
          close();
          toast({ title: "Subject updated" });
          reload();
        }}
      />

      <DestructiveDialog
        open={dialog?.kind === "subject-delete"}
        onOpenChange={(o) => !o && close()}
        title={`Delete subject “${subject.name}”?`}
        description={
          <p>
            This permanently deletes the subject and everything in it:{" "}
            <strong>
              {hierarchy.folderCount} {hierarchy.folderCount === 1 ? "folder" : "folders"} and{" "}
              {chapterTotal} {chapterTotal === 1 ? "chapter" : "chapters"}
            </strong>
            . It cannot be undone. To keep it but hide it, archive it instead.
          </p>
        }
        confirmLabel="Delete subject"
        requireText={subject.name}
        onConfirm={async () => {
          await subjectsApi.remove(workspaceId, subject.id);
          toast({ title: `Subject “${subject.name}” deleted` });
          router.push(subjectsHref);
        }}
      />

      <FolderDialog
        open={dialog?.kind === "folder-new" || dialog?.kind === "folder-edit"}
        onOpenChange={(o) => !o && close()}
        workspaceId={workspaceId}
        subjectId={subjectId}
        folder={dialog?.kind === "folder-edit" ? dialog.folder : null}
        parent={dialog?.kind === "folder-new" ? dialog.parent : null}
        onSaved={(f) => {
          const created = dialog?.kind === "folder-new";
          close();
          toast({ title: created ? `Folder “${f.name}” created` : "Folder updated" });
          reload();
        }}
      />

      {dialog?.kind === "folder-move" && (
        <MoveDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Move “${dialog.folder.name}”`}
          description="Folders can be nested up to 3 levels deep. A folder cannot go inside itself or its own subfolders."
          label="New parent folder"
          options={folderMoveOptions(folders, dialog.folder.id)}
          currentId={dialog.folder.parent_folder_id}
          onSubmit={async (target) => {
            await foldersApi.move(workspaceId, subjectId, dialog.folder.id, target);
            toast({ title: `Folder “${dialog.folder.name}” moved` });
            close();
            reload();
          }}
        />
      )}

      {dialog?.kind === "folder-delete" && (
        <DeleteFolderDialog
          open
          onOpenChange={(o) => !o && close()}
          workspaceId={workspaceId}
          subjectId={subjectId}
          folder={dialog.folder}
          counts={cascadeCounts(folders, chapters, dialog.folder.id)}
          onDeleted={() => {
            toast({ title: `Folder “${dialog.folder.name}” deleted` });
            close();
            reload();
          }}
        />
      )}

      <ChapterDialog
        open={dialog?.kind === "chapter-new" || dialog?.kind === "chapter-edit"}
        onOpenChange={(o) => !o && close()}
        workspaceId={workspaceId}
        subjectId={subjectId}
        folders={folders}
        chapter={dialog?.kind === "chapter-edit" ? dialog.chapter : null}
        defaultFolderId={dialog?.kind === "chapter-new" ? dialog.folderId : null}
        onSaved={(c) => {
          const created = dialog?.kind === "chapter-new";
          close();
          toast({ title: created ? `Chapter “${c.title}” created` : "Chapter updated" });
          reload();
        }}
      />

      {dialog?.kind === "chapter-move" && (
        <MoveDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Move “${dialog.chapter.title}”`}
          description="Choose the folder this chapter belongs in."
          label="Folder"
          options={chapterFolderOptions(folders)}
          currentId={dialog.chapter.folder_id}
          onSubmit={async (target) => {
            await chaptersApi.move(workspaceId, subjectId, dialog.chapter.id, target);
            toast({ title: `Chapter “${dialog.chapter.title}” moved` });
            close();
            reload();
          }}
        />
      )}

      {dialog?.kind === "chapter-delete" && (
        <DestructiveDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Delete chapter “${dialog.chapter.title}”?`}
          description={<p>This permanently deletes the chapter. It cannot be undone.</p>}
          confirmLabel="Delete chapter"
          onConfirm={async () => {
            await chaptersApi.remove(workspaceId, subjectId, dialog.chapter.id);
            toast({ title: `Chapter “${dialog.chapter.title}” deleted` });
            close();
            reload();
          }}
        />
      )}
    </div>
  );
}

function SearchResults({
  workspaceId,
  subjectId,
  query,
  loading,
  error,
  result,
  folders,
  onRetry,
}: {
  workspaceId: string;
  subjectId: string;
  query: string;
  loading: boolean;
  error: string | null;
  result: { data: Chapter[]; total: number } | null;
  folders: Folder[];
  onRetry: () => void;
}) {
  if (loading && !result) {
    return (
      <div className="flex min-h-[80px] items-center justify-center" aria-busy="true">
        <LoadingSpinner />
      </div>
    );
  }
  if (error) return <ErrorDisplay title="Search failed" message={error} onRetry={onRetry} />;
  if (!result || result.data.length === 0) {
    return (
      <EmptyState
        title="No chapters match"
        description={`Nothing in this subject has a title containing “${query}”.`}
      />
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-sm" role="status">
        {result.total} {result.total === 1 ? "chapter matches" : "chapters match"} “{query}”
      </p>
      <ul className="space-y-2" aria-label="Search results">
        {result.data.map((c) => (
          <li
            key={c.id}
            className="border-border flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
          >
            <Link
              href={`/workspaces/${workspaceId}/subjects/${subjectId}/chapters/${c.id}`}
              className="focus-visible:ring-ring min-w-0 flex-1 truncate rounded-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
            >
              {c.title}
            </Link>
            <span className="text-muted-foreground truncate text-xs">
              {c.folder_id
                ? folderPath(folders, c.folder_id)
                    .map((f) => f.name)
                    .join(" / ")
                : "No folder"}
            </span>
            <StatusBadge status={c.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
