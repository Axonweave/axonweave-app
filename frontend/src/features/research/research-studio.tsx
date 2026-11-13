"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  PROJECT_STATUSES,
  STATUS_LABELS,
  linesToList,
  researchApi,
  type ProjectStatus,
  type ResearchProject,
} from "@/lib/api/research";
import { workspacesApi } from "@/lib/api/workspaces";
import { PaperLibrary } from "./paper-library";

const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";
const CARD = "border-border bg-card rounded-lg border p-4";
const PAGE = 12;

function fmt(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString() : "Not set";
}

interface FormState {
  title: string;
  description: string;
  domain: string;
  problem: string;
  objectives: string;
  questions: string;
  keywords: string;
  status: ProjectStatus;
  start: string;
  target: string;
}

function toForm(p?: ResearchProject): FormState {
  return {
    title: p?.title ?? "",
    description: p?.description ?? "",
    domain: p?.domain ?? "",
    problem: p?.research_problem ?? "",
    objectives: (p?.objectives ?? []).join("\n"),
    questions: (p?.research_questions ?? []).join("\n"),
    keywords: (p?.keywords ?? []).join(", "),
    status: (p?.status as ProjectStatus | undefined) ?? "planning",
    start: p?.start_date ?? "",
    target: p?.target_date ?? "",
  };
}

function ProjectForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: ResearchProject;
  submitLabel: string;
  onSubmit: (f: FormState) => Promise<void>;
  onCancel: () => void;
}) {
  const [f, setF] = useState<FormState>(toForm(initial));
  const [busy, setBusy] = useState(false);
  const set = (k: keyof FormState, v: string) => setF((s) => ({ ...s, [k]: v }));
  const datesBad = !!f.start && !!f.target && f.target < f.start;
  const valid = f.title.trim().length >= 2 && !datesBad;
  return (
    <form
      className={`${CARD} space-y-3`}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        setBusy(true);
        try {
          await onSubmit(f);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <label htmlFor="rp-title" className="text-sm font-medium">
          Title
        </label>
        <input
          id="rp-title"
          className={FIELD}
          value={f.title}
          maxLength={200}
          onChange={(e) => set("title", e.target.value)}
          required
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="rp-domain" className="text-sm font-medium">
            Research domain
          </label>
          <input
            id="rp-domain"
            className={FIELD}
            value={f.domain}
            maxLength={120}
            onChange={(e) => set("domain", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="rp-status" className="text-sm font-medium">
            Status
          </label>
          <select
            id="rp-status"
            className={`${SELECT} w-full`}
            value={f.status}
            onChange={(e) => set("status", e.target.value)}
          >
            {PROJECT_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="rp-start" className="text-sm font-medium">
            Start date
          </label>
          <input
            id="rp-start"
            type="date"
            className={FIELD}
            value={f.start}
            onChange={(e) => set("start", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="rp-target" className="text-sm font-medium">
            Target completion date
          </label>
          <input
            id="rp-target"
            type="date"
            className={FIELD}
            value={f.target}
            onChange={(e) => set("target", e.target.value)}
          />
        </div>
      </div>
      {datesBad && (
        <p role="alert" className="text-destructive text-sm">
          The target date cannot be before the start date.
        </p>
      )}
      <div>
        <label htmlFor="rp-desc" className="text-sm font-medium">
          Description
        </label>
        <textarea
          id="rp-desc"
          className={FIELD}
          rows={2}
          maxLength={4000}
          value={f.description}
          onChange={(e) => set("description", e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="rp-problem" className="text-sm font-medium">
          Research problem
        </label>
        <textarea
          id="rp-problem"
          className={FIELD}
          rows={2}
          maxLength={4000}
          value={f.problem}
          onChange={(e) => set("problem", e.target.value)}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="rp-objectives" className="text-sm font-medium">
            Research objectives (one per line)
          </label>
          <textarea
            id="rp-objectives"
            className={FIELD}
            rows={3}
            value={f.objectives}
            onChange={(e) => set("objectives", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="rp-questions" className="text-sm font-medium">
            Research questions (one per line)
          </label>
          <textarea
            id="rp-questions"
            className={FIELD}
            rows={3}
            value={f.questions}
            onChange={(e) => set("questions", e.target.value)}
          />
        </div>
      </div>
      <div>
        <label htmlFor="rp-keywords" className="text-sm font-medium">
          Keywords (comma separated)
        </label>
        <input
          id="rp-keywords"
          className={FIELD}
          value={f.keywords}
          onChange={(e) => set("keywords", e.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={!valid || busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function formToBody(f: FormState) {
  return {
    title: f.title.trim(),
    description: f.description.trim() || null,
    domain: f.domain.trim() || null,
    research_problem: f.problem.trim() || null,
    objectives: linesToList(f.objectives),
    research_questions: linesToList(f.questions),
    keywords: f.keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean),
    status: f.status,
    start_date: f.start || null,
    target_date: f.target || null,
  };
}

function Overview({
  p,
  onEdit,
  onArchive,
  onRestore,
  onDelete,
  onClose,
}: {
  p: ResearchProject;
  onEdit: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const archived = p.archived_at !== null;
  return (
    <section className={`${CARD} space-y-3`} aria-label="Project overview">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-foreground text-lg font-semibold">{p.title}</h2>
          <p className="text-muted-foreground text-sm">
            {archived ? "Archived" : (STATUS_LABELS[p.status] ?? p.status)}
            {p.domain ? ` · ${p.domain}` : ""}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      {p.description && <p className="text-sm">{p.description}</p>}
      {p.research_problem && (
        <div>
          <h3 className="text-sm font-semibold">Research problem</h3>
          <p className="text-sm">{p.research_problem}</p>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">Objectives</h3>
          {p.objectives.length === 0 ? (
            <p className="text-muted-foreground text-sm">None added yet.</p>
          ) : (
            <ul className="list-disc pl-5 text-sm">
              {p.objectives.map((o) => (
                <li key={o}>{o}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-sm font-semibold">Research questions</h3>
          {p.research_questions.length === 0 ? (
            <p className="text-muted-foreground text-sm">None added yet.</p>
          ) : (
            <ol className="list-decimal pl-5 text-sm">
              {p.research_questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ol>
          )}
        </div>
      </div>
      {p.keywords.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Keywords">
          {p.keywords.map((k) => (
            <li key={k} className="bg-muted rounded-full px-2 py-0.5 text-xs">
              {k}
            </li>
          ))}
        </ul>
      )}
      <p className="text-muted-foreground text-xs">
        Start {fmt(p.start_date)} · Target {fmt(p.target_date)} · Created {fmt(p.created_at)} ·
        Updated {fmt(p.updated_at)}
      </p>
      <p className="text-muted-foreground text-xs">
        Analyses, notes and drafts will appear here as those parts of Research Studio are added.
      </p>
      <div className="flex flex-wrap gap-2">
        {!archived && (
          <Button size="sm" onClick={onEdit}>
            Edit
          </Button>
        )}
        {archived ? (
          <Button size="sm" variant="outline" onClick={onRestore}>
            Restore
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={onArchive}>
            Archive
          </Button>
        )}
        <Button size="sm" variant="ghost" className="text-destructive" onClick={onDelete}>
          Delete
        </Button>
      </div>
    </section>
  );
}

export function ResearchStudio() {
  const { toast } = useToast();
  const [workspaceId, setWorkspaceId] = useState("");
  const [status, setStatus] = useState("");
  const [archived, setArchived] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"none" | "create" | "edit">("none");
  const [selected, setSelected] = useState<ResearchProject | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  const activeWorkspace = workspaceId || workspaces.data?.[0]?.id || "";
  const projects = useAsync(
    () =>
      researchApi.listProjects({
        workspace_id: activeWorkspace || undefined,
        status: status || undefined,
        q: q || undefined,
        archived,
        limit: PAGE,
        offset,
      }),
    [activeWorkspace, status, q, archived, offset],
  );

  const fail = (err: unknown) =>
    toast({
      title: err instanceof ApiRequestError ? err.message : "Something went wrong",
      variant: "destructive",
    });

  async function create(f: Parameters<typeof formToBody>[0]) {
    try {
      const created = await researchApi.createProject({
        workspace_id: activeWorkspace,
        ...formToBody(f),
      });
      setMode("none");
      setSelected(created);
      projects.reload();
      toast({ title: "Project created" });
    } catch (err) {
      fail(err);
    }
  }

  async function save(f: Parameters<typeof formToBody>[0]) {
    if (!selected) return;
    try {
      const updated = await researchApi.updateProject(selected.id, formToBody(f));
      setSelected(updated);
      setMode("none");
      projects.reload();
    } catch (err) {
      fail(err);
    }
  }

  async function run(action: () => Promise<ResearchProject>) {
    try {
      const updated = await action();
      setSelected(updated);
      projects.reload();
    } catch (err) {
      fail(err);
    }
  }

  async function remove() {
    if (!selected) return;
    try {
      await researchApi.deleteProject(selected.id);
      setSelected(null);
      projects.reload();
      toast({ title: "Project deleted" });
    } catch (err) {
      fail(err);
    }
  }

  const list = projects.data?.data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {(workspaces.data?.length ?? 0) > 1 && (
          <select
            className={SELECT}
            aria-label="Workspace"
            value={activeWorkspace}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              setOffset(0);
              setSelected(null);
            }}
          >
            {workspaces.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        )}
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setQ(searchInput.trim());
            setOffset(0);
          }}
        >
          <input
            className="border-input bg-background h-9 rounded-md border px-2 text-sm"
            placeholder="Search projects"
            aria-label="Search projects"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </form>
        <select
          className={SELECT}
          aria-label="Filter by status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          {PROJECT_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => {
              setArchived(e.target.checked);
              setOffset(0);
              setSelected(null);
            }}
          />
          Archived
        </label>
        <Button
          className="ml-auto"
          disabled={!activeWorkspace}
          onClick={() => {
            setSelected(null);
            setMode("create");
          }}
        >
          New project
        </Button>
      </div>

      {mode === "create" && (
        <ProjectForm
          submitLabel="Create project"
          onSubmit={create}
          onCancel={() => setMode("none")}
        />
      )}
      {mode === "edit" && selected && (
        <ProjectForm
          key={selected.id}
          initial={selected}
          submitLabel="Save changes"
          onSubmit={save}
          onCancel={() => setMode("none")}
        />
      )}
      {mode === "none" && selected && (
        <Overview
          p={selected}
          onEdit={() => setMode("edit")}
          onArchive={() => run(() => researchApi.archiveProject(selected.id))}
          onRestore={() => run(() => researchApi.restoreProject(selected.id))}
          onDelete={() => setConfirmDelete(true)}
          onClose={() => setSelected(null)}
        />
      )}

      {mode === "none" && selected && <PaperLibrary key={selected.id} project={selected} />}

      <AsyncSection
        title="Research projects"
        loading={projects.loading}
        error={projects.error}
        onRetry={projects.reload}
        isEmpty={list.length === 0}
        empty={
          <p className="text-muted-foreground py-8 text-center text-sm">
            {q || status || archived
              ? "No projects match these filters."
              : "No research projects yet. Create one to start organising your research."}
          </p>
        }
      >
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className={`${CARD} hover:bg-muted/50 w-full text-left ${
                  selected?.id === p.id ? "ring-primary ring-2" : ""
                }`}
                onClick={() => {
                  setMode("none");
                  setSelected(p);
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-foreground font-medium">{p.title}</span>
                  <span className="bg-muted shrink-0 rounded-full px-2 py-0.5 text-xs">
                    {p.archived_at ? "Archived" : (STATUS_LABELS[p.status] ?? p.status)}
                  </span>
                </div>
                {p.domain && <p className="text-muted-foreground mt-1 text-xs">{p.domain}</p>}
                <p className="text-muted-foreground mt-2 text-sm">
                  {p.paper_count} paper{p.paper_count === 1 ? "" : "s"} ·{" "}
                  {p.research_questions.length === 0
                    ? "No research questions yet"
                    : `${p.research_questions.length} research question${
                        p.research_questions.length === 1 ? "" : "s"
                      }`}
                </p>
                <p className="text-muted-foreground mt-1 text-xs">Updated {fmt(p.updated_at)}</p>
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <Pager
            offset={offset}
            limit={PAGE}
            total={projects.data?.total ?? 0}
            onChange={setOffset}
          />
        </div>
      </AsyncSection>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this research project?"
        description="This permanently deletes the project and everything attached to it. This cannot be undone. To keep it, archive it instead."
        confirmLabel="Delete"
        destructive
        onConfirm={remove}
      />
    </div>
  );
}
