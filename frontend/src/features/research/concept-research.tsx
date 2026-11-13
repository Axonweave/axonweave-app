"use client";

import Link from "next/link";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import {
  CONCEPT_LINK_STATUS_LABELS,
  GAP_CATEGORY_LABELS,
  researchApi,
  type ConceptResearch,
} from "@/lib/api/research";

type Claims = ConceptResearch["findings"];

function ClaimList({ title, items }: { title: string; items: Claims }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-muted-foreground text-xs font-medium uppercase">{title}</h4>
      <ul className="mt-1 space-y-1 text-sm">
        {items.map((c, i) => (
          <li key={`${c.paper_id}-${i}`}>
            <Link href={`/research/papers/${c.paper_id}`} className="text-primary hover:underline">
              {c.paper_title}
            </Link>
            : {c.claim_text}
            {c.page_number ? (
              <span className="text-muted-foreground"> (page {c.page_number})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Research connected to a knowledge concept: papers, findings, methods, datasets, metrics, gaps. */
export function ConceptResearchSection({ nodeId }: { nodeId: string }) {
  const research = useAsync(() => researchApi.conceptResearch(nodeId), [nodeId]);
  const data = research.data;
  return (
    <AsyncSection
      title="Research"
      loading={research.loading}
      error={research.error}
      onRetry={research.reload}
      isEmpty={!data || data.papers.length === 0}
      empty={
        <p className="text-muted-foreground text-sm">
          No research papers are linked to this concept. Link papers from a research project.
        </p>
      }
    >
      {data && (
        <div className="space-y-3">
          <div>
            <h4 className="text-muted-foreground text-xs font-medium uppercase">Related papers</h4>
            <ul className="mt-1 space-y-1 text-sm">
              {data.papers.map((p) => (
                <li key={p.link_id}>
                  <Link
                    href={`/research/papers/${p.paper_id}`}
                    className="text-primary hover:underline"
                  >
                    {p.paper_title}
                  </Link>{" "}
                  <span className="text-muted-foreground text-xs">
                    {p.project_title} · {CONCEPT_LINK_STATUS_LABELS[p.link_status] ?? p.link_status}
                  </span>
                </li>
              ))}
            </ul>
            {data.papers.every((p) => p.link_status !== "confirmed") && (
              <p className="text-muted-foreground mt-1 text-xs">
                Confirm a link in the research project to see findings, methods and datasets here.
              </p>
            )}
          </div>
          <ClaimList title="Research findings" items={data.findings} />
          <ClaimList title="Methods" items={data.methods} />
          <ClaimList title="Datasets" items={data.datasets} />
          <ClaimList title="Evaluation metrics" items={data.metrics} />
          {data.gaps.length > 0 && (
            <div>
              <h4 className="text-muted-foreground text-xs font-medium uppercase">
                Candidate research gaps
              </h4>
              <ul className="mt-1 space-y-1 text-sm">
                {data.gaps.map((g) => (
                  <li key={g.id}>
                    {g.title}{" "}
                    <span className="text-muted-foreground text-xs">
                      ({GAP_CATEGORY_LABELS[g.category] ?? g.category})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </AsyncSection>
  );
}
