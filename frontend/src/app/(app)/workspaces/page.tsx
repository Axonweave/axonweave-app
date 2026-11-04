"use client";

import { useCallback, useEffect, useState } from "react";
import { Archive, ArchiveRestore, Edit2, MoreHorizontal, Plus, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorDisplay } from "@/components/ui/error-display";
import { useToast } from "@/hooks/use-toast";
import { workspacesApi } from "@/lib/api/workspaces";
import { ApiRequestError } from "@/lib/api/client";
import type { CreateWorkspaceRequest, UpdateWorkspaceRequest, Workspace, WorkspaceType } from "@/types/api";

const WS_TYPES: Array<{ value: WorkspaceType; label: string }> = [
  { value: "personal_learning", label: "Personal learning" },
  { value: "university", label: "University" },
  { value: "research", label: "Research" },
  { value: "professional_development", label: "Professional development" },
  { value: "custom", label: "Custom" },
];

const PRESET_COLOURS = [
  "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b",
  "#10b981", "#ef4444", "#6366f1", "#14b8a6",
];

function ColourPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {PRESET_COLOURS.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          className={`h-7 w-7 rounded-full border-2 transition-transform ${
            value === c ? "scale-110 border-foreground" : "border-transparent"
          }`}
          style={{ backgroundColor: c }}
          aria-label={c}
        />
      ))}
    </div>
  );
}

interface WorkspaceFormData {
  name: string;
  description: string;
  workspace_type: WorkspaceType;
  colour: string;
}

function WorkspaceFormFields({
  data,
  onChange,
}: {
  data: WorkspaceFormData;
  onChange: (d: WorkspaceFormData) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="ws-name">Name *</Label>
        <Input
          id="ws-name"
          value={data.name}
          onChange={(e) => onChange({ ...data, name: e.target.value })}
          maxLength={255}
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ws-desc">Description</Label>
        <Input
          id="ws-desc"
          value={data.description}
          onChange={(e) => onChange({ ...data, description: e.target.value })}
          maxLength={2000}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ws-type">Type</Label>
        <select
          id="ws-type"
          value={data.workspace_type}
          onChange={(e) => onChange({ ...data, workspace_type: e.target.value as WorkspaceType })}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {WS_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label>Colour</Label>
        <ColourPicker value={data.colour} onChange={(c) => onChange({ ...data, colour: c })} />
      </div>
    </div>
  );
}

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
          <span className="font-medium">{ws.name}</span>
          {ws.is_default && (
            <span className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              <Star className="h-3 w-3" />
              Default
            </span>
          )}
          {isArchived && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              Archived
            </span>
          )}
        </div>
        {ws.description && (
          <p className="mt-0.5 text-sm text-muted-foreground line-clamp-1">{ws.description}</p>
        )}
        <p className="mt-0.5 text-xs text-muted-foreground capitalize">
          {ws.workspace_type.replace(/_/g, " ")}
        </p>
      </div>

      {/* Action menu */}
      <div className="relative">
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
            className="absolute right-0 top-8 z-10 min-w-[160px] rounded-md border border-border bg-popover shadow-md"
            onBlur={() => setMenuOpen(false)}
          >
            {!isArchived && (
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onEdit(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <Edit2 className="h-4 w-4" /> Edit
              </button>
            )}
            {!isArchived && !ws.is_default && (
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onSetDefault(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <Star className="h-4 w-4" /> Set as default
              </button>
            )}
            {!isArchived && (
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onArchive(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <Archive className="h-4 w-4" /> Archive
              </button>
            )}
            {isArchived && (
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onRestore(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <ArchiveRestore className="h-4 w-4" /> Restore
              </button>
            )}
            {isArchived && (
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onDelete(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-destructive hover:bg-destructive/10"
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

const DEFAULT_FORM: WorkspaceFormData = {
  name: "",
  description: "",
  workspace_type: "personal_learning",
  colour: PRESET_COLOURS[0],
};

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
      setWorkspaces(r.data.data);
      setError(null);
    } catch {
      setError("Could not load workspaces.");
    } finally {
      setLoading(false);
    }
  }, [showArchived]);

  useEffect(() => { load(); }, [load]);

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
          <h1 className="text-2xl font-semibold text-foreground">Workspaces</h1>
          <p className="mt-1 text-sm text-muted-foreground">
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
          className="text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          {showArchived ? "Hide archived" : "Show archived"}
        </button>
      </div>

      {error && <ErrorDisplay message={error} onRetry={load} />}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading workspaces…</p>
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
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete workspace?"
        description={`This will permanently delete "${deleteTarget?.name}" and all its contents. This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        destructive
      />
    </div>
  );
}
