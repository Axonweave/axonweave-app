"use client";

import { useState, type ReactNode } from "react";
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
import { FormError, errorMessage } from "./form-bits";

interface DestructiveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Say exactly what will be deleted. */
  description: ReactNode;
  confirmLabel: string;
  /** When set, the person must type this exact text before the button enables. */
  requireText?: string;
  /** Rejecting shows the server message in the dialog and keeps it open. */
  onConfirm: () => Promise<void>;
}

function Body({
  onOpenChange,
  title,
  description,
  confirmLabel,
  requireText,
  onConfirm,
}: Omit<DestructiveDialogProps, "open">) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = !requireText || typed === requireText;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <DialogContent showCloseButton={false}>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription render={<div />}>{description}</DialogDescription>
      </DialogHeader>
      {requireText && (
        <div className="space-y-2">
          <Label htmlFor="confirm-text">Type &quot;{requireText}&quot; to confirm</Label>
          <Input
            id="confirm-text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
          />
        </div>
      )}
      <FormError message={error} />
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
          Cancel
        </Button>
        <Button variant="destructive" onClick={run} disabled={!ready || busy}>
          {busy ? "Working…" : confirmLabel}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

/** Confirmation for destructive actions with optional typed confirmation and async error display. */
export function DestructiveDialog({ open, onOpenChange, ...rest }: DestructiveDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mounted only while open so every opening starts with fresh state. */}
      {open && <Body onOpenChange={onOpenChange} {...rest} />}
    </Dialog>
  );
}
