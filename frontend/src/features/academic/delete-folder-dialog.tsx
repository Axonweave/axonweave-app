"use client";

import { useState } from "react";
import { foldersApi } from "@/lib/api/folders";
import { ApiRequestError } from "@/lib/api/client";
import type { Folder } from "@/types/api";
import { DestructiveDialog } from "./destructive-dialog";

interface DeleteFolderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  subjectId: string;
  folder: Folder;
  /** What a cascade delete would remove, from the loaded hierarchy. */
  counts: { folders: number; chapters: number };
  onDeleted: () => void;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * Two steps (D-12). First a plain delete, which the server refuses with 409 FOLDER_NOT_EMPTY when
 * the folder has contents. Then a strong confirmation (type the folder name) that states exactly
 * what the cascade will delete.
 */
export function DeleteFolderDialog({
  open,
  onOpenChange,
  workspaceId,
  subjectId,
  folder,
  counts,
  onDeleted,
}: DeleteFolderDialogProps) {
  const [cascade, setCascade] = useState(false);

  const close = (next: boolean) => {
    onOpenChange(next);
    if (!next) setCascade(false);
  };

  if (!cascade) {
    return (
      <DestructiveDialog
        key="plain"
        open={open}
        onOpenChange={close}
        title={`Delete folder “${folder.name}”?`}
        description={<p>This permanently deletes the folder. It cannot be undone.</p>}
        confirmLabel="Delete folder"
        onConfirm={async () => {
          try {
            await foldersApi.remove(workspaceId, subjectId, folder.id);
            onDeleted();
          } catch (err) {
            if (err instanceof ApiRequestError && err.code === "FOLDER_NOT_EMPTY") {
              setCascade(true);
              return;
            }
            throw err;
          }
        }}
      />
    );
  }

  // A distinct key gives this stage fresh state; otherwise the "busy" flag of stage one carries over.
  return (
    <DestructiveDialog
      key="cascade"
      open={open}
      onOpenChange={close}
      title={`“${folder.name}” is not empty`}
      description={
        <div className="space-y-2">
          <p>
            Deleting it will also permanently delete{" "}
            <strong>
              {plural(counts.folders, "subfolder", "subfolders")} and{" "}
              {plural(counts.chapters, "chapter", "chapters")}
            </strong>{" "}
            inside it. This cannot be undone.
          </p>
        </div>
      }
      confirmLabel="Delete folder and everything inside"
      requireText={folder.name}
      onConfirm={async () => {
        await foldersApi.remove(workspaceId, subjectId, folder.id, true);
        onDeleted();
      }}
    />
  );
}
