"use client";

import Link from "next/link";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { buttonVariants } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { studyApi, type QuizResult } from "@/lib/api/study";
import { formatClock } from "./quiz-taker";
import { SourceRefs } from "./sources";
import { Chip } from "./ui-bits";

type ResultQuestion = QuizResult["questions"][number];

const show = (v: ResultQuestion["submitted_answer"]) =>
  Array.isArray(v) ? v.join(", ") : (v ?? "");

function optionText(q: ResultQuestion, ids: string[] | string | null): string {
  const list = Array.isArray(ids) ? ids : ids ? [ids] : [];
  return list.map((id) => q.options.find((o) => o.id === id)?.text ?? id).join("; ");
}

/**
 * Results and review. Correct answers and explanations come from the results route, which the
 * server only answers for a submitted attempt (D-94). A quiz score is not a measure of mastery.
 */
export function QuizResults({ materialId, attemptId }: { materialId: string; attemptId: string }) {
  const res = useAsync(async () => {
    const material = await studyApi.get(materialId);
    if (!material.item_id) throw new Error("no quiz");
    return { quizId: material.item_id, result: await studyApi.result(material.item_id, attemptId) };
  }, [materialId, attemptId]);

  if (res.loading) return <LoadingSpinner />;
  if (res.error || !res.data)
    return (
      <ErrorDisplay
        title="Results unavailable"
        message="These results could not be loaded."
        onRetry={res.reload}
      />
    );
  const r = res.data.result;
  const choice = (q: ResultQuestion) =>
    ["multiple_choice", "multiple_select", "true_false"].includes(q.question_type);
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Quiz results</h1>
        <p className="text-3xl font-semibold" data-testid="quiz-score">
          {r.percentage !== null && r.percentage !== undefined
            ? `${Math.round(r.percentage)}%`
            : "Self-assessed"}
        </p>
        <dl className="text-muted-foreground grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          <div>
            <dt className="inline">Score: </dt>
            <dd className="inline">
              {r.score} of {r.graded_questions}
            </dd>
          </div>
          <div>
            <dt className="inline">Correct: </dt>
            <dd className="inline">{r.correct}</dd>
          </div>
          <div>
            <dt className="inline">Incorrect: </dt>
            <dd className="inline">{r.incorrect}</dd>
          </div>
          <div>
            <dt className="inline">Unanswered: </dt>
            <dd className="inline">{r.unanswered}</dd>
          </div>
          <div>
            <dt className="inline">Not graded: </dt>
            <dd className="inline">{r.not_graded}</dd>
          </div>
          <div>
            <dt className="inline">Time taken: </dt>
            <dd className="inline">{formatClock(r.time_taken_seconds)}</dd>
          </div>
        </dl>
        {r.auto_submitted ? (
          <p role="status" className="text-sm text-amber-700 dark:text-amber-400">
            Time ran out, so this attempt was submitted automatically with the answers you had
            saved.
          </p>
        ) : null}
        <p className="text-muted-foreground text-sm">{r.note}</p>
      </header>

      <ol className="space-y-4">
        {r.questions.map((q, i) => (
          <li key={q.id} className="border-border space-y-2 rounded-lg border p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground text-sm">Question {i + 1}</span>
              {q.grading === "self_assessment" ? (
                <Chip>Compare with the model answer</Chip>
              ) : !q.answered ? (
                <Chip>Unanswered</Chip>
              ) : q.is_correct ? (
                <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-900 dark:bg-green-950 dark:text-green-200">
                  Correct
                </span>
              ) : (
                <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-900 dark:bg-red-950 dark:text-red-200">
                  Incorrect
                </span>
              )}
            </div>
            <p className="font-medium break-words whitespace-pre-wrap">{q.question}</p>
            <p className="text-sm">
              <span className="font-medium">Your answer: </span>
              {q.answered
                ? choice(q)
                  ? optionText(q, q.submitted_answer as string[])
                  : show(q.submitted_answer)
                : "No answer"}
            </p>
            <p className="text-sm">
              <span className="font-medium">
                {q.grading === "self_assessment" ? "Model answer: " : "Correct answer: "}
              </span>
              {choice(q) ? optionText(q, q.correct_answers) : q.correct_answers.join(" / ")}
            </p>
            {q.rubric.length > 0 ? (
              <div className="text-sm">
                <p className="font-medium">Points to check yourself against:</p>
                <ul className="list-disc pl-6">
                  {q.rubric.map((p, j) => (
                    <li key={j}>{p}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {q.explanation ? (
              <p className="text-muted-foreground text-sm break-words">{q.explanation}</p>
            ) : null}
            <SourceRefs
              refs={(q.source_references as { rank: number }[]).map((s) => s.rank)}
              sources={q.source_references as never}
            />
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Link className={buttonVariants({ variant: "outline" })} href={`/study/${materialId}`}>
          Back to the quiz
        </Link>
        <Link className={buttonVariants({ variant: "default" })} href={`/study/${materialId}/quiz`}>
          Retake quiz
        </Link>
      </div>
    </div>
  );
}
