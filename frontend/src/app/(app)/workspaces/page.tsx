"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Archive, ArchiveRestore, Edit2, MoreHorizontal, Plus, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { useToast } from "@/hooks/use-toast";
import { workspacesApi } from "@/lib/api/workspaces";
import { ApiRequestError } from "@/lib/api/client";
import {
  DEFAULT_FORM,
  PRESET_COLOURS,
  WorkspaceFormFields,
  type WorkspaceFormData,
} from "@/features/workspaces/workspace-form";
import type {
  CreateWorkspaceRequest,
  UpdateWorkspaceRequest,
  Workspace,
  WorkspaceType,
} from "@/types/api";

function WorkspaceCard({
  ws,
  onEdit,
  onSetDefault,
  onArchive,
  onRestore,
  onDelete,
}: {
  ws: Workspace;
  onEdit: () => void;
  onSetDefault: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const isArchived = !!ws.archived_at;

  return (
    <div
      className={`relative flex items-start gap-4 rounded-lg border p-4 transition-colors ${
        isArchived ? "border-border/50 opacity-60" : "border-border hover:border-foreground/20"
      }`}
    >
      {/* Colour indicator */}
      <div
        className="mt-1 h-8 w-8 shrink-0 rounded-md"
        style={{ backgroundColor: ws.colour ?? "#6b7280" }}
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {isArchived ? (
            <span className="font-medium">{ws.name}</span>
          ) : (
            <Link
              href={`/workspaces/${ws.id}`}
              className="font-medium after:absolute after:inset-0 after:rounded-lg hover:underline"
            >
              {ws.name}
            </Link>
          )}
          {ws.is_default && (
            <span className="bg-primary/10 text-primary flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium">
              <Star className="h-3 w-3" />
              Default
            </span>
          )}
          {isArchived && (
            <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
              Archived
            </span>
          )}
        </div>
        {ws.description && (
          <p className="text-muted-foreground mt-0.5 line-clamp-1 text-sm">{ws.description}</p>
        )}
        <p className="text-muted-foreground mt-0.5 text-xs capitalize">
          {ws.workspace_type.replace(/_/g, " ")}
        </p>
      </div>

      {/* Action menu */}
      <div className="relative z-10">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="Workspace actions"
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
        {menuOpen && (
          <div
            className="border-border bg-popover absolute top-8 right-0 z-10 min-w-[160px] rounded-md border shadow-md"
            onBlur={() => setMenuOpen(false)}
          >
            {!isArchived && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onEdit();
                }}
                className="hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              >
                <Edit2 className="h-4 w-4" /> Edit
              </button>
            )}
            {!isArchived && !ws.is_default && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onSetDefault();
                }}
                className="hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              >
                <Star className="h-4 w-4" /> Set as default
              </button>
            )}
            {!isArchived && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onArchive();
                }}
                className="hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              >
                <Archive className="h-4 w-4" /> Archive
              </button>
            )}
            {isArchived && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onRestore();
                }}
                className="hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              >
                <ArchiveRestore className="h-4 w-4" /> Restore
              </button>
            )}
            {isArchived && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onDelete();
                }}
                className="text-destructive hover:bg-destructive/10 flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              >
                <Trash2 className="h-4 w-4" /> Delete
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function WorkspacesPage() {
  const { toast } = useToast();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  // Create/edit modal
  const [formOpen, setFormOpen] = useState(false);
  const [editingWs, setEditingWs] = useState<Workspace | null>(null);
  const [formData, setFormData] = useState<WorkspaceFormData>(DEFAULT_FORM);
  const [submitting, setSubmitting] = useState(false);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await workspacesApi.list(showArchived);
      setWorkspaces(r.data);
      setError(null);
    } catch {
      setError("Could not load workspaces.");
    } finally {
      setLoading(false);
    }
  }, [showArchived]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  function openCreate() {
    setEditingWs(null);
    setFormData(DEFAULT_FORM);
    setFormOpen(true);
  }

  function openEdit(ws: Workspace) {
    setEditingWs(ws);
    setFormData({
      name: ws.name,
      description: ws.description ?? "",
      workspace_type: ws.workspace_type as WorkspaceType,
      colour: ws.colour ?? PRESET_COLOURS[0],
    });
    setFormOpen(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload: CreateWorkspaceRequest | UpdateWorkspaceRequest = {
        name: formData.name,
        description: formData.description || null,
        workspace_type: formData.workspace_type,
        colour: formData.colour,
      };
      if (editingWs) {
        await workspacesApi.update(editingWs.id, payload);
        toast({ title: "Workspace updated" });
      } else {
        await workspacesApi.create(payload as CreateWorkspaceRequest);
        toast({ title: "Workspace created" });
      }
      setFormOpen(false);
      await load();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not save workspace.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSetDefault(ws: Workspace) {
    try {
      await workspacesApi.setDefault(ws.id);
      toast({ title: `"${ws.name}" is now the default workspace` });
      await load();
    } catch {
      toast({ title: "Could not set default workspace", variant: "destructive" });
    }
  }

  async function handleArchive(ws: Workspace) {
    if (ws.is_default) {
      toast({ title: "Cannot archive the default workspace", variant: "destructive" });
      return;
    }
    try {
      await workspacesApi.archive(ws.id);
      toast({ title: `"${ws.name}" archived` });
      await load();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not archive workspace.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    }
  }

  async function handleRestore(ws: Workspace) {
    try {
      await workspacesApi.restore(ws.id);
      toast({ title: `"${ws.name}" restored` });
      await load();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not restore workspace.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await workspacesApi.delete(deleteTarget.id);
      toast({ title: `"${deleteTarget.name}" deleted` });
      setDeleteTarget(null);
      await load();
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Could not delete workspace.";
      toast({ title: "Error", description: msg, variant: "destructive" });
    }
  }

  const visible = showArchived ? workspaces : workspaces.filter((w) => !w.archived_at);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-foreground text-2xl font-semibold">Workspaces</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Organise your learning into separate workspaces.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          New workspace
        </Button>
      </div>

      {/* Toggle archived */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setShowArchived((v) => !v)}
          className="text-muted-foreground hover:text-foreground text-sm underline-offset-2 hover:underline"
        >
          {showArchived ? "Hide archived" : "Show archived"}
        </button>
      </div>

      {error && <ErrorDisplay message={error} onRetry={load} />}

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading workspaces…</p>
      ) : visible.length === 0 ? (
        <EmptyState
          title={showArchived ? "No archived workspaces" : "No workspaces yet"}
          description="Create your first workspace to get started."
          action={<Button onClick={openCreate}>Create workspace</Button>}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((ws) => (
            <WorkspaceCard
              key={ws.id}
              ws={ws}
              onEdit={() => openEdit(ws)}
              onSetDefault={() => handleSetDefault(ws)}
              onArchive={() => handleArchive(ws)}
              onRestore={() => handleRestore(ws)}
              onDelete={() => setDeleteTarget(ws)}
            />
          ))}
        </div>
      )}

      {/* Create / Edit modal */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent showCloseButton={false}>
          <form onSubmit={handleSubmit} className="space-y-4 p-6">
            <h2 className="text-lg font-semibold">
              {editingWs ? "Edit workspace" : "Create workspace"}
            </h2>
            <WorkspaceFormFields data={formData} onChange={setFormData} />
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting || !formData.name.trim()}>
                {submitting ? "Saving…" : editingWs ? "Save changes" : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete workspace?"
        description={`This will permanently delete "${deleteTarget?.name}" and all its contents. This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        destructive
      />
    </div>
  );
}
