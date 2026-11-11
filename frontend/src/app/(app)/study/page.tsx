import { StudyLibrary } from "@/features/study/study-library";

export default function StudyPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Study materials</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Summaries, flashcards, quizzes, guides, glossaries and formula sheets generated from your
          documents. The text you choose is sent to the AI provider to write them. Only you can see
          them.
        </p>
      </div>
      <StudyLibrary />
    </div>
  );
}
