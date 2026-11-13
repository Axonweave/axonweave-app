import { KnowledgeExplorer } from "@/features/knowledge/knowledge-explorer";

export default function KnowledgePage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Knowledge Graph</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          The concepts in your materials and how they connect, each linked back to the passage it
          came from. Only you can see this.
        </p>
      </div>
      <KnowledgeExplorer />
    </div>
  );
}
