"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  ANALYSIS_LABELS,
  ANALYSIS_SECTIONS,
  NOT_REPORTED,
  RUN_STATUS_LABELS,
  SOURCE_LABELS,
  researchApi,
  type AnalysisClaim,
  type AnalysisRun,
  type PaperNote,
  type ResearchPaper,
  type SectionId,
} from "@/lib/api/research";

const CARD = "border-border bg-card rounded-lg border p-4";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";
const POLL_MS = 3000;

type TabId = "overview" | SectionId | "evidence";

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

function ClaimCard({ claim }: { claim: AnalysisClaim }) {
  const inferred = claim.origin === "ai_inferred";
  return (
    <li className={`${CARD} space-y-2`}>
      <div className="flex flex-wrap items-center gap-2">
        {claim.label && <span className="text-foreground text-sm font-medium">{claim.label}</span>}
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${inferred ? "bg-amber-100 text-amber-900" : "bg-muted"}`}
        >
          {inferred ? "AI-inferred, not stated by the authors" : "Stated in the paper"}
        </span>
        {claim.confidence !== null && (
          <span className="text-muted-foreground text-xs">
            Support {Math.round(claim.confidence * 100)}%
          </span>
        )}
      </div>
      <p className="text-foreground text-sm">{claim.text}</p>
      <ul className="space-y-1">
        {claim.evidence.map((ev) => (
          <li key={ev.id} className="border-border border-l-2 pl-3 text-xs">
            <q className="text-muted-foreground">{ev.quote}</q>
            <span className="text-muted-foreground">
              {ev.page_number ? ` · page ${ev.page_number}` : ""}
            </span>
            {ev.document_id && (
              <Link
                className="text-primary ml-2 underline"
                href={`/documents/${ev.document_id}${ev.page_number ? `?page=${ev.page_number}` : ""}`}
              >
                Open original{ev.page_number ? ` at page ${ev.page_number}` : ""}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </li>
  );
}

function Notes({
  paperId,
  section,
  notes,
  disabled,
  onChanged,
}: {
  paperId: string;
  section: SectionId | null;
  notes: PaperNote[];
  disabled: boolean;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const [text, setText] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const mine = notes.filter((n) => n.section === section);

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      onChanged();
    } catch (e) {
      toast({
        title: "Could not save the note",
        description: errorText(e),
        variant: "destructive",
      });
    }
  }

  return (
    <section aria-label="Your notes" className="space-y-2 pt-2">
      <h3 className="text-foreground text-sm font-medium">Your notes</h3>
      <p className="text-muted-foreground text-xs">
        Notes are yours. Running the analysis again never changes or removes them.
      </p>
      <ul className="space-y-2">
        {mine.map((n) => (
          <li key={n.id} className={CARD}>
            {editing === n.id ? (
              <div className="space-y-2">
                <textarea
                  className={FIELD}
                  aria-label="Edit note"
                  rows={3}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!draft.trim()}
                    onClick={() =>
                      void run(async () => {
                        await researchApi.editNote(n.id, draft);
                        setEditing(null);
                      })
                    }
                  >
                    Save note
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-foreground text-sm whitespace-pre-wrap">{n.body}</p>
                <div className="flex gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditing(n.id);
                      setDraft(n.body);
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => void run(() => researchApi.deleteNote(n.id))}
                  >
                    Delete note
                  </Button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      {!disabled && (
        <div className="space-y-2">
          <textarea
            className={FIELD}
            aria-label="New note"
            rows={2}
            maxLength={5000}
            placeholder="Add a note"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!text.trim()}
            onClick={() =>
              void run(async () => {
                await researchApi.addNote(paperId, { section, body: text });
                setText("");
              })
            }
          >
            Add note
          </Button>
        </div>
      )}
    </section>
  );
}

function RunInfo({ run }: { run: AnalysisRun }) {
  const stats = (run.result_stats ?? {}) as Record<string, number>;
  return (
    <p className="text-muted-foreground text-xs">
      Version {run.version_number}
      {run.completed_at ? ` · ${new Date(run.completed_at).toLocaleString()}` : ""}
      {run.model_identifier ? ` · model ${run.model_identifier}` : ""}
      {typeof stats.claims === "number" ? ` · ${stats.claims} confirmed claims` : ""}
      {stats.dropped ? ` · ${stats.dropped} dropped because they could not be confirmed` : ""}
    </p>
  );
}

export function PaperAnalysisView({ paperId }: { paperId: string }) {
  const { toast } = useToast();
  const [tab, setTab] = useState<TabId>("overview");
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const paper = useAsync<ResearchPaper>(() => researchApi.getPaper(paperId), [paperId]);
  const analysis = useAsync(() => researchApi.analysis(paperId, version), [paperId, version]);
  const history = useAsync(() => researchApi.analysisHistory(paperId), [paperId]);
  const notes = useAsync(() => researchApi.listNotes(paperId), [paperId]);

  const active = analysis.data?.active ?? null;
  const activeId = active?.id;
  const { reload: reloadAnalysis } = analysis;
  const { reload: reloadHistory } = history;
  const { reload: reloadPaper } = paper;

  // Poll while a run is in progress; one final reload picks up the finished result.
  useEffect(() => {
    if (!activeId) return;
    const timer = setInterval(() => {
      reloadAnalysis();
      reloadHistory();
      reloadPaper();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [activeId, reloadAnalysis, reloadHistory, reloadPaper]);

  function refresh() {
    reloadAnalysis();
    reloadHistory();
    reloadPaper();
  }

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      refresh();
    } catch (e) {
      toast({ title: "Could not do that", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  const p = paper.data;
  const data = analysis.data;
  const archived = p?.archived_at != null;
  const canRun = !!p && !!p.document_id && !archived && !active;
  const latest = history.data?.data[0];
  const failedLatest =
    latest &&
    latest.status === "failed" &&
    (!data?.run || latest.version_number > data.run.version_number)
      ? latest
      : null;
  const sections = data?.sections ?? [];
  const current = sections.find((s) => s.section === tab);
  const totalClaims = sections.reduce((n, s) => n + s.items.length, 0);

  return (
    <div className="space-y-4">
      <AsyncSection
        title="Paper"
        loading={paper.loading && !p}
        error={paper.error}
        onRetry={paper.reload}
        isEmpty={!p}
        empty={<p className="text-sm">Paper not found.</p>}
        action={
          p ? (
            <Link className="text-primary text-sm underline" href="/research">
              Back to Research Studio
            </Link>
          ) : null
        }
      >
        {p && (
          <div className={`${CARD} space-y-1`}>
            <h2 className="text-foreground text-lg font-semibold">{p.title}</h2>
            <p className="text-muted-foreground text-sm">
              {p.authors.length ? p.authors.join(", ") : "Authors not entered"}
              {p.publication_year ? ` · ${p.publication_year}` : ""}
              {p.venue ? ` · ${p.venue}` : ""}
            </p>
            <p className="text-muted-foreground text-xs">
              {p.doi ? `DOI ${p.doi} · ` : ""}
              {SOURCE_LABELS[p.metadata_source] ?? p.metadata_source}
              {p.metadata_verified ? " · verified by you" : " · not yet verified"}
              {" · "}
              {ANALYSIS_LABELS[p.analysis_status] ?? p.analysis_status}
            </p>
            <p className="text-xs">
              {p.document_id ? `File: ${p.document_name ?? "document"}` : "No file attached"}
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <Button
                disabled={!canRun || busy}
                onClick={() => void act(() => researchApi.startAnalysis(paperId))}
              >
                {data?.run ? "Analyse again" : "Analyse paper"}
              </Button>
              {!p.document_id && (
                <span className="text-muted-foreground text-xs">
                  Attach a PDF to this paper to analyse it.
                </span>
              )}
              {archived && (
                <span className="text-muted-foreground text-xs">
                  Restore this paper to analyse it.
                </span>
              )}
            </div>
          </div>
        )}
      </AsyncSection>

      {active && (
        <div className={`${CARD} space-y-2`} role="status" aria-live="polite">
          <p className="text-foreground text-sm font-medium">
            {RUN_STATUS_LABELS[active.status] ?? active.status}… {active.progress}%
          </p>
          <progress className="w-full" max={100} value={active.progress} aria-label="Progress" />
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void act(() => researchApi.cancelAnalysis(paperId, active.id))}
          >
            Cancel analysis
          </Button>
        </div>
      )}

      {failedLatest && (
        <div className={`${CARD} text-sm`} role="alert">
          The latest analysis (version {failedLatest.version_number}) did not finish:{" "}
          {failedLatest.error_message ?? "it failed."}
          {data?.run ? " The earlier result below is unchanged." : ""}
        </div>
      )}

      <AsyncSection
        title="Analysis"
        loading={analysis.loading && !data}
        error={analysis.error}
        onRetry={analysis.reload}
        isEmpty={!data?.run}
        empty={
          <p className="text-muted-foreground text-sm">
            This paper has not been analysed yet. The analysis reads the attached file and lists
            what the paper reports, each item with the quotation that supports it. Anything the
            paper does not report is left empty.
          </p>
        }
        action={
          (history.data?.data.filter((r) => r.status === "completed").length ?? 0) > 1 ? (
            <select
              className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              aria-label="Analysis version"
              value={version ?? ""}
              onChange={(e) => setVersion(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">Latest</option>
              {history.data?.data
                .filter((r) => r.status === "completed")
                .map((r) => (
                  <option key={r.id} value={r.version_number}>
                    Version {r.version_number}
                  </option>
                ))}
            </select>
          ) : null
        }
      >
        {data?.run && (
          <div className="space-y-3">
            <RunInfo run={data.run} />
            <p className="text-muted-foreground text-xs">
              Generated by AI from the attached file. Each item is shown only when its quotation was
              found in the paper; check the quotations against the original.
            </p>
            <div role="tablist" aria-label="Analysis sections" className="flex flex-wrap gap-1">
              {(
                [
                  { id: "overview", label: "Overview" },
                  ...ANALYSIS_SECTIONS,
                  { id: "evidence", label: "Evidence" },
                ] as { id: TabId; label: string }[]
              ).map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  type="button"
                  aria-selected={tab === t.id}
                  className={`rounded-md px-3 py-1.5 text-sm ${tab === t.id ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div role="tabpanel" className="space-y-3">
              {tab === "overview" && (
                <>
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {ANALYSIS_SECTIONS.map((s) => {
                      const count = sections.find((x) => x.section === s.id)?.items.length ?? 0;
                      return (
                        <li key={s.id} className={`${CARD} flex items-center justify-between`}>
                          <button
                            type="button"
                            className="text-primary text-sm underline"
                            onClick={() => setTab(s.id)}
                          >
                            {s.label}
                          </button>
                          <span className="text-muted-foreground text-xs">
                            {count ? `${count} item${count === 1 ? "" : "s"}` : NOT_REPORTED}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  {totalClaims === 0 && <p className="text-sm">{NOT_REPORTED}</p>}
                </>
              )}

              {current && (
                <>
                  {current.items.length === 0 ? (
                    <p className="text-muted-foreground text-sm">{NOT_REPORTED}</p>
                  ) : (
                    <ul className="space-y-3">
                      {current.items.map((c) => (
                        <ClaimCard key={`${current.section}-${c.index}`} claim={c} />
                      ))}
                    </ul>
                  )}
                </>
              )}

              {tab === "evidence" && (
                <ul className="space-y-2">
                  {sections.flatMap((s) =>
                    s.items.flatMap((c) =>
                      c.evidence.map((ev) => (
                        <li key={ev.id} className={`${CARD} space-y-1 text-sm`}>
                          <p className="text-muted-foreground text-xs">
                            {ANALYSIS_SECTIONS.find((x) => x.id === s.section)?.label}
                            {c.label ? ` · ${c.label}` : ""}
                          </p>
                          <p className="text-foreground">{c.text}</p>
                          <q className="text-muted-foreground text-xs">{ev.quote}</q>
                          {ev.document_id && (
                            <Link
                              className="text-primary block text-xs underline"
                              href={`/documents/${ev.document_id}${ev.page_number ? `?page=${ev.page_number}` : ""}`}
                            >
                              Open original{ev.page_number ? ` at page ${ev.page_number}` : ""}
                            </Link>
                          )}
                        </li>
                      )),
                    ),
                  )}
                  {totalClaims === 0 && <li className="text-sm">{NOT_REPORTED}</li>}
                </ul>
              )}

              {tab !== "evidence" && (
                <Notes
                  paperId={paperId}
                  section={tab === "overview" ? null : tab}
                  notes={notes.data ?? []}
                  disabled={archived}
                  onChanged={notes.reload}
                />
              )}
            </div>
          </div>
        )}
      </AsyncSection>
    </div>
  );
}
