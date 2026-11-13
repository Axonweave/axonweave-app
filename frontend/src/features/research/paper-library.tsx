"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import { STATUS_LABELS as DOC_STATUS, documentsApi } from "@/lib/api/documents";
import {
  ANALYSIS_LABELS,
  PAPER_STATUSES,
  SOURCE_LABELS,
  linesToList,
  researchApi,
  type DuplicateCandidate,
  type PaperCreate,
  type ResearchPaper,
  type ResearchProject,
} from "@/lib/api/research";

const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";
const CARD = "border-border bg-card rounded-lg border p-4";
const PAGE = 10;

type AddMode = "manual" | "doi" | "upload" | "document";

const ADD_MODES: { id: AddMode; label: string }[] = [
  { id: "manual", label: "Enter details" },
  { id: "doi", label: "Add by DOI" },
  { id: "upload", label: "Upload PDF" },
  { id: "document", label: "Use an existing document" },
];

interface FormState {
  title: string;
  authors: string;
  year: string;
  venue: string;
  publisher: string;
  doi: string;
  url: string;
  abstract: string;
  keywords: string;
  volume: string;
  issue: string;
  pages: string;
  status: string;
  verified: boolean;
  documentId: string;
}

function toForm(p?: ResearchPaper): FormState {
  return {
    title: p?.title ?? "",
    authors: (p?.authors ?? []).join("\n"),
    year: p?.publication_year ? String(p.publication_year) : "",
    venue: p?.venue ?? "",
    publisher: p?.publisher ?? "",
    doi: p?.doi ?? "",
    url: p?.url ?? "",
    abstract: p?.abstract ?? "",
    keywords: (p?.keywords ?? []).join(", "),
    volume: p?.volume ?? "",
    issue: p?.issue ?? "",
    pages: p?.pages ?? "",
    status: p?.status ?? "unread",
    verified: p?.metadata_verified ?? false,
    documentId: p?.document_id ?? "",
  };
}

function toBody(f: FormState) {
  const year = Number.parseInt(f.year, 10);
  return {
    title: f.title.trim(),
    authors: linesToList(f.authors),
    publication_year: Number.isFinite(year) ? year : null,
    venue: f.venue.trim() || null,
    publisher: f.publisher.trim() || null,
    doi: f.doi.trim() || null,
    url: f.url.trim() || null,
    abstract: f.abstract.trim() || null,
    keywords: f.keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean),
    volume: f.volume.trim() || null,
    issue: f.issue.trim() || null,
    pages: f.pages.trim() || null,
    status: f.status as PaperCreate["status"],
  };
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  max,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  max?: number;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        type={type}
        className={FIELD}
        value={value}
        maxLength={max}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function PaperForm({
  mode,
  initial,
  workspaceId,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  mode: AddMode | "edit";
  initial?: ResearchPaper;
  workspaceId: string;
  submitLabel: string;
  onSubmit: (f: FormState, file: File | null) => Promise<void>;
  onCancel: () => void;
}) {
  const [f, setF] = useState<FormState>(toForm(initial));
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof FormState, v: string | boolean) => setF((s) => ({ ...s, [k]: v }));
  const docs = useAsync(
    () =>
      mode === "document"
        ? documentsApi.list({ workspace_id: workspaceId, limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [mode, workspaceId],
  );
  const yearBad = f.year !== "" && !/^\d{4}$/.test(f.year);
  const needsFile = mode === "upload" && !file;
  const needsDoc = mode === "document" && !f.documentId;
  const needsDoi = mode === "doi" && !f.doi.trim();
  const valid = f.title.trim().length >= 2 && !yearBad && !needsFile && !needsDoc && !needsDoi;
  const full = mode === "manual" || mode === "edit";

  return (
    <form
      className={`${CARD} space-y-3`}
      aria-label={initial ? "Edit paper" : "Add paper"}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        setBusy(true);
        try {
          await onSubmit(f, file);
        } finally {
          setBusy(false);
        }
      }}
    >
      {mode === "upload" && (
        <div>
          <label htmlFor="pp-file" className="text-sm font-medium">
            PDF file
          </label>
          <input
            id="pp-file"
            type="file"
            accept="application/pdf,.pdf"
            className={FIELD}
            onChange={(e) => {
              const picked = e.target.files?.[0] ?? null;
              setFile(picked);
              if (picked && !f.title) set("title", picked.name.replace(/\.pdf$/i, ""));
            }}
          />
          <p className="text-muted-foreground mt-1 text-xs">
            The file is checked and processed like any other document. Check the title before
            saving: it starts as the file name, not as extracted metadata.
          </p>
        </div>
      )}
      {mode === "document" && (
        <div>
          <label htmlFor="pp-doc" className="text-sm font-medium">
            Document
          </label>
          <select
            id="pp-doc"
            className={`${SELECT} w-full`}
            value={f.documentId}
            onChange={(e) => {
              set("documentId", e.target.value);
              const d = docs.data?.find((x) => x.id === e.target.value);
              if (d && !f.title) set("title", d.display_name.replace(/\.pdf$/i, ""));
            }}
          >
            <option value="">Choose a document</option>
            {docs.data?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.display_name}
              </option>
            ))}
          </select>
        </div>
      )}
      {mode === "doi" && (
        <div>
          <Field id="pp-doi" label="DOI" value={f.doi} onChange={(v) => set("doi", v)} max={200} />
          <p className="text-muted-foreground mt-1 text-xs">
            Online metadata lookup is not set up, so enter the title and any details you have. The
            DOI is saved and used to spot duplicates.
          </p>
        </div>
      )}
      <Field
        id="pp-title"
        label="Title"
        value={f.title}
        onChange={(v) => set("title", v)}
        max={500}
      />
      {full && (
        <>
          <div>
            <label htmlFor="pp-authors" className="text-sm font-medium">
              Authors (one per line)
            </label>
            <textarea
              id="pp-authors"
              className={FIELD}
              rows={3}
              value={f.authors}
              onChange={(e) => set("authors", e.target.value)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              id="pp-year"
              label="Publication year"
              value={f.year}
              onChange={(v) => set("year", v)}
              max={4}
            />
            <Field
              id="pp-venue"
              label="Journal or conference"
              value={f.venue}
              onChange={(v) => set("venue", v)}
              max={300}
            />
            <Field
              id="pp-publisher"
              label="Publisher"
              value={f.publisher}
              onChange={(v) => set("publisher", v)}
              max={200}
            />
            <Field
              id="pp-doi2"
              label="DOI"
              value={f.doi}
              onChange={(v) => set("doi", v)}
              max={200}
            />
            <Field
              id="pp-url"
              label="Publication URL"
              value={f.url}
              onChange={(v) => set("url", v)}
              max={1000}
            />
            <Field
              id="pp-keywords"
              label="Keywords (comma separated)"
              value={f.keywords}
              onChange={(v) => set("keywords", v)}
            />
            <Field
              id="pp-volume"
              label="Volume"
              value={f.volume}
              onChange={(v) => set("volume", v)}
              max={40}
            />
            <Field
              id="pp-issue"
              label="Issue"
              value={f.issue}
              onChange={(v) => set("issue", v)}
              max={40}
            />
            <Field
              id="pp-pages"
              label="Pages"
              value={f.pages}
              onChange={(v) => set("pages", v)}
              max={40}
            />
            <div>
              <label htmlFor="pp-status" className="text-sm font-medium">
                Reading status
              </label>
              <select
                id="pp-status"
                className={`${SELECT} w-full`}
                value={f.status}
                onChange={(e) => set("status", e.target.value)}
              >
                {PAPER_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label htmlFor="pp-abstract" className="text-sm font-medium">
              Abstract
            </label>
            <textarea
              id="pp-abstract"
              className={FIELD}
              rows={4}
              maxLength={10000}
              value={f.abstract}
              onChange={(e) => set("abstract", e.target.value)}
            />
          </div>
        </>
      )}
      {yearBad && (
        <p role="alert" className="text-destructive text-sm">
          The year must have four digits.
        </p>
      )}
      {mode === "edit" && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={f.verified}
            onChange={(e) => set("verified", e.target.checked)}
          />
          I have checked this metadata against the paper
        </label>
      )}
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

function PaperRow({
  p,
  onEdit,
  onArchive,
  onRestore,
  onDelete,
}: {
  p: ResearchPaper;
  onEdit: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  const archived = p.archived_at !== null;
  return (
    <li className={`${CARD} space-y-1`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-foreground font-medium">{p.title}</h3>
        <span className="bg-muted rounded-full px-2 py-0.5 text-xs capitalize">{p.status}</span>
      </div>
      <p className="text-muted-foreground text-sm">
        {p.authors.length
          ? p.authors.slice(0, 4).join(", ") + (p.authors.length > 4 ? " et al." : "")
          : "Authors not entered"}
        {p.publication_year ? ` · ${p.publication_year}` : ""}
        {p.venue ? ` · ${p.venue}` : ""}
      </p>
      <p className="text-muted-foreground text-xs">
        {p.doi ? `DOI ${p.doi} · ` : ""}
        {SOURCE_LABELS[p.metadata_source] ?? p.metadata_source}
        {p.metadata_verified ? " · verified by you" : " · not yet verified"}
      </p>
      <p className="text-xs">
        {p.document_id
          ? `File: ${p.document_name ?? "document"} (${DOC_STATUS[p.processing_status ?? ""] ?? p.processing_status})`
          : "No file attached"}
        {" · "}
        {ANALYSIS_LABELS[p.analysis_status] ?? p.analysis_status}
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        {!archived && (
          <Button size="sm" variant="outline" onClick={onEdit}>
            Edit details
          </Button>
        )}
        {archived ? (
          <Button size="sm" variant="outline" onClick={onRestore}>
            Restore
          </Button>
        ) : (
          <Button size="sm" variant="ghost" onClick={onArchive}>
            Archive
          </Button>
        )}
        <Button size="sm" variant="ghost" className="text-destructive" onClick={onDelete}>
          Remove
        </Button>
      </div>
    </li>
  );
}

function DuplicateReview({
  items,
  onResolve,
}: {
  items: DuplicateCandidate[];
  onResolve: (
    c: DuplicateCandidate,
    action: "not_duplicate" | "merge",
    survivor?: string,
  ) => Promise<void>;
}) {
  if (items.length === 0)
    return (
      <p className="text-muted-foreground text-sm">
        No possible duplicates. Papers are only suggested when their titles match closely, and they
        are never merged without your decision.
      </p>
    );
  return (
    <ul className="space-y-3">
      {items.map((c) => (
        <li key={`${c.paper_a.id}-${c.paper_b.id}`} className={`${CARD} space-y-2`}>
          <p className="text-muted-foreground text-xs">
            {c.reason === "same_title" ? "Same title" : "Very similar titles"}
            {c.shared_authors.length ? ` · shared author: ${c.shared_authors.join(", ")}` : ""}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {[c.paper_a, c.paper_b].map((p) => (
              <div key={p.id} className="text-sm">
                <p className="font-medium">{p.title}</p>
                <p className="text-muted-foreground text-xs">
                  {p.authors.join(", ") || "No authors"}
                  {p.publication_year ? ` · ${p.publication_year}` : ""}
                  {p.doi ? ` · ${p.doi}` : ""}
                  {p.has_file ? " · has file" : ""}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-1"
                  onClick={() => onResolve(c, "merge", p.id)}
                >
                  Merge into this one
                </Button>
              </div>
            ))}
          </div>
          <Button size="sm" variant="ghost" onClick={() => onResolve(c, "not_duplicate")}>
            These are different papers
          </Button>
        </li>
      ))}
    </ul>
  );
}

export function PaperLibrary({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const [view, setView] = useState<"list" | "duplicates">("list");
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState<AddMode | null>(null);
  const [editing, setEditing] = useState<ResearchPaper | null>(null);
  const [removing, setRemoving] = useState<ResearchPaper | null>(null);

  const readOnly = project.archived_at !== null;
  const papers = useAsync(
    () =>
      researchApi.listPapers(project.id, {
        q: q || undefined,
        status: status || undefined,
        archived,
        limit: PAGE,
        offset,
      }),
    [project.id, q, status, archived, offset],
  );
  const dupes = useAsync(() => researchApi.duplicates(project.id), [project.id, papers.data]);

  const fail = (err: unknown) =>
    toast({
      title: err instanceof ApiRequestError ? err.message : "Something went wrong",
      variant: "destructive",
    });

  async function add(f: FormState, file: File | null) {
    try {
      let documentId: string | undefined = f.documentId || undefined;
      if (adding === "upload" && file) {
        const result = await documentsApi.upload([file], { workspace_id: project.workspace_id });
        const doc = result.documents[0];
        if (!doc) {
          toast({
            title: result.rejected[0]?.message ?? "The file was not accepted",
            variant: "destructive",
          });
          return;
        }
        documentId = doc.id;
      }
      await researchApi.addPaper(project.id, { ...toBody(f), document_id: documentId });
      setAdding(null);
      setOffset(0);
      papers.reload();
      toast({ title: "Paper added" });
    } catch (err) {
      fail(err);
    }
  }

  async function save(f: FormState) {
    if (!editing) return;
    try {
      await researchApi.updatePaper(editing.id, { ...toBody(f), metadata_verified: f.verified });
      setEditing(null);
      papers.reload();
    } catch (err) {
      fail(err);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      papers.reload();
    } catch (err) {
      fail(err);
    }
  }

  async function resolve(
    c: DuplicateCandidate,
    action: "not_duplicate" | "merge",
    survivor?: string,
  ) {
    await act(() =>
      researchApi.resolveDuplicate(project.id, {
        paper_id: c.paper_a.id,
        other_id: c.paper_b.id,
        action,
        survivor_id: survivor,
      }),
    );
  }

  const list = papers.data?.data ?? [];
  const dupCount = dupes.data?.length ?? 0;
  return (
    <section className="space-y-3" aria-label="Paper library">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-foreground text-lg font-semibold">Papers</h2>
        <div role="tablist" className="ml-2 flex gap-1">
          {(["list", "duplicates"] as const).map((v) => (
            <button
              key={v}
              role="tab"
              type="button"
              aria-selected={view === v}
              onClick={() => setView(v)}
              className={`rounded-md px-3 py-1 text-sm ${
                view === v ? "bg-muted font-medium" : "text-muted-foreground"
              }`}
            >
              {v === "list" ? "Library" : `Possible duplicates${dupCount ? ` (${dupCount})` : ""}`}
            </button>
          ))}
        </div>
      </div>

      {view === "duplicates" ? (
        <AsyncSection
          title="Possible duplicates"
          loading={dupes.loading}
          error={dupes.error}
          onRetry={dupes.reload}
          isEmpty={false}
          empty={null}
        >
          <DuplicateReview items={dupes.data ?? []} onResolve={resolve} />
        </AsyncSection>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
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
                placeholder="Search papers"
                aria-label="Search papers"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </form>
            <select
              className={SELECT}
              aria-label="Filter by reading status"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Any status</option>
              {PAPER_STATUSES.map((s) => (
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
                }}
              />
              Archived papers
            </label>
          </div>
          {!readOnly && !adding && !editing && (
            <div className="flex flex-wrap gap-2">
              {ADD_MODES.map((m) => (
                <Button key={m.id} size="sm" variant="outline" onClick={() => setAdding(m.id)}>
                  {m.label}
                </Button>
              ))}
            </div>
          )}
          {adding && (
            <PaperForm
              key={adding}
              mode={adding}
              workspaceId={project.workspace_id}
              submitLabel="Add paper"
              onSubmit={add}
              onCancel={() => setAdding(null)}
            />
          )}
          {editing && (
            <PaperForm
              key={editing.id}
              mode="edit"
              initial={editing}
              workspaceId={project.workspace_id}
              submitLabel="Save changes"
              onSubmit={save}
              onCancel={() => setEditing(null)}
            />
          )}
          <AsyncSection
            title="Papers in this project"
            loading={papers.loading}
            error={papers.error}
            onRetry={papers.reload}
            isEmpty={list.length === 0}
            empty={
              <p className="text-muted-foreground py-6 text-center text-sm">
                {q || status || archived
                  ? "No papers match these filters."
                  : "No papers yet. Add one by entering its details, a DOI or a PDF."}
              </p>
            }
          >
            <ul className="space-y-3">
              {list.map((p) => (
                <PaperRow
                  key={p.id}
                  p={p}
                  onEdit={() => {
                    setAdding(null);
                    setEditing(p);
                  }}
                  onArchive={() => act(() => researchApi.archivePaper(p.id))}
                  onRestore={() => act(() => researchApi.restorePaper(p.id))}
                  onDelete={() => setRemoving(p)}
                />
              ))}
            </ul>
            <div className="mt-3">
              <Pager
                offset={offset}
                limit={PAGE}
                total={papers.data?.total ?? 0}
                onChange={setOffset}
              />
            </div>
          </AsyncSection>
        </>
      )}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Remove this paper from the project?"
        description="The library record is deleted. A document attached to it stays in your document library."
        confirmLabel="Remove"
        destructive
        onConfirm={() => {
          const target = removing;
          setRemoving(null);
          if (target) void act(() => researchApi.deletePaper(target.id));
        }}
      />
    </section>
  );
}
