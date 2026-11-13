"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  CONCEPT_LINK_STATUS_LABELS,
  researchApi,
  type ConceptLink,
  type ConceptLinkStatus,
  type ResearchProject,
} from "@/lib/api/research";

const CARD = "border-border bg-card rounded-lg border p-4";
const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

export function ConceptLinksWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const list = useAsync(
    () => researchApi.listConceptLinks(project.id, { link_status: status || undefined }),
    [project.id, status],
  );

  async function run(job: () => Promise<unknown>, failure: string, done?: string) {
    setBusy(true);
    try {
      await job();
      if (done) toast({ title: done });
      list.reload();
    } catch (e) {
      toast({ title: failure, description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  const review = (l: ConceptLink, next: ConceptLinkStatus) =>
    run(() => researchApi.reviewConceptLink(l.id, next), "Could not update the link");

  const items = list.data?.data ?? [];
  return (
    <section aria-label="Knowledge graph links" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Knowledge graph links</h2>
      <div className={`${CARD} space-y-3`}>
        <p className="text-muted-foreground text-sm">
          Connects your analysed papers to concepts that are already in your knowledge graph, using
          the concept names and aliases that appear in each paper&apos;s verified claims. Nothing is
          added to the graph, and reading a paper does not change your mastery.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          {!readOnly && (
            <Button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const made = await researchApi.suggestConceptLinks(project.id);
                  toast({
                    title: made.length
                      ? `${made.length} new link(s) suggested`
                      : "No new links found",
                  });
                }, "Could not find links")
              }
            >
              {busy ? "Looking…" : "Find concept links"}
            </Button>
          )}
          <label className="text-sm">
            <span className="text-muted-foreground block">Status</span>
            <select className={SELECT} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              {Object.entries(CONCEPT_LINK_STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <AsyncSection
        title="Paper–concept links"
        loading={list.loading}
        error={list.error}
        onRetry={list.reload}
        isEmpty={items.length === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No links yet. Analyse papers and add concepts to your knowledge graph, then search.
          </p>
        }
      >
        <ul className="space-y-3">
          {items.map((l) => (
            <li
              key={l.id}
              className={`${CARD} space-y-2`}
              aria-label={`${l.paper.title} and ${l.node.name}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm">
                  <Link href={`/research/papers/${l.paper.id}`} className="font-medium underline">
                    {l.paper.title}
                  </Link>{" "}
                  mentions{" "}
                  <Link href={`/knowledge?node=${l.node.id}`} className="font-medium underline">
                    {l.node.name}
                  </Link>
                </p>
                <span className="bg-muted rounded px-2 py-0.5 text-xs">
                  {CONCEPT_LINK_STATUS_LABELS[l.link_status] ?? l.link_status}
                </span>
              </div>
              <p className="text-muted-foreground text-xs">
                Matched {l.match_kind === "alias" ? "alias" : "name"} “{l.matched_text}” in{" "}
                {l.mention_count} claim(s). First: {l.claim_text}
                {l.page_number ? ` (page ${l.page_number})` : ""}
              </p>
              {!readOnly && (
                <div className="flex flex-wrap gap-2">
                  {l.link_status !== "confirmed" && (
                    <Button size="sm" disabled={busy} onClick={() => review(l, "confirmed")}>
                      Confirm
                    </Button>
                  )}
                  {l.link_status !== "rejected" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => review(l, "rejected")}
                    >
                      Reject
                    </Button>
                  )}
                  {l.link_status !== "suggested" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => review(l, "suggested")}
                    >
                      Undo
                    </Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      </AsyncSection>
    </section>
  );
}
