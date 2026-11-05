"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { foldersApi } from "@/lib/api/folders";
import type { Folder } from "@/types/api";
import { FormError, TEXTAREA_CLASS, errorMessage } from "./form-bits";

interface FolderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  subjectId: string;
  /** Present = rename/edit, absent = create. */
  folder?: Folder | null;
  /** For create: the parent folder, or null for the top level. */
  parent?: Folder | null;
  onSaved: (folder: Folder) => void;
}

function Form({
  onOpenChange,
  workspaceId,
  subjectId,
  folder,
  parent,
  onSaved,
}: Omit<FolderDialogProps, "open">) {
  const editing = !!folder;
  const [name, setName] = useState(folder?.name ?? "");
  const [description, setDescription] = useState(folder?.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = editing
        ? await foldersApi.update(workspaceId, subjectId, folder.id, {
            name: name.trim(),
            description: description.trim(),
          })
        : await foldersApi.create(workspaceId, subjectId, {
            name: name.trim(),
            description: description.trim() || null,
            parent_folder_id: parent?.id ?? null,
          });
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <DialogContent showCloseButton={false}>
      <form onSubmit={submit} className="space-y-4">
        <DialogHeader>
          <DialogTitle>
            {editing ? "Edit folder" : parent ? "New subfolder" : "New folder"}
          </DialogTitle>
          {!editing && (
            <DialogDescription>
              {parent ? `Inside “${parent.name}”.` : "At the top level of this subject."}
            </DialogDescription>
          )}
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="folder-name">Name *</Label>
          <Input
            id="folder-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            required
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="folder-description">Description</Label>
          <textarea
            id="folder-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={2000}
            className={TEXTAREA_CLASS}
          />
        </div>
        <FormError message={error} />
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create folder"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

export function FolderDialog({ open, onOpenChange, ...rest }: FolderDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Form onOpenChange={onOpenChange} {...rest} />
    </Dialog>
  );
}
