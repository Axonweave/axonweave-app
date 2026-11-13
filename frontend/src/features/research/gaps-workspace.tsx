"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  GAP_CATEGORY_LABELS,
  GAP_CONFIDENCE_LABELS,
  GAP_STATUS_LABELS,
  researchApi,
  type ResearchGap,
  type ResearchProject,
} from "@/lib/api/research";

const CARD = "border-border bg-card rounded-lg border p-4";
const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

function GapCard({
  gap,
  titles,
  readOnly,
  onChanged,
}: {
  gap: ResearchGap;
  titles: Record<string, string>;
  readOnly: boolean;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const [notes, setNotes] = useState(gap.researcher_notes ?? "");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const supporting = gap.evidence.filter((e) => e.evidence_role === "supporting");
  const counter = gap.evidence.filter((e) => e.evidence_role === "counter_evidence");

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (e) {
      toast({ title: "Could not do that", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  const setStatus = (status: "accepted" | "rejected" | "investigating" | "suggested") =>
    act(() => researchApi.patchGap(gap.id, { validation_status: status }));

  return (
    <li className={`${CARD} space-y-3`} aria-label={gap.title}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-foreground font-medium">{gap.title}</h3>
        <div className="flex flex-wrap gap-1 text-xs">
          <span className="bg-muted rounded px-2 py-0.5">
            {GAP_CATEGORY_LABELS[gap.category] ?? gap.category}
          </span>
          <span className="bg-muted rounded px-2 py-0.5">
            {GAP_CONFIDENCE_LABELS[gap.confidence_label] ?? gap.confidence_label}
          </span>
          <span className="bg-muted rounded px-2 py-0.5">
            {GAP_STATUS_LABELS[gap.validation_status] ?? gap.validation_status}
          </span>
        </div>
      </div>
      <p className="text-sm">{gap.description}</p>
      <p className="text-muted-foreground text-sm">{gap.rationale}</p>
      <p className="text-sm">
        <span className="font-medium">Suggested direction: </span>
        {gap.suggested_direction}
      </p>
      <p className="text-muted-foreground text-xs">{gap.limitations}</p>

      <details>
        <summary className="cursor-pointer text-sm font-medium">
          Supporting evidence ({supporting.length})
        </summary>
        <ul className="mt-2 space-y-1 text-sm">
          {supporting.map((e) => (
            <li key={e.id}>
              <span className="text-muted-foreground">
                {titles[e.research_paper_id] ?? "Paper"} ({e.claim_type}):{" "}
              </span>
              {e.claim_text}
            </li>
          ))}
        </ul>
      </details>
      <details open={counter.length > 0}>
        <summary className="cursor-pointer text-sm font-medium">
          Counter-evidence ({counter.length})
        </summary>
        {counter.length === 0 ? (
          <p className="text-muted-foreground mt-2 text-sm">
            None found among the analysed papers.
          </p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm">
            {counter.map((e) => (
              <li key={e.id}>
                <span className="text-muted-foreground">
                  {titles[e.research_paper_id] ?? "Paper"} ({e.claim_type}):{" "}
                </span>
                {e.claim_text}
              </li>
            ))}
          </ul>
        )}
      </details>

      {!readOnly && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={() => setStatus("accepted")}>
              Accept
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => setStatus("investigating")}
            >
              Investigating
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => setStatus("rejected")}
            >
              Reject
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </Button>
          </div>
          <label className="block text-sm">
            <span className="text-muted-foreground">Your notes</span>
            <textarea
              className={FIELD}
              rows={2}
              value={notes}
              maxLength={4000}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || notes === (gap.researcher_notes ?? "")}
            onClick={() => act(() => researchApi.patchGap(gap.id, { researcher_notes: notes }))}
          >
            Save notes
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={confirmDelete}
        title="Delete this gap?"
        description="The gap and its evidence links are removed. The papers are not affected."
        confirmLabel="Delete"
        destructive
        onOpenChange={setConfirmDelete}
        onConfirm={() => {
          setConfirmDelete(false);
          void act(() => researchApi.deleteGap(gap.id));
        }}
      />
    </li>
  );
}

export function GapsWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const gaps = useAsync(
    () =>
      researchApi.listGaps(project.id, {
        category: category || undefined,
        status: status || undefined,
      }),
    [project.id, category, status],
  );
  const papers = useAsync(
    () => researchApi.listPapers(project.id, { archived: false, limit: 100 }),
    [project.id],
  );
  const titles = Object.fromEntries((papers.data?.data ?? []).map((p) => [p.id, p.title]));

  async function generate() {
    setBusy(true);
    try {
      const created = await researchApi.generateGaps(project.id);
      toast({
        title: created.length ? "Gap candidates updated" : "No new gap candidates",
        description:
          "Candidates describe only the analysed papers in this project, not all research.",
      });
      gaps.reload();
    } catch (e) {
      toast({ title: "Could not generate", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Research gaps" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Research gaps</h2>
      <div className={`${CARD} space-y-3`}>
        <p className="text-muted-foreground text-sm">
          Candidates are built from limitations and future-work statements in the papers you have
          analysed. They are suggestions to review, not proof that nothing has been done.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          {!readOnly && (
            <Button disabled={busy} onClick={generate}>
              {busy ? "Generating…" : "Generate gap candidates"}
            </Button>
          )}
          <label className="text-sm">
            <span className="text-muted-foreground block">Category</span>
            <select
              className={SELECT}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">All</option>
              {Object.entries(GAP_CATEGORY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-muted-foreground block">Status</span>
            <select className={SELECT} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              {Object.entries(GAP_STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <AsyncSection
        title="Gap candidates"
        loading={gaps.loading}
        error={gaps.error}
        onRetry={gaps.reload}
        isEmpty={!gaps.data || gaps.data.data.length === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No gap candidates yet. Analyse papers, then generate candidates.
          </p>
        }
      >
        <ul className="space-y-3">
          {(gaps.data?.data ?? []).map((g) => (
            <GapCard
              key={g.id}
              gap={g}
              titles={titles}
              readOnly={readOnly}
              onChanged={gaps.reload}
            />
          ))}
        </ul>
      </AsyncSection>
    </section>
  );
}
