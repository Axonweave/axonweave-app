"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  CONTRADICTION_CATEGORY_LABELS,
  CONTRADICTION_REVIEW_LABELS,
  researchApi,
  type ResearchContradiction,
  type ResearchProject,
} from "@/lib/api/research";

const CARD = "border-border bg-card rounded-lg border p-4";
const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";

const CONDITION_LABELS: Record<string, string> = {
  dataset: "Dataset",
  metrics: "Evaluation metrics",
  setup: "Experimental setup",
};
const COMPARISON_LABELS: Record<string, string> = {
  same: "Same",
  partly_overlapping: "Partly overlapping",
  different: "Different",
  unknown: "Not described",
};

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

type Side = ResearchContradiction["claim_a"];

function ClaimSide({ title, side }: { title: string; side: Side }) {
  return (
    <div className="border-border space-y-1 rounded-md border p-3 text-sm">
      <p className="text-muted-foreground text-xs font-medium">{title}</p>
      <Link href={`/research/papers/${side.paper_id}`} className="font-medium underline">
        {side.paper_title}
      </Link>
      <p>{side.claim_text}</p>
      {side.quote ? (
        <blockquote className="text-muted-foreground border-l-2 pl-2 text-xs">
          “{side.quote}”{side.page_number ? ` (page ${side.page_number})` : ""}
        </blockquote>
      ) : (
        <p className="text-muted-foreground text-xs">No verified quotation is linked.</p>
      )}
    </div>
  );
}

type Condition = { comparison: string; shared: string[]; only_a: string[]; only_b: string[] };

function ContradictionCard({
  item,
  readOnly,
  onChanged,
}: {
  item: ResearchContradiction;
  readOnly: boolean;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const [text, setText] = useState(item.researcher_explanation ?? "");
  const [busy, setBusy] = useState(false);

  async function act(body: Parameters<typeof researchApi.patchContradiction>[1]) {
    setBusy(true);
    try {
      await researchApi.patchContradiction(item.id, body);
      onChanged();
    } catch (e) {
      toast({ title: "Could not do that", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  const conditions = item.conditions as Record<string, unknown>;
  return (
    <li
      className={`${CARD} space-y-3`}
      aria-label={`${item.claim_a.paper_title} and ${item.claim_b.paper_title}`}
    >
      <div className="flex flex-wrap gap-1 text-xs">
        <span className="bg-muted rounded px-2 py-0.5">
          {CONTRADICTION_CATEGORY_LABELS[item.category] ?? item.category}
        </span>
        <span className="bg-muted rounded px-2 py-0.5">Confidence: {item.confidence_label}</span>
        <span className="bg-muted rounded px-2 py-0.5">
          {CONTRADICTION_REVIEW_LABELS[item.review_status] ?? item.review_status}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <ClaimSide title="Claim A" side={item.claim_a} />
        <ClaimSide title="Claim B" side={item.claim_b} />
      </div>
      <p className="text-sm">{item.explanation}</p>
      <details>
        <summary className="cursor-pointer text-sm font-medium">Compare conditions</summary>
        <table className="mt-2 w-full text-left text-sm">
          <thead>
            <tr className="text-muted-foreground">
              <th className="py-1 pr-2">Condition</th>
              <th className="py-1 pr-2">Comparison</th>
              <th className="py-1">Terms only in A / only in B</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(CONDITION_LABELS).map(([key, label]) => {
              const c = conditions[key] as Condition | undefined;
              if (!c) return null;
              return (
                <tr key={key} className="border-border border-t">
                  <td className="py-1 pr-2">{label}</td>
                  <td className="py-1 pr-2">{COMPARISON_LABELS[c.comparison] ?? c.comparison}</td>
                  <td className="py-1">
                    {c.only_a.join(", ") || "none"} / {c.only_b.join(", ") || "none"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
      {!readOnly && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={() => act({ review_status: "genuine" })}>
              Mark genuine
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => act({ review_status: "context_dependent" })}
            >
              Mark context-dependent
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => act({ review_status: "dismissed" })}
            >
              Dismiss
            </Button>
          </div>
          <label className="block text-sm">
            <span className="text-muted-foreground">Your explanation</span>
            <textarea
              className={FIELD}
              rows={2}
              maxLength={4000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || text === (item.researcher_explanation ?? "")}
            onClick={() => act({ researcher_explanation: text })}
          >
            Save explanation
          </Button>
        </div>
      )}
    </li>
  );
}

export function ContradictionsWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const [category, setCategory] = useState("");
  const [review, setReview] = useState("");
  const [busy, setBusy] = useState(false);
  const list = useAsync(
    () =>
      researchApi.listContradictions(project.id, {
        category: category || undefined,
        review_status: review || undefined,
      }),
    [project.id, category, review],
  );

  async function generate() {
    setBusy(true);
    try {
      const created = await researchApi.generateContradictions(project.id);
      toast({
        title: created.length ? "Candidates updated" : "No new candidates",
        description: "A difference in results is not always a contradiction; check the conditions.",
      });
      list.reload();
    } catch (e) {
      toast({ title: "Could not generate", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Contradictions" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Contradictions</h2>
      <div className={`${CARD} space-y-3`}>
        <p className="text-muted-foreground text-sm">
          Pairs of findings from different analysed papers that point in opposite directions on the
          same topic. Each pair is checked against the papers’ datasets, metrics and setups before
          it is labelled.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          {!readOnly && (
            <Button disabled={busy} onClick={generate}>
              {busy ? "Looking…" : "Find contradictions"}
            </Button>
          )}
          <label className="text-sm">
            <span className="text-muted-foreground block">Type</span>
            <select
              className={SELECT}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">All</option>
              {Object.entries(CONTRADICTION_CATEGORY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-muted-foreground block">Review</span>
            <select className={SELECT} value={review} onChange={(e) => setReview(e.target.value)}>
              <option value="">All</option>
              {Object.entries(CONTRADICTION_REVIEW_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <AsyncSection
        title="Contradiction candidates"
        loading={list.loading}
        error={list.error}
        onRetry={list.reload}
        isEmpty={!list.data || list.data.data.length === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No contradiction candidates. Analyse at least two papers, then search.
          </p>
        }
      >
        <ul className="space-y-3">
          {(list.data?.data ?? []).map((c) => (
            <ContradictionCard key={c.id} item={c} readOnly={readOnly} onChanged={list.reload} />
          ))}
        </ul>
      </AsyncSection>
    </section>
  );
}
