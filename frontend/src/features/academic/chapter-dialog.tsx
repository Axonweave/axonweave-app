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
import { chaptersApi } from "@/lib/api/chapters";
import type { Chapter, ChapterStatus, Folder } from "@/types/api";
import { FormError, SELECT_CLASS, TEXTAREA_CLASS, errorMessage, indented } from "./form-bits";
import { STATUS_OPTIONS } from "./status";
import { chapterFolderOptions } from "./tree";

interface ChapterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  subjectId: string;
  folders: Folder[];
  /** Present = edit, absent = create. */
  chapter?: Chapter | null;
  /** For create: preselected folder. */
  defaultFolderId?: string | null;
  onSaved: (chapter: Chapter) => void;
}

const NONE = "__none__";

function Form({
  onOpenChange,
  workspaceId,
  subjectId,
  folders,
  chapter,
  defaultFolderId,
  onSaved,
}: Omit<ChapterDialogProps, "open">) {
  const editing = !!chapter;
  const [title, setTitle] = useState(chapter?.title ?? "");
  const [description, setDescription] = useState(chapter?.description ?? "");
  const [folderId, setFolderId] = useState(chapter?.folder_id ?? defaultFolderId ?? NONE);
  const [status, setStatus] = useState<ChapterStatus>(
    (chapter?.status as ChapterStatus | undefined) ?? "not_started",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const folder = folderId === NONE ? null : folderId;
    try {
      const saved = editing
        ? await chaptersApi.update(workspaceId, subjectId, chapter.id, {
            title: title.trim(),
            description: description.trim(),
            status,
            ...(folder !== chapter.folder_id ? { folder_id: folder, folder_id_set: true } : {}),
          })
        : await chaptersApi.create(workspaceId, subjectId, {
            title: title.trim(),
            description: description.trim() || null,
            folder_id: folder,
            status,
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
          <DialogTitle>{editing ? "Edit chapter" : "New chapter"}</DialogTitle>
          <DialogDescription>
            Status is just a label you set to organise your work.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="chapter-title">Title *</Label>
          <Input
            id="chapter-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={500}
            required
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="chapter-description">Description</Label>
          <textarea
            id="chapter-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={5000}
            className={TEXTAREA_CLASS}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="chapter-folder">Folder</Label>
          <select
            id="chapter-folder"
            value={folderId}
            onChange={(e) => setFolderId(e.target.value)}
            className={SELECT_CLASS}
          >
            {chapterFolderOptions(folders).map((o) => (
              <option key={o.id ?? NONE} value={o.id ?? NONE}>
                {indented(o.label, o.depth)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="chapter-status">Status</Label>
          <select
            id="chapter-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as ChapterStatus)}
            className={SELECT_CLASS}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
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
          <Button type="submit" disabled={busy || !title.trim()}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create chapter"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

export function ChapterDialog({ open, onOpenChange, ...rest }: ChapterDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mounted only while open so every opening starts with fresh state. */}
      {open && <Form onOpenChange={onOpenChange} {...rest} />}
    </Dialog>
  );
}
