import { ProgressView } from "@/features/revision/progress-view";

export default function ProgressPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Progress</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Your quiz results, flashcard reviews and study streaks. Figures come only from your own
          activity.
        </p>
      </div>
      <ProgressView />
    </div>
  );
}
