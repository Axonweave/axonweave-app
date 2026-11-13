"use client";

import Link from "next/link";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { CONCEPT_LINK_STATUS_LABELS, researchApi } from "@/lib/api/research";

/** Knowledge graph concepts related to one paper (suggested and confirmed links). */
export function PaperConcepts({ paperId }: { paperId: string }) {
  const links = useAsync(() => researchApi.paperConcepts(paperId), [paperId]);
  const items = links.data ?? [];
  return (
    <AsyncSection
      title="Related concepts"
      loading={links.loading}
      error={links.error}
      onRetry={links.reload}
      isEmpty={items.length === 0}
      empty={
        <p className="text-muted-foreground text-sm">
          No concepts are linked to this paper yet. Use “Find concept links” in the research
          project.
        </p>
      }
    >
      <ul className="space-y-2">
        {items.map((l) => (
          <li key={l.id} className="border-border bg-card rounded-lg border p-3 text-sm">
            <Link href={`/knowledge?node=${l.node.id}`} className="font-medium underline">
              {l.node.name}
            </Link>{" "}
            <span className="text-muted-foreground text-xs">
              ({CONCEPT_LINK_STATUS_LABELS[l.link_status] ?? l.link_status})
            </span>
            <p className="text-muted-foreground mt-1 text-xs">{l.claim_text}</p>
          </li>
        ))}
      </ul>
    </AsyncSection>
  );
}
