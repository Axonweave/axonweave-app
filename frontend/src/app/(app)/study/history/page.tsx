import { QuizHistory } from "@/features/study/quiz-history";

export default function QuizHistoryPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Quiz history</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Every quiz attempt you have made. Pick two submitted attempts of the same quiz to see how
          your answers changed.
        </p>
      </div>
      <QuizHistory />
    </div>
  );
}
