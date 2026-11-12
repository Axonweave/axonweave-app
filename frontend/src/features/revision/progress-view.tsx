"use client";

import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { analyticsApi, formatDuration, formatPercent, type TopicRow } from "@/lib/api/revision";

const STATUS_STYLE: Record<string, string> = {
  strong: "text-green-700 dark:text-green-400",
  developing: "text-amber-700 dark:text-amber-400",
  needs_revision: "text-red-700 dark:text-red-400",
  not_enough_data: "text-muted-foreground",
};

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="border-border rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-foreground text-xl font-semibold">{value}</p>
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}

export function TopicTable({ rows }: { rows: TopicRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Quiz accuracy by topic</caption>
        <thead>
          <tr className="text-muted-foreground border-border border-b text-xs">
            <th className="py-2 pr-3 font-medium">Topic</th>
            <th className="py-2 pr-3 font-medium">Accuracy</th>
            <th className="py-2 pr-3 font-medium">Answers</th>
            <th className="py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.topic} className="border-border border-b last:border-0">
              <td className="py-2 pr-3">{t.topic}</td>
              <td className="py-2 pr-3">{formatPercent(t.accuracy)}</td>
              <td className="py-2 pr-3">{t.answers}</td>
              <td className={`py-2 ${STATUS_STYLE[t.status] ?? ""}`}>{t.status_label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProgressView() {
  const overview = useAsync(() => analyticsApi.overview(), []);
  const topics = useAsync(() => analyticsApi.topics(), []);
  const calendar = useAsync(() => analyticsApi.calendar(), []);
  const o = overview.data;

  return (
    <div className="min-w-0 space-y-8">
      <AsyncSection
        title="Overview"
        loading={overview.loading}
        error={overview.error}
        onRetry={overview.reload}
        isEmpty={!!o && o.quiz_attempts === 0 && o.flashcards_reviewed === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No study activity yet. Take a quiz or review a few flashcards and your progress will
            show up here.
          </p>
        }
      >
        {o ? (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Quiz attempts" value={String(o.quiz_attempts)} />
              <Stat label="Average quiz score" value={formatPercent(o.average_quiz_percentage)} />
              <Stat label="Cards reviewed" value={String(o.flashcards_reviewed)} />
              <Stat label="Time studied" value={formatDuration(o.time_spent_seconds)} />
              <Stat label="Current streak" value={`${o.current_streak_days} days`} />
              <Stat label="Longest streak" value={`${o.longest_streak_days} days`} />
              <Stat label="Due today" value={String(o.due_today)} hint={`${o.overdue} overdue`} />
              <Stat label="Topics to revisit" value={String(o.topics_needing_attention)} />
            </div>
            <p className="text-muted-foreground text-xs">{o.note}</p>
          </div>
        ) : null}
      </AsyncSection>

      <AsyncSection
        title="Topics"
        loading={topics.loading}
        error={topics.error}
        onRetry={topics.reload}
        isEmpty={(topics.data?.items.length ?? 0) === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            Topic results appear after you submit a quiz whose questions have topics.
          </p>
        }
      >
        {topics.data ? (
          <div className="space-y-2">
            <TopicTable rows={topics.data.items} />
            <p className="text-muted-foreground text-xs">{topics.data.note}</p>
          </div>
        ) : null}
      </AsyncSection>

      <AsyncSection
        title="Last 90 days"
        loading={calendar.loading}
        error={calendar.error}
        onRetry={calendar.reload}
        isEmpty={(calendar.data?.days.length ?? 0) === 0}
        empty={<p className="text-muted-foreground text-sm">No activity in this period.</p>}
      >
        <div className="space-y-2">
          {calendar.data ? (
            <p className="text-foreground text-sm">{calendar.data.streak.message}</p>
          ) : null}
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {calendar.data?.days
              .slice()
              .reverse()
              .map((d) => (
                <li
                  key={d.date}
                  className="border-border flex justify-between rounded border px-2 py-1"
                >
                  <span>{d.date}</span>
                  <span className="text-muted-foreground">
                    {d.quiz_attempts} quiz · {d.reviews} cards
                  </span>
                </li>
              ))}
          </ul>
        </div>
      </AsyncSection>
    </div>
  );
}
