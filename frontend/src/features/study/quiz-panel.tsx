"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { formatDateTime } from "@/lib/activity";
import { studyApi, type StudyMaterial } from "@/lib/api/study";
import { Chip } from "./ui-bits";

/** Quiz materials show the quiz facts and attempt history. No questions or answers appear here. */
export function QuizPanel({ material }: { material: StudyMaterial }) {
  const quizId = material.item_id ?? null;
  const quiz = useAsync(() => (quizId ? studyApi.quiz(quizId) : Promise.resolve(null)), [quizId]);
  const attempts = useAsync(
    () => (quizId ? studyApi.attempts(quizId) : Promise.resolve([])),
    [quizId],
  );
  if (!quizId) return <p className="text-muted-foreground text-sm">This quiz is not available.</p>;

  const q = quiz.data;
  const list = attempts.data ?? [];
  const open = list.find((a) => a.status === "in_progress");
  return (
    <div className="space-y-5">
      {q ? (
        <div className="space-y-2">
          {q.description ? <p className="text-sm break-words">{q.description}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Chip>{q.question_count} questions</Chip>
            <Chip>
              {q.time_limit_seconds
                ? `${Math.round(q.time_limit_seconds / 60)} minute limit`
                : "No time limit"}
            </Chip>
            {q.randomize_order ? <Chip>Random order</Chip> : null}
          </div>
        </div>
      ) : null}
      <Link className={buttonVariants({ variant: "default" })} href={`/study/${material.id}/quiz`}>
        {open ? "Resume attempt" : list.length > 0 ? "Retake quiz" : "Start quiz"}
      </Link>
      <section aria-labelledby="attempts-h" className="space-y-2">
        <h2 id="attempts-h" className="text-lg font-semibold">
          Attempt history
        </h2>
        {list.length === 0 ? (
          <p className="text-muted-foreground text-sm">No attempts yet.</p>
        ) : (
          <ul className="divide-border border-border divide-y rounded-lg border">
            {list.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
                <span>{formatDateTime(a.started_at)}</span>
                {a.status === "in_progress" ? (
                  <Chip>In progress</Chip>
                ) : (
                  <>
                    <span className="font-medium">
                      {a.percentage !== null && a.percentage !== undefined
                        ? `${Math.round(a.percentage)}% (${a.score} of ${a.graded_questions})`
                        : "Self-assessed questions only"}
                    </span>
                    {a.auto_submitted ? <Chip>Auto-submitted when time ran out</Chip> : null}
                    <Link
                      className="text-primary underline underline-offset-2"
                      href={`/study/${material.id}/quiz/results/${a.id}`}
                    >
                      View results
                    </Link>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
