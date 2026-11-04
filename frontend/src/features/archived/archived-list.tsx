"use client";

import { useState } from "react";
import { ArchiveRestore, Trash2 } from "lucide-react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { formatDate } from "@/lib/activity";
import { ApiRequestError } from "@/lib/api/client";
import { archivedApi } from "@/lib/api/archived";
import { dashboardApi } from "@/lib/api/dashboard";
import type { ArchivedItem } from "@/types/api";

const PAGE_SIZE = 20;

const TYPE_LABEL: Record<ArchivedItem["type"], string> = {
  workspace: "Workspace",
  subject: "Subject",
  folder: "Folder",
  chapter: "Chapter",
};

/** What the confirmation dialog tells the user will be deleted (D-12). */
export function deleteWarning(item: ArchivedItem): string {
  switch (item.type) {
    case "workspace":
      return `This permanently deletes the workspace "${item.name}" and every subject, folder and chapter in it. This cannot be undone.`;
    case "subject":
      return `This permanently deletes the subject "${item.name}" and every folder and chapter in it. This cannot be undone.`;
    case "folder":
      return `This permanently deletes the folder "${item.name}" and everything inside it, including sub-folders and chapters. This cannot be undone.`;
    case "chapter":
      return `This permanently deletes the chapter "${item.name}". This cannot be undone.`;
  }
}

function parentLabel(item: ArchivedItem): string {
  if (item.type === "workspace") return "";
  if (item.type === "subject") return `in ${item.workspace_name}`;
  return `in ${item.subject_name ?? "a subject"} · ${item.workspace_name}`;
}

export function ArchivedList() {
  const { toast } = useToast();
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ArchivedItem | null>(null);
  const { data, loading, error, reload } = useAsync(
    () => dashboardApi.archived(PAGE_SIZE, offset),
    [offset],
  );
  const items = data?.data ?? [];
  const total = data?.total ?? 0;

  function afterChange() {
    // Stepping back a page when the last item on it was removed avoids landing on an empty page.
    if (offset > 0 && items.length === 1) setOffset(Math.max(0, offset - PAGE_SIZE));
    else reload();
  }

  function errorMessage(err: unknown, fallback: string): string {
    return err instanceof ApiRequestError ? err.message : fallback;
  }

  async function handleRestore(item: ArchivedItem) {
    setBusyId(item.id);
    try {
      await archivedApi.restore(item);
      toast({ title: `${TYPE_LABEL[item.type]} "${item.name}" restored` });
      afterChange();
    } catch (err) {
      toast({
        title: "Could not restore",
        description: errorMessage(err, "Something went wrong."),
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete() {
    const item = deleteTarget;
    if (!item) return;
    setDeleteTarget(null);
    setBusyId(item.id);
    try {
      await archivedApi.remove(item);
      toast({ title: `${TYPE_LABEL[item.type]} "${item.name}" deleted` });
      afterChange();
    } catch (err) {
      toast({
        title: "Could not delete",
        description: errorMessage(err, "Something went wrong."),
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <AsyncSection
        title="Archived"
        loading={loading}
        error={error}
        onRetry={reload}
        isEmpty={items.length === 0}
        empty={
          <EmptyState
            title="Nothing archived"
            description="Items you archive show up here, where you can restore or permanently delete them."
          />
        }
      >
        <ul className="divide-border border-border divide-y rounded-lg border">
          {items.map((item) => (
            <li
              key={`${item.type}-${item.id}`}
              className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <p className="font-medium break-words">
                  <span className="bg-muted text-muted-foreground mr-2 rounded-full px-2 py-0.5 text-xs font-normal">
                    {TYPE_LABEL[item.type]}
                  </span>
                  {item.name}
                </p>
                <p className="text-muted-foreground text-xs">
                  {parentLabel(item)} {parentLabel(item) && "· "}Archived{" "}
                  {formatDate(item.archived_at)}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === item.id}
                  onClick={() => handleRestore(item)}
                  aria-label={`Restore ${TYPE_LABEL[item.type].toLowerCase()} ${item.name}`}
                >
                  <ArchiveRestore className="mr-1 h-4 w-4" aria-hidden="true" />
                  Restore
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive"
                  disabled={busyId === item.id}
                  onClick={() => setDeleteTarget(item)}
                  aria-label={`Delete ${TYPE_LABEL[item.type].toLowerCase()} ${item.name}`}
                >
                  <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </AsyncSection>
      {!loading && !error && (
        <Pager offset={offset} limit={PAGE_SIZE} total={total} onChange={setOffset} />
      )}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={deleteTarget ? `Delete ${TYPE_LABEL[deleteTarget.type].toLowerCase()}?` : "Delete?"}
        description={deleteTarget ? deleteWarning(deleteTarget) : ""}
        confirmLabel="Delete permanently"
        onConfirm={handleDelete}
        destructive
      />
    </div>
  );
}
