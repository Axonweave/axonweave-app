"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  COMPARE_DIMENSIONS,
  COMPARE_NOT_REPORTED,
  comparisonToCsv,
  researchApi,
  type CompareResult,
  type ComparisonDimension,
  type ComparisonSummary,
  type ResearchComparison,
  type ResearchProject,
} from "@/lib/api/research";

const CARD = "border-border bg-card rounded-lg border p-4";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";
const MAX_PAPERS = 6;

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const AGREEMENT: Record<string, string> = {
  similar: "Similar",
  different: "Different",
  unknown: "Not confirmed (not reported)",
};

function Matrix({
  cmp,
  readOnly,
  onSaved,
}: {
  cmp: ResearchComparison;
  readOnly: boolean;
  onSaved: (c: ResearchComparison) => void;
}) {
  const { toast } = useToast();
  const result = cmp.result as unknown as CompareResult;
  const [notes, setNotes] = useState<Record<string, string>>({ ...cmp.notes });
  const [busy, setBusy] = useState(false);
  const title = new Map(result.papers.map((p) => [p.paper_id, p.title]));
  const comp = result.comparability;

  async function saveNotes() {
    setBusy(true);
    try {
      onSaved(await researchApi.patchComparison(cmp.id, { notes }));
      toast({ title: "Notes saved" });
    } catch (e) {
      toast({ title: "Could not save notes", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-foreground text-base font-semibold">{cmp.title}</h3>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            download(
              `${cmp.title.replace(/[^\w-]+/g, "_").slice(0, 60) || "comparison"}.csv`,
              comparisonToCsv(result, cmp.notes),
            )
          }
        >
          Export CSV
        </Button>
      </div>

      <div className={`${CARD} space-y-1 text-sm`} role="note" aria-label="Comparability">
        <p className="text-foreground font-medium">
          {comp.results_directly_comparable
            ? "Same dataset and metrics: results can be set against each other."
            : "Results are not shown as directly comparable."}
        </p>
        <p className="text-muted-foreground text-xs">
          Dataset: {AGREEMENT[comp.dataset]} · Metrics: {AGREEMENT[comp.metrics]} · Setup:{" "}
          {AGREEMENT[comp.setup]} · Methodology: {AGREEMENT[comp.methodology]}
        </p>
        <ul className="list-disc pl-5">
          {comp.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
        <p className="text-muted-foreground text-xs">
          Similarities and differences below are shared and unique wording in each paper’s extracted
          claims, not a judgement. Built from analysis version
          {result.papers.length > 1 ? "s" : ""}{" "}
          {result.papers.map((p) => `${p.title} v${p.version_number}`).join(", ")}.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-sm">
          <caption className="sr-only">Comparison matrix</caption>
          <thead>
            <tr>
              <th scope="col" className="border-border border-b p-2">
                Dimension
              </th>
              {result.papers.map((p) => (
                <th key={p.paper_id} scope="col" className="border-border border-b p-2">
                  {p.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row) => (
              <tr key={row.dimension} className="align-top">
                <th scope="row" className="border-border border-b p-2 font-medium">
                  {row.label}
                  {row.dimension === "results" && row.directly_comparable === false && (
                    <span className="mt-1 block text-xs font-normal text-amber-800">
                      Conditions differ or are not confirmed: do not compare these numbers directly.
                    </span>
                  )}
                </th>
                {result.papers.map((p) => {
                  const cell = row.cells.find((c) => c.paper_id === p.paper_id);
                  return (
                    <td key={p.paper_id} className="border-border space-y-2 border-b p-2">
                      {!cell || !cell.reported ? (
                        <span className="text-muted-foreground">{COMPARE_NOT_REPORTED}</span>
                      ) : (
                        cell.items.map((item, i) => (
                          <div key={i} className="space-y-1">
                            <p>
                              {item.label ? <strong>{item.label}: </strong> : null}
                              {item.text}
                              {item.origin === "ai_inferred" && (
                                <em className="text-muted-foreground"> (AI-inferred)</em>
                              )}
                            </p>
                            {item.evidence.slice(0, 2).map((ev, j) => (
                              <p key={j} className="text-muted-foreground text-xs">
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
                          </div>
                        ))
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3">
        {result.rows.map((row) => (
          <li key={row.dimension} className={`${CARD} space-y-1`}>
            <h4 className="text-foreground text-sm font-medium">{row.label}</h4>
            {row.status === "not_reported" ? (
              <p className="text-muted-foreground text-sm">{COMPARE_NOT_REPORTED}</p>
            ) : (
              <>
                <p className="text-sm">
                  <span className="font-medium">Similarities: </span>
                  {row.similarities.length
                    ? row.similarities.join(", ")
                    : row.status === "partial"
                      ? `None shown: not reported for ${row.not_reported_for.map((id) => title.get(id)).join(", ")}.`
                      : "No shared wording."}
                </p>
                {row.differences.length > 0 && (
                  <p className="text-sm">
                    <span className="font-medium">Differences: </span>
                    {row.differences
                      .map((d) => `${title.get(d.paper_id)}: ${d.terms.join(", ") || "none"}`)
                      .join(" · ")}
                  </p>
                )}
              </>
            )}
            <label className="block text-xs">
              <span className="text-muted-foreground">Your note on {row.label}</span>
              <textarea
                className={`${FIELD} mt-1`}
                rows={2}
                maxLength={5000}
                disabled={readOnly}
                value={notes[row.dimension] ?? ""}
                onChange={(e) => setNotes({ ...notes, [row.dimension]: e.target.value })}
              />
            </label>
          </li>
        ))}
      </ul>
      {!readOnly && (
        <Button size="sm" disabled={busy} onClick={() => void saveNotes()}>
          Save notes
        </Button>
      )}
    </div>
  );
}

export function ComparisonWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const saved = useAsync(() => researchApi.listComparisons(project.id), [project.id]);
  const papers = useAsync(
    () => researchApi.listPapers(project.id, { archived: false, limit: 100 }),
    [project.id],
  );
  const analysed = (papers.data?.data ?? []).filter((p) => p.analysis_status === "analysed");
  const [title, setTitle] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [dims, setDims] = useState<ComparisonDimension[]>(COMPARE_DIMENSIONS.map((d) => d.id));
  const [open, setOpen] = useState<ResearchComparison | null>(null);
  const [removing, setRemoving] = useState<ComparisonSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const canCompare =
    !readOnly && !busy && title.trim().length > 0 && chosen.length >= 2 && dims.length > 0;

  function toggle<T>(list: T[], v: T): T[] {
    return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  }

  async function create() {
    setBusy(true);
    try {
      const made = await researchApi.createComparison(project.id, {
        title: title.trim(),
        paper_ids: chosen,
        dimensions: dims.length === COMPARE_DIMENSIONS.length ? null : dims,
      });
      setOpen(made);
      setTitle("");
      setChosen([]);
      saved.reload();
    } catch (e) {
      toast({ title: "Could not compare", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function openSaved(id: string) {
    try {
      setOpen(await researchApi.getComparison(id));
    } catch (e) {
      toast({ title: "Could not open", description: errorText(e), variant: "destructive" });
    }
  }

  async function remove(target: ComparisonSummary) {
    try {
      await researchApi.deleteComparison(target.id);
      if (open?.id === target.id) setOpen(null);
      saved.reload();
    } catch (e) {
      toast({ title: "Could not delete", description: errorText(e), variant: "destructive" });
    }
  }

  return (
    <section aria-label="Paper comparison" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Compare papers</h2>
      {!readOnly && (
        <div className={`${CARD} space-y-3`}>
          {analysed.length < 2 ? (
            <p className="text-muted-foreground text-sm">
              Comparing needs at least two papers with a completed analysis. Open a paper and run
              its analysis first.
            </p>
          ) : (
            <>
              <label className="block text-sm">
                <span className="text-muted-foreground">Comparison title</span>
                <input
                  className={`${FIELD} mt-1`}
                  maxLength={200}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <fieldset className="space-y-1">
                <legend className="text-sm font-medium">
                  Papers (2 to {MAX_PAPERS}, analysed only)
                </legend>
                {analysed.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={chosen.includes(p.id)}
                      disabled={!chosen.includes(p.id) && chosen.length >= MAX_PAPERS}
                      onChange={() => setChosen(toggle(chosen, p.id))}
                    />
                    {p.title}
                  </label>
                ))}
              </fieldset>
              <fieldset className="space-y-1">
                <legend className="text-sm font-medium">Dimensions</legend>
                <div className="grid gap-1 sm:grid-cols-2">
                  {COMPARE_DIMENSIONS.map((d) => (
                    <label key={d.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={dims.includes(d.id)}
                        onChange={() => setDims(toggle(dims, d.id))}
                      />
                      {d.label}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Button disabled={!canCompare} onClick={() => void create()}>
                Compare papers
              </Button>
            </>
          )}
        </div>
      )}

      <AsyncSection
        title="Saved comparisons"
        loading={saved.loading}
        error={saved.error}
        onRetry={saved.reload}
        isEmpty={(saved.data?.data.length ?? 0) === 0}
        empty={<p className="text-muted-foreground text-sm">No saved comparisons yet.</p>}
      >
        <ul className="space-y-2">
          {saved.data?.data.map((c) => (
            <li key={c.id} className={`${CARD} flex flex-wrap items-center justify-between gap-2`}>
              <span className="text-sm">
                <span className="text-foreground font-medium">{c.title}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · {c.paper_count} papers · {new Date(c.created_at).toLocaleDateString()}
                </span>
              </span>
              <span className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => void openSaved(c.id)}>
                  Open
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive"
                  onClick={() => setRemoving(c)}
                >
                  Delete
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </AsyncSection>

      {open && (
        <Matrix
          key={open.id}
          cmp={open}
          readOnly={readOnly}
          onSaved={(c) => {
            setOpen(c);
            saved.reload();
          }}
        />
      )}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Delete this comparison?"
        description="The saved comparison and your notes on it are deleted. The papers and their analyses are not affected."
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          const target = removing;
          setRemoving(null);
          if (target) void remove(target);
        }}
      />
    </section>
  );
}
