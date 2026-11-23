"use client";

/** The room's files: drop new ones in, see processing status, open any of them. */
import Link from "next/link";
import { ExternalLink, FileText, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { documentsApi } from "@/lib/api/documents";
import { StatusBadge } from "@/features/documents/status-badge";
import { UploadZone } from "@/features/documents/upload-zone";
import { useLearningSpace } from "@/features/learning-spaces/space-provider";

const LIMIT = 50;

export function FilesPanel() {
  const { ctx, subject, chapters } = useLearningSpace();
  const docs = useAsync(
    () =>
      documentsApi.list({ workspace_id: ctx.workspaceId, subject_id: subject.id, limit: LIMIT }),
    [ctx.workspaceId, subject.id],
  );
  const chapterTitle = (id: string | null) =>
    id ? (chapters.find((c) => c.id === id)?.title ?? null) : null;
  const list = docs.data?.data ?? [];

  return (
    <div className="space-y-5">
      <UploadZone
        onUploaded={docs.reload}
        defaultPlacement={{ workspace_id: ctx.workspaceId, subject_id: subject.id }}
      />

      <section aria-labelledby="room-files">
        <div className="mb-2 flex items-center justify-between">
          <h3 id="room-files" className="text-sm font-semibold">
            In this room{docs.data ? ` (${docs.data.total})` : ""}
          </h3>
          <Button variant="ghost" size="sm" onClick={docs.reload} disabled={docs.loading}>
            <RefreshCw className={docs.loading ? "animate-spin" : ""} aria-hidden="true" />
            Refresh
          </Button>
        </div>
        {docs.error ? (
          <p className="text-muted-foreground text-sm">Could not load the files.</p>
        ) : !docs.data ? (
          <ul className="space-y-2" aria-label="Loading files">
            {[0, 1, 2].map((i) => (
              <li key={i} className="bg-muted h-14 animate-pulse rounded-xl" />
            ))}
          </ul>
        ) : list.length === 0 ? (
          <p className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
            No files yet. Drop PDFs, slides or notes above and the AI Tutor will answer from them.
          </p>
        ) : (
          <ul className="space-y-2">
            {list.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/documents/${d.id}`}
                  className="group bg-card hover:border-primary/30 focus-visible:ring-ring hover:border-foreground/20 flex items-center gap-3 rounded-xl border p-3 transition-all focus-visible:ring-2 focus-visible:outline-none"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-500/10">
                    <FileText
                      className="h-4 w-4 text-blue-600 dark:text-blue-300"
                      aria-hidden="true"
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{d.display_name}</span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {d.file_type.toUpperCase()}
                      {chapterTitle(d.chapter_id) ? ` · ${chapterTitle(d.chapter_id)}` : ""}
                    </span>
                  </span>
                  <StatusBadge status={d.processing_status} />
                  <ExternalLink
                    className="text-muted-foreground h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {docs.data && docs.data.total > list.length ? (
          <p className="text-muted-foreground mt-3 text-xs">
            Showing the latest {list.length}.{" "}
            <Link
              href={`/library?workspace=${ctx.workspaceId}&subject=${subject.id}`}
              className="text-primary hover:underline"
            >
              See all in the Library
            </Link>
          </p>
        ) : null}
      </section>
    </div>
  );
}
