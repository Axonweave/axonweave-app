"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  MATRIX_ORIGIN_LABELS,
  matrixToCsv,
  researchApi,
  type MatrixSummary,
  type ResearchMatrix,
  type ResearchProject,
} from "@/lib/api/research";
import { downloadText, fileStem } from "./download";

const CARD = "border-border bg-card rounded-lg border p-4";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

function MatrixTable({
  initial,
  papers,
  readOnly,
  onChanged,
  onDeleted,
}: {
  initial: ResearchMatrix;
  papers: { id: string; title: string }[];
  readOnly: boolean;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const { toast } = useToast();
  const [m, setM] = useState(initial);
  const [search, setSearch] = useState("");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [desc, setDesc] = useState(false);
  const [groupByYear, setGroupByYear] = useState(false);
  const [editing, setEditing] = useState<{ paper: string; column: string } | null>(null);
  const [draft, setDraft] = useState("");
  const [newColumn, setNewColumn] = useState("");
  const [addPaper, setAddPaper] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  async function act(action: () => Promise<ResearchMatrix | unknown>) {
    setBusy(true);
    try {
      const next = await action();
      if (next && typeof next === "object" && "columns" in next) setM(next as ResearchMatrix);
      onChanged();
    } catch (e) {
      toast({ title: "Could not do that", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    let out = m.rows.filter(
      (r) =>
        !q ||
        r.paper.title.toLowerCase().includes(q) ||
        r.cells.some((c) => c.value.toLowerCase().includes(q)),
    );
    if (sortCol) {
      const val = (r: (typeof out)[number]) =>
        (r.cells.find((c) => c.column_id === sortCol)?.value ?? "").toLowerCase();
      out = [...out].sort((a, b) => (desc ? -1 : 1) * val(a).localeCompare(val(b)));
    }
    if (groupByYear) {
      out = [...out].sort(
        (a, b) => (b.paper.publication_year ?? 0) - (a.paper.publication_year ?? 0),
      );
    }
    return out;
  }, [m.rows, search, sortCol, desc, groupByYear]);

  const inMatrix = new Set(m.rows.map((r) => r.paper.id));
  const addable = papers.filter((p) => !inMatrix.has(p.id));
  const ids = m.columns.map((c) => c.id);

  function move(index: number, by: number) {
    const next = [...ids];
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item);
    void act(() => researchApi.matrixReorder(m.id, next));
  }

  function rename(id: string, current: string) {
    const title = window.prompt("Column name", current);
    if (title && title.trim() && title.trim() !== current) {
      void act(() => researchApi.matrixRenameColumn(m.id, id, title.trim()));
    }
  }

  const yearStart = useMemo(() => {
    const starts = new Map<string, number | null>();
    let last: number | null | undefined = undefined;
    for (const r of rows) {
      if (groupByYear && r.paper.publication_year !== last) {
        starts.set(r.paper.id, r.paper.publication_year);
        last = r.paper.publication_year;
      }
    }
    return starts;
  }, [rows, groupByYear]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-foreground text-base font-semibold">{m.title}</h3>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => downloadText(`${fileStem(m.title, "matrix")}.csv`, matrixToCsv(m))}
          >
            Export CSV
          </Button>
          {!readOnly && (
            <>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void act(() => researchApi.matrixRefresh(m.id))}
              >
                Refresh from analyses
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                onClick={() => setConfirmDelete(true)}
              >
                Delete matrix
              </Button>
            </>
          )}
        </div>
      </div>
      <p className="text-muted-foreground text-xs">
        Cells show what the paper reports, or are empty when it does not. Refreshing re-reads the
        paper analyses and never overwrites text you wrote yourself.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <input
          className={`${FIELD} max-w-xs`}
          aria-label="Search matrix"
          placeholder="Search papers and cells"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={groupByYear}
            onChange={(e) => setGroupByYear(e.target.checked)}
          />
          Group by year
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <caption className="sr-only">Evidence matrix</caption>
          <thead>
            <tr>
              {m.columns.map((c, i) => (
                <th key={c.id} scope="col" className="border-border border-b p-2 align-top">
                  <button
                    type="button"
                    className="font-medium"
                    aria-label={`Sort by ${c.title}`}
                    onClick={() => {
                      if (sortCol === c.id) setDesc(!desc);
                      else {
                        setSortCol(c.id);
                        setDesc(false);
                      }
                    }}
                  >
                    {c.title}
                    {sortCol === c.id ? (desc ? " ▼" : " ▲") : ""}
                  </button>
                  {!readOnly && (
                    <div className="mt-1 flex flex-wrap gap-1 text-xs font-normal">
                      <button
                        type="button"
                        aria-label={`Move ${c.title} left`}
                        disabled={i === 0 || busy}
                        onClick={() => move(i, -1)}
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        aria-label={`Move ${c.title} right`}
                        disabled={i === m.columns.length - 1 || busy}
                        onClick={() => move(i, 1)}
                      >
                        →
                      </button>
                      <button
                        type="button"
                        aria-label={`Rename ${c.title}`}
                        onClick={() => rename(c.id, c.title)}
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove ${c.title}`}
                        className="text-destructive"
                        onClick={() => void act(() => researchApi.matrixRemoveColumn(m.id, c.id))}
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </th>
              ))}
              {!readOnly && <th className="border-border border-b p-2" />}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={m.columns.length + 1} className="text-muted-foreground p-3">
                  {m.rows.length === 0
                    ? "No papers in this matrix yet. Add a paper below."
                    : "No rows match this search."}
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const startsGroup = yearStart.has(row.paper.id);
              const heading = yearStart.get(row.paper.id);
              return [
                startsGroup ? (
                  <tr key={`y-${row.paper.id}`}>
                    <th colSpan={m.columns.length + 1} className="bg-muted p-2">
                      {heading ?? "Year not entered"}
                    </th>
                  </tr>
                ) : null,
                <tr key={row.paper.id} className="align-top">
                  {m.columns.map((c) => {
                    const cell = row.cells.find((x) => x.column_id === c.id);
                    const isEditing = editing?.paper === row.paper.id && editing.column === c.id;
                    return (
                      <td key={c.id} className="border-border space-y-1 border-b p-2">
                        {isEditing ? (
                          <div className="space-y-1">
                            <textarea
                              className={FIELD}
                              aria-label={`Edit ${c.title}`}
                              rows={3}
                              maxLength={5000}
                              value={draft}
                              onChange={(e) => setDraft(e.target.value)}
                            />
                            <div className="flex gap-1">
                              <Button
                                size="sm"
                                disabled={busy}
                                onClick={() =>
                                  void act(async () => {
                                    const next = await researchApi.matrixEditCell(
                                      m.id,
                                      row.paper.id,
                                      c.id,
                                      draft,
                                    );
                                    setEditing(null);
                                    return next;
                                  })
                                }
                              >
                                Save
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                                Cancel
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <p className="whitespace-pre-wrap">
                              {cell?.value || (
                                <span className="text-muted-foreground">Not reported.</span>
                              )}
                            </p>
                            {cell && cell.value && cell.origin !== "extracted" && (
                              <p className="text-muted-foreground text-xs">
                                {MATRIX_ORIGIN_LABELS[cell.origin]}
                              </p>
                            )}
                            {cell?.evidence.slice(0, 2).map((ev) => (
                              <p key={ev.id} className="text-muted-foreground text-xs">
                                <q>{ev.quote}</q>
                                {ev.page_number ? ` · page ${ev.page_number}` : ""}
                                {ev.document_id && (
                                  <Link
                                    className="text-primary ml-1 underline"
                                    href={`/documents/${ev.document_id}${ev.page_number ? `?page=${ev.page_number}` : ""}`}
                                  >
                                    Open original
                                  </Link>
                                )}
                              </p>
                            ))}
                            {cell && cell.stale_evidence > 0 && (
                              <p className="text-xs text-amber-800">
                                {cell.stale_evidence} linked quotation
                                {cell.stale_evidence === 1 ? " is" : "s are"} no longer available.
                              </p>
                            )}
                            {!readOnly && (
                              <button
                                type="button"
                                className="text-primary text-xs underline"
                                aria-label={`Edit ${c.title} for ${row.paper.title}`}
                                onClick={() => {
                                  setEditing({ paper: row.paper.id, column: c.id });
                                  setDraft(cell?.value ?? "");
                                }}
                              >
                                Edit
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    );
                  })}
                  {!readOnly && (
                    <td className="border-border border-b p-2">
                      <button
                        type="button"
                        className="text-destructive text-xs"
                        aria-label={`Remove ${row.paper.title} from the matrix`}
                        onClick={() =>
                          void act(() => researchApi.matrixRemovePaper(m.id, row.paper.id))
                        }
                      >
                        Remove paper
                      </button>
                    </td>
                  )}
                </tr>,
              ];
            })}
          </tbody>
        </table>
      </div>

      {!readOnly && (
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex items-end gap-2">
            <label className="text-sm">
              <span className="text-muted-foreground">New column</span>
              <input
                className={`${FIELD} mt-1`}
                maxLength={80}
                value={newColumn}
                onChange={(e) => setNewColumn(e.target.value)}
              />
            </label>
            <Button
              size="sm"
              variant="outline"
              disabled={!newColumn.trim() || busy}
              onClick={() =>
                void act(async () => {
                  const next = await researchApi.matrixAddColumn(m.id, newColumn.trim());
                  setNewColumn("");
                  return next;
                })
              }
            >
              Add column
            </Button>
          </div>
          <div className="flex items-end gap-2">
            <label className="text-sm">
              <span className="text-muted-foreground">Add paper</span>
              <select
                className={`${FIELD} mt-1`}
                value={addPaper}
                onChange={(e) => setAddPaper(e.target.value)}
              >
                <option value="">Choose a paper</option>
                {addable.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </label>
            <Button
              size="sm"
              variant="outline"
              disabled={!addPaper || busy}
              onClick={() =>
                void act(async () => {
                  const next = await researchApi.matrixAddPapers(m.id, [addPaper]);
                  setAddPaper("");
                  return next;
                })
              }
            >
              Add to matrix
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this matrix?"
        description="The matrix and your edits are deleted. Papers and their analyses are not affected."
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          setConfirmDelete(false);
          void act(async () => {
            await researchApi.deleteMatrix(m.id);
            onDeleted();
          });
        }}
      />
    </div>
  );
}

export function MatrixWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const saved = useAsync(() => researchApi.listMatrices(project.id), [project.id]);
  const papers = useAsync(
    () => researchApi.listPapers(project.id, { archived: false, limit: 100 }),
    [project.id],
  );
  const all = (papers.data?.data ?? []).map((p) => ({ id: p.id, title: p.title }));
  const [title, setTitle] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [open, setOpen] = useState<ResearchMatrix | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    try {
      setOpen(
        await researchApi.createMatrix(project.id, { title: title.trim(), paper_ids: chosen }),
      );
      setTitle("");
      setChosen([]);
      saved.reload();
    } catch (e) {
      toast({ title: "Could not create", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function openSaved(s: MatrixSummary) {
    try {
      setOpen(await researchApi.getMatrix(s.id));
    } catch (e) {
      toast({ title: "Could not open", description: errorText(e), variant: "destructive" });
    }
  }

  return (
    <section aria-label="Evidence matrix" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Evidence matrix</h2>
      {!readOnly && (
        <div className={`${CARD} space-y-3`}>
          <label className="block text-sm">
            <span className="text-muted-foreground">Matrix title</span>
            <input
              className={`${FIELD} mt-1`}
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {all.length > 0 && (
            <fieldset className="space-y-1">
              <legend className="text-sm font-medium">Papers to include</legend>
              {all.map((p) => (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={chosen.includes(p.id)}
                    onChange={() =>
                      setChosen(
                        chosen.includes(p.id)
                          ? chosen.filter((x) => x !== p.id)
                          : [...chosen, p.id],
                      )
                    }
                  />
                  {p.title}
                </label>
              ))}
            </fieldset>
          )}
          <Button disabled={!title.trim() || busy} onClick={() => void create()}>
            Create matrix
          </Button>
        </div>
      )}

      <AsyncSection
        title="Saved matrices"
        loading={saved.loading}
        error={saved.error}
        onRetry={saved.reload}
        isEmpty={(saved.data?.data.length ?? 0) === 0}
        empty={<p className="text-muted-foreground text-sm">No matrices yet.</p>}
      >
        <ul className="space-y-2">
          {saved.data?.data.map((s) => (
            <li key={s.id} className={`${CARD} flex flex-wrap items-center justify-between gap-2`}>
              <span className="text-sm">
                <span className="text-foreground font-medium">{s.title}</span>
                <span className="text-muted-foreground"> · {s.paper_count} papers</span>
              </span>
              <Button size="sm" variant="outline" onClick={() => void openSaved(s)}>
                Open matrix
              </Button>
            </li>
          ))}
        </ul>
      </AsyncSection>

      {open && (
        <MatrixTable
          key={open.id}
          initial={open}
          papers={all}
          readOnly={readOnly}
          onChanged={saved.reload}
          onDeleted={() => {
            setOpen(null);
            saved.reload();
          }}
        />
      )}
    </section>
  );
}
