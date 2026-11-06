"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { subjectsApi } from "@/lib/api/subjects";
import { ColourPicker, PRESET_COLOURS } from "@/features/workspaces/workspace-form";
import type { Subject } from "@/types/api";
import { FormError, TEXTAREA_CLASS, errorMessage } from "./form-bits";

interface SubjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  /** Present = edit, absent = create. */
  subject?: Subject | null;
  onSaved: (subject: Subject) => void;
}

function Form({ onOpenChange, workspaceId, subject, onSaved }: Omit<SubjectDialogProps, "open">) {
  const editing = !!subject;
  const [name, setName] = useState(subject?.name ?? "");
  const [description, setDescription] = useState(subject?.description ?? "");
  const [colour, setColour] = useState(subject?.colour ?? PRESET_COLOURS[0]);
  const [icon, setIcon] = useState(subject?.icon ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = editing
        ? await subjectsApi.update(workspaceId, subject.id, {
            name: name.trim(),
            description: description.trim(),
            colour,
            icon: icon.trim(),
          })
        : await subjectsApi.create(workspaceId, {
            name: name.trim(),
            description: description.trim() || null,
            colour,
            icon: icon.trim() || null,
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
          <DialogTitle>{editing ? "Edit subject" : "New subject"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="subject-name">Name *</Label>
          <Input
            id="subject-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            required
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="subject-description">Description</Label>
          <textarea
            id="subject-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={2000}
            className={TEXTAREA_CLASS}
          />
        </div>
        <div className="space-y-2">
          <Label>Colour</Label>
          <ColourPicker value={colour} onChange={setColour} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="subject-icon">Icon (optional)</Label>
          <Input
            id="subject-icon"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
            maxLength={64}
            placeholder="An emoji or a short label"
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
            {busy ? "Saving…" : editing ? "Save changes" : "Create subject"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

export function SubjectDialog({ open, onOpenChange, ...rest }: SubjectDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mounted only while open so every opening starts with fresh state. */}
      {open && <Form onOpenChange={onOpenChange} {...rest} />}
    </Dialog>
  );
}
