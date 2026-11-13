"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import {
  analyticsApi,
  formatDuration,
  formatPercent,
  type SubjectPerformance,
  type TopicRow,
} from "@/lib/api/revision";
import { CalendarGrid } from "./calendar-grid";
import { BarChart, TrendChart } from "./charts";
import { ScopeFilter, type ScopeValue } from "./scope-filter";

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

export function SubjectTable({ rows }: { rows: SubjectPerformance["items"] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Performance by subject</caption>
        <thead>
          <tr className="text-muted-foreground border-border border-b text-xs">
            <th className="py-2 pr-3 font-medium">Subject</th>
            <th className="py-2 pr-3 font-medium">Quiz attempts</th>
            <th className="py-2 pr-3 font-medium">Average score</th>
            <th className="py-2 pr-3 font-medium">Cards reviewed</th>
            <th className="py-2 font-medium">Hard or again</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.subject_id ?? "none"} className="border-border border-b last:border-0">
              <td className="py-2 pr-3">{s.subject_name ?? "No subject"}</td>
              <td className="py-2 pr-3">{s.quiz_attempts}</td>
              <td className="py-2 pr-3">{formatPercent(s.average_quiz_percentage)}</td>
              <td className="py-2 pr-3">{s.reviews}</td>
              <td className="py-2">
                {s.hard_or_again_share === null
                  ? "No data yet"
                  : formatPercent(s.hard_or_again_share * 100)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProgressView() {
  const [scope, setScope] = useState<ScopeValue>({});
  const scopeKey = JSON.stringify(scope);
  const overview = useAsync(() => analyticsApi.overview(scope), [scopeKey]);
  const topics = useAsync(() => analyticsApi.topics(scope), [scopeKey]);
  const subjects = useAsync(() => analyticsApi.subjects(scope), [scopeKey]);
  const quizzes = useAsync(() => analyticsApi.quizzes(scope), [scopeKey]);
  const activity = useAsync(() => analyticsApi.activity(scope), [scopeKey]);
  const o = overview.data;

  return (
    <div className="min-w-0 space-y-8">
      <ScopeFilter value={scope} onChange={setScope} />
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
        title="Subjects"
        loading={subjects.loading}
        error={subjects.error}
        onRetry={subjects.reload}
        isEmpty={(subjects.data?.items.length ?? 0) === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            Subject results appear after you submit a quiz or review cards from a subject.
          </p>
        }
      >
        {subjects.data ? <SubjectTable rows={subjects.data.items} /> : null}
      </AsyncSection>

      <AsyncSection
        title="Trends"
        loading={quizzes.loading || activity.loading}
        error={quizzes.error ?? activity.error}
        onRetry={() => {
          quizzes.reload();
          activity.reload();
        }}
        isEmpty={
          (quizzes.data?.points.length ?? 0) === 0 && (activity.data?.total_reviews ?? 0) === 0
        }
        empty={
          <p className="text-muted-foreground text-sm">
            Trends appear once you have submitted quizzes or reviewed cards.
          </p>
        }
      >
        <div className="grid gap-6 lg:grid-cols-2">
          <TrendChart
            title="Quiz scores over time"
            points={(quizzes.data?.points ?? []).map((p) => ({
              label: p.local_date,
              value: p.percentage,
            }))}
          />
          <BarChart
            title="Cards reviewed per day"
            data={(activity.data?.days ?? []).map((d) => ({ label: d.date, value: d.reviews }))}
          />
        </div>
      </AsyncSection>

      <CalendarGrid filters={scope} />

      <p className="text-sm">
        <Link className="text-primary underline" href="/study/history">
          View your quiz history and compare attempts
        </Link>
      </p>
    </div>
  );
}
