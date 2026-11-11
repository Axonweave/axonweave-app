"use client";

import { GenerateButton } from "@/features/study/generate-button";
import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Archive, FolderInput, Pencil, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { chaptersApi } from "@/lib/api/chapters";
import { foldersApi } from "@/lib/api/folders";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { ChapterDialog } from "@/features/academic/chapter-dialog";
import { DestructiveDialog } from "@/features/academic/destructive-dialog";
import { MoveDialog } from "@/features/academic/move-dialog";
import { PageBreadcrumbs } from "@/features/academic/page-breadcrumbs";
import { StatusBadge } from "@/features/academic/status";
import { chapterFolderOptions, folderPath } from "@/features/academic/tree";
import type { Chapter, Folder, Subject, Workspace } from "@/types/api";

type Loaded =
  | { notFound: true }
  | {
      notFound: false;
      workspace: Workspace;
      subject: Subject;
      folders: Folder[];
      chapter: Chapter;
    };

const COMING_SOON_TABS = [
  "Learning materials",
  "AI explanations",
  "Flashcards",
  "Quizzes",
  "Notes",
  "Revision history",
];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

type Dialog = "edit" | "move" | "delete" | null;

export default function ChapterDetailPage() {
  const { workspaceId, subjectId, chapterId } = useParams<{
    workspaceId: string;
    subjectId: string;
    chapterId: string;
  }>();
  const router = useRouter();
  const { toast } = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);

  const state = useAsync<Loaded>(async () => {
    try {
      const [workspace, subject, folders, chapter] = await Promise.all([
        workspacesApi.get(workspaceId).then((r) => r.data),
        subjectsApi.get(workspaceId, subjectId),
        foldersApi.listAll(workspaceId, subjectId),
        chaptersApi.get(workspaceId, subjectId, chapterId),
      ]);
      return { notFound: false, workspace, subject, folders, chapter };
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) return { notFound: true };
      throw err;
    }
  }, [workspaceId, subjectId, chapterId]);

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
        title="Chapter not found"
        description="It may have been deleted, or it is not in your account."
        action={
          <Link href="/subjects" className="text-primary underline underline-offset-4">
            Back to subjects
          </Link>
        }
      />
    );
  }

  const { workspace, subject, folders, chapter } = data;
  const subjectHref = `/workspaces/${workspaceId}/subjects/${subjectId}`;
  const path = folderPath(folders, chapter.folder_id);
  const close = () => setDialog(null);

  const archive = async () => {
    try {
      await chaptersApi.archive(workspaceId, subjectId, chapter.id);
      toast({ title: `Chapter “${chapter.title}” archived` });
      router.push(subjectHref);
    } catch (err) {
      toast({
        title: "Could not archive chapter",
        description: err instanceof ApiRequestError ? err.message : undefined,
        variant: "destructive",
      });
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageBreadcrumbs
        crumbs={[
          { label: workspace.name, href: `/subjects?workspace=${workspace.id}` },
          { label: subject.name, href: subjectHref },
          ...path.map((f) => ({ label: f.name, href: subjectHref })),
          { label: chapter.title },
        ]}
      />

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold break-words">{chapter.title}</h1>
          {chapter.description ? (
            <p className="text-muted-foreground mt-1 text-sm break-words whitespace-pre-wrap">
              {chapter.description}
            </p>
          ) : (
            <p className="text-muted-foreground mt-1 text-sm">No description.</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/library?workspace=${workspaceId}&subject=${subjectId}&chapter=${chapterId}`}
            className={buttonVariants({ variant: "outline" })}
          >
            Upload documents
          </Link>
          <GenerateButton preset={{ type: "chapter", id: chapterId, label: chapter.title }} />
          <Button variant="outline" onClick={() => setDialog("edit")}>
            <Pencil className="mr-2 h-4 w-4" aria-hidden="true" />
            Edit
          </Button>
          <Button variant="outline" onClick={() => setDialog("move")}>
            <FolderInput className="mr-2 h-4 w-4" aria-hidden="true" />
            Move
          </Button>
          <Button variant="outline" onClick={archive}>
            <Archive className="mr-2 h-4 w-4" aria-hidden="true" />
            Archive
          </Button>
          <Button variant="destructive" onClick={() => setDialog("delete")}>
            <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
            Delete
          </Button>
        </div>
      </header>

      <dl className="border-border grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground text-xs">Status</dt>
          <dd className="mt-1">
            <StatusBadge status={chapter.status} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Folder</dt>
          <dd className="mt-1 text-sm break-words">
            {path.length > 0 ? path.map((f) => f.name).join(" / ") : "Not in a folder"}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Created</dt>
          <dd className="mt-1 text-sm">{formatDate(chapter.created_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Last updated</dt>
          <dd className="mt-1 text-sm">{formatDate(chapter.updated_at)}</dd>
        </div>
      </dl>

      <section aria-labelledby="tabs-heading" className="space-y-2">
        <h2 id="tabs-heading" className="text-lg font-semibold">
          Study tools{" "}
          <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs font-medium">
            Coming soon
          </span>
        </h2>
        <div
          role="tablist"
          aria-label="Study tools, not available yet"
          className="flex flex-wrap gap-2"
        >
          {COMING_SOON_TABS.map((label) => (
            <button
              key={label}
              type="button"
              role="tab"
              aria-selected="false"
              disabled
              className="border-border text-muted-foreground cursor-not-allowed rounded-md border px-3 py-1.5 text-sm opacity-60"
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-muted-foreground text-sm">
          These arrive in later phases. Chapter status is only a label for organising your work.
        </p>
      </section>

      <ChapterDialog
        open={dialog === "edit"}
        onOpenChange={(o) => !o && close()}
        workspaceId={workspaceId}
        subjectId={subjectId}
        folders={folders}
        chapter={chapter}
        onSaved={() => {
          close();
          toast({ title: "Chapter updated" });
          state.reload();
        }}
      />

      {dialog === "move" && (
        <MoveDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Move “${chapter.title}”`}
          description="Choose the folder this chapter belongs in."
          label="Folder"
          options={chapterFolderOptions(folders)}
          currentId={chapter.folder_id}
          onSubmit={async (target) => {
            await chaptersApi.move(workspaceId, subjectId, chapter.id, target);
            toast({ title: `Chapter “${chapter.title}” moved` });
            close();
            state.reload();
          }}
        />
      )}

      {dialog === "delete" && (
        <DestructiveDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Delete chapter “${chapter.title}”?`}
          description={<p>This permanently deletes the chapter. It cannot be undone.</p>}
          confirmLabel="Delete chapter"
          onConfirm={async () => {
            await chaptersApi.remove(workspaceId, subjectId, chapter.id);
            toast({ title: `Chapter “${chapter.title}” deleted` });
            router.push(subjectHref);
          }}
        />
      )}
    </div>
  );
}
