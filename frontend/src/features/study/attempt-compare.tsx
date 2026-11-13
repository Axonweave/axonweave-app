"use client";

import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { formatDuration, formatPercent } from "@/lib/api/revision";
import { studyApi, type QuizCompare } from "@/lib/api/study";

const MOVEMENT_STYLE: Record<string, string> = {
  improved: "text-green-700 dark:text-green-400",
  declined: "text-red-700 dark:text-red-400",
  same: "text-muted-foreground",
};

const MOVEMENT_LABEL: Record<string, string> = {
  improved: "Improved",
  declined: "Declined",
  same: "No change",
};

/** "+5" / "-3" / "0" for a signed change, or a dash when it cannot be worked out. */
export function formatChange(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "–";
  const rounded = Math.round(value);
  if (rounded === 0) return `0${unit}`;
  return `${rounded > 0 ? "+" : ""}${rounded}${unit}`;
}

export function CompareTable({ data }: { data: QuizCompare }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="border-border rounded-lg border p-3">
          <p className="text-muted-foreground text-xs">Score change</p>
          <p className="text-foreground text-xl font-semibold">{formatChange(data.score_change)}</p>
          <p className="text-muted-foreground text-xs">
            {formatPercent(data.first.percentage)} to {formatPercent(data.second.percentage)}
          </p>
        </div>
        <div className="border-border rounded-lg border p-3">
          <p className="text-muted-foreground text-xs">Percentage change</p>
          <p className="text-foreground text-xl font-semibold">
            {formatChange(data.percentage_change, " pts")}
          </p>
        </div>
        <div className="border-border rounded-lg border p-3">
          <p className="text-muted-foreground text-xs">Time change</p>
          <p className="text-foreground text-xl font-semibold">
            {data.time_change_seconds === null
              ? "–"
              : `${data.time_change_seconds > 0 ? "+" : "-"}${formatDuration(
                  Math.abs(data.time_change_seconds),
                )}`}
          </p>
        </div>
      </div>

      {data.topics.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Topic results in the two attempts</caption>
            <thead>
              <tr className="text-muted-foreground border-border border-b text-xs">
                <th className="py-2 pr-3 font-medium">Topic</th>
                <th className="py-2 pr-3 font-medium">First</th>
                <th className="py-2 pr-3 font-medium">Second</th>
                <th className="py-2 font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {data.topics.map((t) => (
                <tr key={t.topic ?? "none"} className="border-border border-b last:border-0">
                  <td className="py-2 pr-3">{t.topic ?? "No topic"}</td>
                  <td className="py-2 pr-3">{formatPercent(t.first_percentage)}</td>
                  <td className="py-2 pr-3">{formatPercent(t.second_percentage)}</td>
                  <td className="py-2">{formatChange(t.change, " pts")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Question by question comparison</caption>
          <thead>
            <tr className="text-muted-foreground border-border border-b text-xs">
              <th className="py-2 pr-3 font-medium">Question</th>
              <th className="py-2 pr-3 font-medium">First</th>
              <th className="py-2 pr-3 font-medium">Second</th>
              <th className="py-2 font-medium">Movement</th>
            </tr>
          </thead>
          <tbody>
            {data.questions.map((q) => (
              <tr key={q.question_id} className="border-border border-b last:border-0">
                <td className="py-2 pr-3">{q.question}</td>
                <td className="py-2 pr-3 capitalize">{q.first.replace("_", " ")}</td>
                <td className="py-2 pr-3 capitalize">{q.second.replace("_", " ")}</td>
                <td className={`py-2 ${MOVEMENT_STYLE[q.movement] ?? ""}`}>
                  {MOVEMENT_LABEL[q.movement] ?? q.movement}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted-foreground text-xs">{data.note}</p>
    </div>
  );
}

interface AttemptCompareProps {
  quizId: string;
  first: string;
  second: string;
}

/** Loads and shows the comparison of two attempts of one quiz (first = earlier pick). */
export function AttemptCompare({ quizId, first, second }: AttemptCompareProps) {
  const compare = useAsync(() => studyApi.compare(quizId, first, second), [quizId, first, second]);
  return (
    <AsyncSection
      title="Attempt comparison"
      loading={compare.loading}
      error={compare.error}
      onRetry={compare.reload}
      isEmpty={!compare.data}
      empty={<p className="text-muted-foreground text-sm">Nothing to compare.</p>}
    >
      {compare.data ? <CompareTable data={compare.data} /> : null}
    </AsyncSection>
  );
}
