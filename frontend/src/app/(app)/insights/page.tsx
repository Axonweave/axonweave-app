import { IntelligenceView } from "@/features/knowledge/intelligence-view";

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<{ concept?: string }>;
}) {
  const { concept } = await searchParams;
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Learner Intelligence</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          What you understand, where the gaps are and what to do next, based on your own quiz and
          flashcard results. Concepts with no results are shown as not assessed.
        </p>
      </div>
      <IntelligenceView initialConceptId={concept} />
    </div>
  );
}
