"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { formatDuration, formatPercent } from "@/lib/api/revision";
import { studyApi, type QuizHistoryItem } from "@/lib/api/study";
import { ScopeFilter, type ScopeValue } from "@/features/revision/scope-filter";
import { AttemptCompare } from "./attempt-compare";

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<string, string> = {
  in_progress: "In progress",
  submitted: "Submitted",
  abandoned: "Abandoned",
};

type StatusFilter = "" | "in_progress" | "submitted" | "abandoned";

/** Two picked attempts can be compared when both are submitted and belong to the same quiz. */
export function canCompare(a: QuizHistoryItem | undefined, b: QuizHistoryItem | undefined) {
  return (
    !!a &&
    !!b &&
    a.id !== b.id &&
    a.quiz_id === b.quiz_id &&
    a.status === "submitted" &&
    b.status === "submitted"
  );
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "–";
}

export function QuizHistory() {
  const [status, setStatus] = useState<StatusFilter>("");
  const [scope, setScope] = useState<ScopeValue>({});
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState<QuizHistoryItem[]>([]);
  const [comparing, setComparing] = useState<[QuizHistoryItem, QuizHistoryItem] | null>(null);

  const scopeKey = JSON.stringify(scope);
  const history = useAsync(
    () =>
      studyApi.history({
        status: status || undefined,
        subject_id: scope.subject_id,
        chapter_id: scope.chapter_id,
        date_from: scope.start_date,
        // the API reads a bare date as midnight, so end the chosen day at its last second
        date_to: scope.end_date ? `${scope.end_date}T23:59:59` : undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [status, scopeKey, offset],
  );

  function resetPaging() {
    setOffset(0);
    setPicked([]);
    setComparing(null);
  }

  function toggle(item: QuizHistoryItem) {
    setComparing(null);
    setPicked((current) => {
      if (current.some((p) => p.id === item.id)) return current.filter((p) => p.id !== item.id);
      // keep at most two picks; a third replaces the oldest
      return [...current, item].slice(-2);
    });
  }

  const [a, b] = picked;
  const comparable = canCompare(a, b);
  // earlier attempt first, so "improved" reads in time order
  const ordered: [QuizHistoryItem, QuizHistoryItem] | null = comparable
    ? new Date(a.started_at) <= new Date(b.started_at)
      ? [a, b]
      : [b, a]
    : null;

  return (
    <div className="min-w-0 space-y-6">
      <ScopeFilter
        value={scope}
        onChange={(next) => {
          setScope(next);
          resetPaging();
        }}
      />
      <label className="block text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Status</span>
        <select
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as StatusFilter);
            resetPaging();
          }}
        >
          <option value="">All</option>
          <option value="submitted">Submitted</option>
          <option value="in_progress">In progress</option>
          <option value="abandoned">Abandoned</option>
        </select>
      </label>

      <AsyncSection
        title="Attempts"
        loading={history.loading}
        error={history.error}
        onRetry={history.reload}
        isEmpty={(history.data?.items.length ?? 0) === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No quiz attempts match. Take a quiz from your study library and it will be listed here.
          </p>
        }
        action={
          <Button
            size="sm"
            disabled={!ordered}
            onClick={() => ordered && setComparing(ordered)}
            title={
              ordered ? undefined : "Pick two submitted attempts of the same quiz to compare them"
            }
          >
            Compare selected
          </Button>
        }
      >
        {history.data ? (
          <div className="space-y-3">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Your quiz attempts, newest first</caption>
                <thead>
                  <tr className="text-muted-foreground border-border border-b text-xs">
                    <th className="py-2 pr-3 font-medium">Compare</th>
                    <th className="py-2 pr-3 font-medium">Quiz</th>
                    <th className="py-2 pr-3 font-medium">Started</th>
                    <th className="py-2 pr-3 font-medium">Status</th>
                    <th className="py-2 pr-3 font-medium">Score</th>
                    <th className="py-2 pr-3 font-medium">Time</th>
                    <th className="py-2 font-medium">
                      <span className="sr-only">Results</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {history.data.items.map((item) => (
                    <tr key={item.id} className="border-border border-b last:border-0">
                      <td className="py-2 pr-3">
                        <input
                          type="checkbox"
                          aria-label={`Select attempt of ${item.quiz_title} started ${formatDate(item.started_at)}`}
                          checked={picked.some((p) => p.id === item.id)}
                          onChange={() => toggle(item)}
                        />
                      </td>
                      <td className="py-2 pr-3">{item.quiz_title}</td>
                      <td className="py-2 pr-3">{formatDate(item.started_at)}</td>
                      <td className="py-2 pr-3">{STATUS_LABEL[item.status] ?? item.status}</td>
                      <td className="py-2 pr-3">
                        {item.status === "submitted" ? formatPercent(item.percentage) : "–"}
                      </td>
                      <td className="py-2 pr-3">
                        {item.time_taken_seconds != null
                          ? formatDuration(item.time_taken_seconds)
                          : "–"}
                      </td>
                      <td className="py-2">
                        {item.status === "submitted" ? (
                          <Link
                            className="text-primary underline"
                            href={`/study/${item.study_material_id}/quiz/results/${item.id}`}
                          >
                            View results
                          </Link>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              offset={offset}
              limit={PAGE_SIZE}
              total={history.data.total}
              onChange={(next) => {
                setOffset(next);
                setPicked([]);
                setComparing(null);
              }}
            />
          </div>
        ) : null}
      </AsyncSection>

      {comparing ? (
        <AttemptCompare
          quizId={comparing[0].quiz_id}
          first={comparing[0].id}
          second={comparing[1].id}
        />
      ) : null}
    </div>
  );
}
