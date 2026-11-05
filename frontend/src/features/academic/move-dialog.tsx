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
import { Label } from "@/components/ui/label";
import type { FolderOption } from "./tree";
import { FormError, SELECT_CLASS, errorMessage, indented } from "./form-bits";

interface MoveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Label of the select, e.g. "New parent folder". */
  label: string;
  options: FolderOption[];
  /** id of where the item is now (null = top level / no folder). */
  currentId: string | null;
  /** Rejecting shows the server message (depth, name clash, ...) and keeps the dialog open. */
  onSubmit: (targetId: string | null) => Promise<void>;
}

const NONE = "__none__";

function Body({
  onOpenChange,
  title,
  description,
  label,
  options,
  currentId,
  onSubmit,
}: Omit<MoveDialogProps, "open">) {
  const [value, setValue] = useState(currentId ?? NONE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(value === NONE ? null : value);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <DialogContent showCloseButton={false}>
      <form onSubmit={submit} className="space-y-4">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="move-target">{label}</Label>
          <select
            id="move-target"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className={SELECT_CLASS}
          >
            {options.map((o) => (
              <option key={o.id ?? NONE} value={o.id ?? NONE} disabled={o.disabled}>
                {indented(o.label, o.depth)}
                {o.reason ? ` (${o.reason})` : ""}
              </option>
            ))}
          </select>
        </div>
        <FormError message={error} />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || value === (currentId ?? NONE)}>
            {busy ? "Moving…" : "Move"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

export function MoveDialog({ open, onOpenChange, ...rest }: MoveDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Body onOpenChange={onOpenChange} {...rest} />
    </Dialog>
  );
}
