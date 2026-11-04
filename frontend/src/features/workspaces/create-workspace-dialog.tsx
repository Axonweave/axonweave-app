"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { workspacesApi } from "@/lib/api/workspaces";
import { DEFAULT_FORM, WorkspaceFormFields, type WorkspaceFormData } from "./workspace-form";

interface CreateWorkspaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

/** The same fields and API call as the Workspaces page, usable from anywhere. */
export function CreateWorkspaceDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateWorkspaceDialogProps) {
  const { toast } = useToast();
  const [data, setData] = useState<WorkspaceFormData>(DEFAULT_FORM);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await workspacesApi.create({
        name: data.name,
        description: data.description || null,
        workspace_type: data.workspace_type,
        colour: data.colour,
      });
      toast({ title: "Workspace created" });
      setData(DEFAULT_FORM);
      onOpenChange(false);
      onCreated();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not create workspace.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false}>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <h2 className="text-lg font-semibold">Create workspace</h2>
          <WorkspaceFormFields data={data} onChange={setData} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !data.name.trim()}>
              {submitting ? "Saving…" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
