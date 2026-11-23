"use client";

/** Content tab of a chapter environment: the former chapter page body with all its actions. */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Archive, FolderInput, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { chaptersApi } from "@/lib/api/chapters";
import { environmentHref, makeContext } from "@/lib/learning-context";
import { formatDateTime } from "@/lib/activity";
import { ChapterDialog } from "@/features/academic/chapter-dialog";
import { DestructiveDialog } from "@/features/academic/destructive-dialog";
import { MoveDialog } from "@/features/academic/move-dialog";
import { StatusBadge } from "@/features/academic/status";
import { chapterFolderOptions } from "@/features/academic/tree";
import { ScopedMaterials } from "./scoped-materials";
import { useLearningSpace } from "./space-provider";

const COMING_SOON_TABS = ["AI explanations", "Notes"];

type Dialog = "edit" | "move" | "delete" | null;

export function ChapterContent() {
  const { workspace, subject, folders, chapter, path, reload } = useLearningSpace();
  const router = useRouter();
  const { toast } = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  if (!chapter) return null;

  const workspaceId = workspace.id;
  const subjectId = subject.id;
  const subjectHref = environmentHref(makeContext({ workspaceId, subjectId }), "content");
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
    <div className="space-y-6">
      <section aria-labelledby="chapter-details" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="chapter-details" className="text-lg font-semibold">
            Chapter details
          </h2>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setDialog("edit")}>
              <Pencil className="mr-1 h-4 w-4" aria-hidden="true" />
              Edit
            </Button>
            <Button variant="outline" onClick={() => setDialog("move")}>
              <FolderInput className="mr-1 h-4 w-4" aria-hidden="true" />
              Move
            </Button>
            <Button variant="outline" onClick={archive}>
              <Archive className="mr-1 h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
            <Button variant="destructive" onClick={() => setDialog("delete")}>
              <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
              Delete
            </Button>
          </div>
        </div>

        {chapter.description ? (
          <p className="text-muted-foreground text-sm break-words whitespace-pre-wrap">
            {chapter.description}
          </p>
        ) : (
          <p className="text-muted-foreground text-sm">No description.</p>
        )}

        <dl className="border-border grid gap-4 rounded-xl border p-4 sm:grid-cols-2 lg:grid-cols-4">
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
            <dd className="mt-1 text-sm">{formatDateTime(chapter.created_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">Last updated</dt>
            <dd className="mt-1 text-sm">{formatDateTime(chapter.updated_at)}</dd>
          </div>
        </dl>
        <p className="text-muted-foreground text-xs">
          Chapter status is only a label for organising your work, not a measure of understanding.
        </p>
      </section>

      <section aria-labelledby="chapter-materials" className="space-y-3">
        <h2 id="chapter-materials" className="text-lg font-semibold">
          Learning materials
        </h2>
        <ScopedMaterials />
      </section>

      <section aria-labelledby="tabs-heading" className="space-y-2">
        <h2 id="tabs-heading" className="text-base font-semibold">
          More study tools{" "}
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
          reload();
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
            reload();
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
