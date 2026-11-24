"use client";

/**
 * What is inside a folder: its sub-folders, its documents, and the two things you do here —
 * add a sub-folder or upload documents. The study room (chat, revision, materials) is one button
 * away and works on everything inside this folder. Management (rename, move, archive, delete)
 * stays in the full organiser behind "Manage".
 */
import { useRef, useState } from "react";
import Link from "next/link";
import { FileText, Folder as FolderIcon, FolderPlus, Settings2, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { formatDate } from "@/lib/activity";
import { ApiRequestError } from "@/lib/api/client";
import { documentsApi } from "@/lib/api/documents";
import { environmentHref, makeContext } from "@/lib/learning-context";
import { cn } from "@/lib/utils";
import { FolderDialog } from "@/features/academic/folder-dialog";
import { ACCEPT, MAX_FILES } from "@/features/documents/upload-zone";
import { StatusBadge, formatBytes } from "@/features/documents/status-badge";
import { useStatusPolling } from "@/features/documents/use-status-polling";
import { useLearningSpace } from "./space-provider";

const PAGE = 100;

export function FolderContents() {
  const space = useLearningSpace();
  const { workspace, subject, folder, folders, chapters, reload } = space;
  const { toast } = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [creating, setCreating] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  const parentId = folder?.id ?? null;
  const subFolders = folders.filter((f) => (f.parent_folder_id ?? null) === parentId);
  const looseChapters = chapters.filter((c) => (c.folder_id ?? null) === parentId);
  const folderName = (id: string | null) => folders.find((f) => f.id === id)?.name ?? null;

  const docs = useAsync(
    () =>
      documentsApi.list({
        workspace_id: workspace.id,
        ...(folder ? { folder_id: folder.id } : { subject_id: subject.id }),
        limit: PAGE,
      }),
    [workspace.id, subject.id, folder?.id],
  );
  const list = docs.data?.data ?? [];
  useStatusPolling(
    list.map((d) => d.processing_status),
    docs.reload,
  );

  const hrefFor = (ids: { folderId?: string; chapterId?: string }) =>
    environmentHref(makeContext({ workspaceId: workspace.id, subjectId: subject.id, ...ids }));

  async function upload(files: File[]) {
    if (files.length === 0) return;
    if (files.length > MAX_FILES) {
      toast({ title: `Upload up to ${MAX_FILES} files at a time`, variant: "destructive" });
      return;
    }
    setUploading(true);
    try {
      const result = await documentsApi.upload(files, {
        workspace_id: workspace.id,
        subject_id: subject.id,
        folder_id: folder?.id ?? null,
      });
      if (result.documents.length > 0) {
        toast({
          title: `${result.documents.length} file${result.documents.length === 1 ? "" : "s"} uploaded`,
          description: "Processing has started. Status updates here automatically.",
        });
        docs.reload();
      }
      for (const rejected of result.rejected) {
        toast({
          title: `${rejected.filename} was not uploaded`,
          description: rejected.message,
          variant: "destructive",
        });
      }
    } catch (err) {
      toast({
        title: "Upload failed",
        description: err instanceof ApiRequestError ? err.message : "Something went wrong.",
        variant: "destructive",
      });
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => setCreating(true)}>
          <FolderPlus aria-hidden="true" />
          New folder
        </Button>
        <Button disabled={uploading} onClick={() => input.current?.click()}>
          <UploadCloud aria-hidden="true" />
          {uploading ? "Uploading…" : "Upload documents"}
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          aria-label="Choose documents to upload"
          onChange={(e) => void upload(Array.from(e.target.files ?? []))}
        />
        <Link
          href={environmentHref(space.ctx, "content")}
          className="text-muted-foreground hover:text-foreground ml-auto inline-flex items-center gap-1.5 text-sm"
        >
          <Settings2 className="h-4 w-4" aria-hidden="true" />
          Manage (rename, move, archive)
        </Link>
      </div>

      <section aria-labelledby="folders-heading" className="space-y-3">
        <h2 id="folders-heading" className="text-base font-semibold">
          Folders
        </h2>
        {subFolders.length === 0 && looseChapters.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No folders inside yet. Add one for each chapter or topic, or upload documents straight
            into this folder.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {subFolders.map((f) => (
              <li key={f.id}>
                <Link
                  href={hrefFor({ folderId: f.id })}
                  className="bg-card hover:bg-muted/40 focus-visible:ring-ring flex items-center gap-3 rounded-lg border p-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  <FolderIcon
                    className="text-muted-foreground h-5 w-5 shrink-0"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{f.name}</span>
                    {f.description ? (
                      <span className="text-muted-foreground block truncate text-xs">
                        {f.description}
                      </span>
                    ) : null}
                  </span>
                </Link>
              </li>
            ))}
            {looseChapters.map((c) => (
              <li key={c.id}>
                <Link
                  href={hrefFor({ chapterId: c.id })}
                  className="bg-card hover:bg-muted/40 focus-visible:ring-ring flex items-center gap-3 rounded-lg border p-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  <FileText className="text-muted-foreground h-5 w-5 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{c.title}</span>
                    <span className="text-muted-foreground block text-xs">Chapter</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section
        aria-labelledby="documents-heading"
        className="space-y-3"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void upload(Array.from(e.dataTransfer.files));
        }}
      >
        <h2 id="documents-heading" className="text-base font-semibold">
          Documents
          {docs.data ? (
            <span className="text-muted-foreground ml-2 text-sm font-normal">
              {docs.data.total}
            </span>
          ) : null}
        </h2>
        {docs.loading && !docs.data ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : docs.error ? (
          <ErrorDisplay message={docs.error} onRetry={docs.reload} />
        ) : list.length === 0 ? (
          <div
            className={cn(
              "rounded-lg border-2 border-dashed",
              dragging ? "border-primary bg-muted" : "border-border",
            )}
          >
            <EmptyState
              title="No documents yet"
              description="Drop files here or use Upload documents. PDF, PowerPoint, Word, text, Markdown, PNG or JPEG."
              icon={<UploadCloud className="h-8 w-8" aria-hidden="true" />}
            />
          </div>
        ) : (
          <ul
            className={cn(
              "divide-border border-border divide-y rounded-lg border",
              dragging && "border-primary bg-muted/40",
            )}
          >
            {list.map((d) => (
              <li
                key={d.id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <Link
                    href={`/documents/${d.id}`}
                    className="font-medium break-words hover:underline"
                  >
                    {d.display_name}
                  </Link>
                  <p className="text-muted-foreground text-xs">
                    {d.file_type.toUpperCase()} · {formatBytes(d.file_size)} ·{" "}
                    {formatDate(d.created_at)}
                    {!folder && folderName(d.folder_id ?? null)
                      ? ` · in ${folderName(d.folder_id ?? null)}`
                      : ""}
                  </p>
                </div>
                <StatusBadge status={d.processing_status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {creating ? (
        <FolderDialog
          open={creating}
          onOpenChange={setCreating}
          workspaceId={workspace.id}
          subjectId={subject.id}
          parent={folder}
          onSaved={() => {
            setCreating(false);
            reload();
          }}
        />
      ) : null}
    </div>
  );
}
