import { ResearchStudio } from "@/features/research/research-studio";

export default function ResearchPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Research Studio</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Organise a research project: its problem, objectives and questions. Papers, evidence and
          drafts are added to projects as those tools arrive. Only you can see your projects.
        </p>
      </div>
      <ResearchStudio />
    </div>
  );
}
