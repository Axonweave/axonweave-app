"use client";

import { useParams } from "next/navigation";
import { PaperAnalysisView } from "@/features/research/paper-analysis";
import { PaperConcepts } from "@/features/research/paper-concepts";

export default function PaperPage() {
  const { paperId } = useParams<{ paperId: string }>();
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Paper analysis</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          What this paper reports, section by section, with the quotation behind every item. Only
          you can see your papers and notes.
        </p>
      </div>
      <PaperAnalysisView paperId={paperId} />
      <PaperConcepts paperId={paperId} />
    </div>
  );
}
