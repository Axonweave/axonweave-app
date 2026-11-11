"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Flag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorDisplay } from "@/components/ui/error-display";
import { LoadingSpinner } from "@/components/ui/loading";
import { ApiRequestError } from "@/lib/api/client";
import { studyApi, type QuizAttempt, type QuizQuestion } from "@/lib/api/study";
import { Textarea } from "./ui-bits";

type AnswerValue = string[] | string;

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export const isAnswered = (v: AnswerValue | undefined) =>
  Array.isArray(v) ? v.length > 0 : Boolean(v && v.trim());

const SAVE_DELAY_MS = 700;

/**
 * Quiz-taking screen. The questions carry no answer key (D-94). The deadline is the server's:
 * every response says how many seconds remain, and the countdown only displays that. When it
 * reaches zero the attempt is submitted; the server finalises an expired attempt itself, so a
 * closed tab or a skewed clock cannot extend the time.
 */
export function QuizTaker({ materialId }: { materialId: string }) {
  const router = useRouter();
  const routerRef = useRef(router);
  useEffect(() => {
    routerRef.current = router;
  });
  const [quizId, setQuizId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<QuizAttempt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [flagged, setFlagged] = useState<string[]>([]);
  const [current, setCurrent] = useState(0);
  const [save, setSave] = useState<"saved" | "saving" | "error">("saved");
  const [remaining, setRemaining] = useState<number | null>(null);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const deadline = useRef<number | null>(null); // performance.now() value at which time is up
  // Latest values, read at save time so a debounced save never uses stale render state.
  const answersRef = useRef<Record<string, AnswerValue>>({});
  const flaggedRef = useRef<string[]>([]);
  const dirty = useRef<Set<string>>(new Set());
  const flagsDirty = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const finished = useRef(false);

  const syncClock = useCallback((a: QuizAttempt) => {
    deadline.current =
      a.seconds_remaining === null || a.seconds_remaining === undefined
        ? null
        : performance.now() + a.seconds_remaining * 1000;
    setRemaining(a.seconds_remaining ?? null);
  }, []);

  // Start (or resume) the attempt. The server returns the open attempt after a refresh.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const material = await studyApi.get(materialId);
        if (!material.item_id) throw new Error("no quiz");
        const started = await studyApi.startAttempt(material.item_id);
        if (cancelled) return;
        if (started.status === "submitted") {
          routerRef.current.replace(`/study/${materialId}/quiz/results/${started.id}`);
          return;
        }
        setQuizId(material.item_id);
        setAttempt(started);
        answersRef.current = started.answers as Record<string, AnswerValue>;
        flaggedRef.current = started.flagged;
        setAnswers(answersRef.current);
        setFlagged(started.flagged);
        syncClock(started);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof ApiRequestError && err.code === "QUIZ_ATTEMPT_LIMIT"
              ? "You have reached the attempt limit for this quiz."
              : "This quiz could not be started.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [materialId, syncClock]);

  const submit = useCallback(
    async (auto: boolean) => {
      if (!attempt || !quizId || finished.current) return;
      finished.current = true;
      setSubmitting(true);
      window.clearTimeout(timer.current);
      try {
        const final: { question_id: string; answer: AnswerValue }[] = Object.entries(
          answersRef.current,
        ).map(([question_id, answer]) => ({ question_id, answer }));
        await studyApi.submit(quizId, attempt.id, final);
      } catch (err) {
        // Already submitted or expired: the server has the final state; go and read it.
        if (!(err instanceof ApiRequestError) || err.status >= 500) {
          finished.current = false;
          setSubmitting(false);
          setError(
            auto
              ? "Time is up, but submitting failed. Try again."
              : "Submitting failed. Try again.",
          );
          return;
        }
      }
      routerRef.current.push(`/study/${materialId}/quiz/results/${attempt.id}`);
    },
    [attempt, quizId, materialId],
  );

  // Countdown display from the server deadline.
  useEffect(() => {
    if (deadline.current === null || !attempt) return;
    const id = window.setInterval(() => {
      const left = ((deadline.current ?? 0) - performance.now()) / 1000;
      setRemaining(Math.max(0, left));
      if (left <= 0) void submit(true);
    }, 500);
    return () => window.clearInterval(id);
  }, [attempt, submit]);

  // Debounced autosave of changed answers and flags.
  const flush = useCallback(async () => {
    if (!attempt || !quizId || finished.current) return;
    const ids = [...dirty.current];
    if (ids.length === 0 && !flagsDirty.current) return;
    setSave("saving");
    try {
      const saved = await studyApi.saveAnswers(
        quizId,
        attempt.id,
        ids.map((question_id) => ({
          question_id,
          answer: answersRef.current[question_id] ?? [],
        })),
        flagsDirty.current ? flaggedRef.current : undefined,
      );
      ids.forEach((i) => dirty.current.delete(i));
      flagsDirty.current = false;
      syncClock(saved);
      setSave("saved");
    } catch (err) {
      if (
        err instanceof ApiRequestError &&
        (err.code === "QUIZ_ATTEMPT_EXPIRED" || err.code === "QUIZ_ATTEMPT_SUBMITTED")
      ) {
        void submit(true);
        return;
      }
      setSave("error");
    }
  }, [attempt, quizId, syncClock, submit]);

  const schedule = useCallback(() => {
    setSave("saving");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), SAVE_DELAY_MS);
  }, [flush]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  function setAnswer(q: QuizQuestion, value: AnswerValue) {
    answersRef.current = { ...answersRef.current, [q.id]: value };
    setAnswers(answersRef.current);
    dirty.current.add(q.id);
    schedule();
  }

  if (error)
    return (
      <div className="space-y-3">
        <ErrorDisplay title="Quiz unavailable" message={error} />
        <Link href={`/study/${materialId}`} className="text-primary text-sm underline">
          Back to the quiz
        </Link>
      </div>
    );
  if (!attempt) return <LoadingSpinner />;

  const questions = attempt.questions;
  const q = questions[current];
  const answered = questions.filter((x) => isAnswered(answers[x.id])).length;
  const unanswered = questions.length - answered;
  const low = remaining !== null && remaining <= 60;

  function toggleFlag(id: string) {
    flagsDirty.current = true;
    flaggedRef.current = flaggedRef.current.includes(id)
      ? flaggedRef.current.filter((x) => x !== id)
      : [...flaggedRef.current, id];
    setFlagged(flaggedRef.current);
    schedule();
  }

  return (
    <div className="space-y-4">
      <div className="bg-background/95 sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b py-2">
        <p className="text-sm" aria-live="polite">
          {answered} of {questions.length} answered
        </p>
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground text-xs" role="status" data-testid="save-state">
            {save === "saved"
              ? "All answers saved"
              : save === "saving"
                ? "Saving…"
                : "Not saved. Retrying on your next change."}
          </span>
          {remaining !== null ? (
            <span
              className={`font-mono text-lg tabular-nums ${low ? "text-destructive font-semibold" : ""}`}
              role="timer"
              aria-label={`Time remaining ${formatClock(remaining)}`}
              data-testid="quiz-timer"
            >
              {formatClock(remaining)}
            </span>
          ) : null}
        </div>
      </div>

      <div
        role="progressbar"
        aria-label="Quiz progress"
        aria-valuemin={0}
        aria-valuemax={questions.length}
        aria-valuenow={answered}
        className="bg-muted h-1.5 overflow-hidden rounded"
      >
        <div
          className="bg-primary h-full"
          style={{ width: `${(answered / Math.max(1, questions.length)) * 100}%` }}
        />
      </div>

      <nav aria-label="Questions" className="flex flex-wrap gap-1.5">
        {questions.map((x, i) => (
          <Button
            key={x.id}
            type="button"
            size="sm"
            variant={
              i === current ? "default" : isAnswered(answers[x.id]) ? "secondary" : "outline"
            }
            aria-current={i === current ? "step" : undefined}
            aria-label={`Question ${i + 1}${isAnswered(answers[x.id]) ? ", answered" : ""}${flagged.includes(x.id) ? ", flagged" : ""}`}
            onClick={() => setCurrent(i)}
          >
            {i + 1}
            {flagged.includes(x.id) ? <Flag className="ml-0.5 h-3 w-3" aria-hidden="true" /> : null}
          </Button>
        ))}
      </nav>

      {q ? (
        <fieldset className="space-y-3" key={q.id}>
          <legend className="text-base font-medium break-words">
            <span className="text-muted-foreground mr-2 text-sm">
              Question {current + 1} of {questions.length}
            </span>
            <span className="block pt-1 whitespace-pre-wrap">{q.question}</span>
          </legend>
          {q.answer_format === "text" ? (
            <Textarea
              aria-label="Your answer"
              rows={
                q.question_type === "descriptive" ? 8 : q.question_type === "short_answer" ? 4 : 1
              }
              maxLength={8000}
              value={typeof answers[q.id] === "string" ? (answers[q.id] as string) : ""}
              onChange={(e) => setAnswer(q, e.target.value)}
            />
          ) : (
            <div
              className="space-y-2"
              role={q.answer_format === "single_choice" ? "radiogroup" : "group"}
            >
              {q.options.map((o) => {
                const chosen = Array.isArray(answers[q.id]) ? (answers[q.id] as string[]) : [];
                const single = q.answer_format === "single_choice";
                return (
                  <label
                    key={o.id}
                    className="border-border hover:bg-muted/40 flex cursor-pointer items-start gap-2 rounded-lg border p-3 text-sm"
                  >
                    <input
                      type={single ? "radio" : "checkbox"}
                      name={`q-${q.id}`}
                      className="mt-0.5"
                      checked={chosen.includes(o.id)}
                      onChange={(e) =>
                        setAnswer(
                          q,
                          single
                            ? [o.id]
                            : e.target.checked
                              ? [...chosen, o.id]
                              : chosen.filter((c) => c !== o.id),
                        )
                      }
                    />
                    <span className="break-words">
                      {q.question_type === "true_false" ? o.text : `${o.id}. ${o.text}`}
                    </span>
                  </label>
                );
              })}
              {q.answer_format === "single_choice" && isAnswered(answers[q.id]) ? (
                <Button type="button" variant="ghost" size="sm" onClick={() => setAnswer(q, [])}>
                  Clear answer
                </Button>
              ) : null}
            </div>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-pressed={flagged.includes(q.id)}
            onClick={() => toggleFlag(q.id)}
          >
            <Flag aria-hidden="true" />
            {flagged.includes(q.id) ? "Unflag question" : "Flag for review"}
          </Button>
        </fieldset>
      ) : null}

      <div className="flex flex-wrap justify-between gap-2">
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={current === 0}
            onClick={() => setCurrent((c) => c - 1)}
          >
            Previous
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={current >= questions.length - 1}
            onClick={() => setCurrent((c) => c + 1)}
          >
            Next
          </Button>
        </div>
        <Button type="button" disabled={submitting} onClick={() => setConfirmSubmit(true)}>
          {submitting ? "Submitting…" : "Submit quiz"}
        </Button>
      </div>

      <ConfirmDialog
        open={confirmSubmit}
        onOpenChange={setConfirmSubmit}
        title="Submit this quiz?"
        description={
          unanswered > 0
            ? `You have ${unanswered} unanswered question${unanswered === 1 ? "" : "s"}${flagged.length ? ` and ${flagged.length} flagged` : ""}. After you submit you cannot change your answers.`
            : "After you submit you cannot change your answers."
        }
        confirmLabel="Submit"
        onConfirm={() => {
          setConfirmSubmit(false);
          void submit(false);
        }}
      />
    </div>
  );
}
