"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FileText, RotateCw, Trash2 } from "lucide-react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { formatDate } from "@/lib/activity";
import { ApiRequestError } from "@/lib/api/client";
import { documentsApi, type DocumentRecord } from "@/lib/api/documents";
import { StatusBadge, formatBytes } from "./status-badge";
import { UploadZone } from "./upload-zone";
import { useStatusPolling } from "./use-status-polling";

const PAGE_SIZE = 25;

export function deleteWarning(doc: DocumentRecord): string {
  return `This permanently deletes "${doc.display_name}", its stored file and its search index. Answers that cited it keep only its name and page. This cannot be undone.`;
}

export function Library() {
  const { toast } = useToast();
  const params = useSearchParams();
  // Set by "Upload documents" on subject and chapter pages.
  const placement = {
    workspace_id: params.get("workspace") ?? undefined,
    subject_id: params.get("subject") ?? undefined,
    chapter_id: params.get("chapter") ?? undefined,
  };
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentRecord | null>(null);

  const { data, loading, error, reload } = useAsync(
    () =>
      documentsApi.list({
        q: q.trim() || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [offset, q, status],
  );
  const docs = data?.data ?? [];
  useStatusPolling(
    docs.map((d) => d.processing_status),
    reload,
  );

  async function run(doc: DocumentRecord, action: () => Promise<unknown>, done: string) {
    setBusyId(doc.id);
    try {
      await action();
      toast({ title: done });
      reload();
    } catch (err) {
      toast({
        title: "Action failed",
        description: err instanceof ApiRequestError ? err.message : "Something went wrong.",
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <UploadZone onUploaded={reload} defaultPlacement={placement} />
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          aria-label="Search documents by name"
          placeholder="Search by name"
          className="border-input bg-background h-9 flex-1 rounded-md border px-3 text-sm"
          value={q}
          onChange={(e) => {
            setOffset(0);
            setQ(e.target.value);
          }}
        />
        <select
          aria-label="Filter by status"
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
        >
          <option value="">All statuses</option>
          <option value="completed">Ready</option>
          <option value="failed">Failed</option>
          <option value="queued">Waiting</option>
        </select>
      </div>
      <AsyncSection
        title="Documents"
        loading={loading && !data}
        error={error}
        onRetry={reload}
        isEmpty={docs.length === 0}
        empty={
          <EmptyState
            title="No documents yet"
            description="Upload your notes, slides or papers. Once processed you can ask the AI Tutor questions about them."
            icon={<FileText className="h-8 w-8" aria-hidden="true" />}
          />
        }
      >
        <ul className="divide-border border-border divide-y rounded-lg border">
          {docs.map((doc) => {
            const failure =
              doc.processing_status === "failed" ? "Processing failed. You can try again." : null;
            return (
              <li
                key={doc.id}
                className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="font-medium break-words">
                    <Link href={`/documents/${doc.id}`} className="hover:underline">
                      {doc.display_name}
                    </Link>
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {doc.file_type.toUpperCase()} · {formatBytes(doc.file_size)} · Uploaded{" "}
                    {formatDate(doc.created_at)}
                  </p>
                  {failure && <p className="text-destructive text-xs">{failure}</p>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={doc.processing_status} />
                  {doc.processing_status === "failed" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busyId === doc.id}
                      onClick={() => run(doc, () => documentsApi.retry(doc.id), "Retrying")}
                      aria-label={`Retry processing ${doc.display_name}`}
                    >
                      <RotateCw className="mr-1 h-4 w-4" aria-hidden="true" />
                      Retry
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive"
                    disabled={busyId === doc.id}
                    onClick={() => setDeleteTarget(doc)}
                    aria-label={`Delete ${doc.display_name}`}
                  >
                    <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
                    Delete
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </AsyncSection>
      {!loading && !error && (
        <Pager offset={offset} limit={PAGE_SIZE} total={data?.total ?? 0} onChange={setOffset} />
      )}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete document?"
        description={deleteTarget ? deleteWarning(deleteTarget) : ""}
        confirmLabel="Delete permanently"
        destructive
        onConfirm={() => {
          const doc = deleteTarget;
          setDeleteTarget(null);
          if (doc)
            void run(doc, () => documentsApi.remove(doc.id), `"${doc.display_name}" deleted`);
        }}
      />
    </div>
  );
}
