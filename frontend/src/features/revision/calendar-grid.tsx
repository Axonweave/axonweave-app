"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { analyticsApi, type AnalyticsFilters } from "@/lib/api/revision";

export interface GridDay {
  date: string;
  activities: number;
  quiz_attempts: number;
  reviews: number;
}

const DAY_MS = 86_400_000;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const utc = (date: string) => Date.parse(`${date}T00:00:00Z`);
/** 0 = Monday ... 6 = Sunday. */
const weekday = (ms: number) => (new Date(ms).getUTCDay() + 6) % 7;

/**
 * Lays days out as weeks (rows) of Monday..Sunday. Days the backend did not return are shown as
 * empty days; cells before the start or after the end are null padding.
 */
export function buildWeeks(days: GridDay[], start: string, end: string): (GridDay | null)[][] {
  const byDate = new Map(days.map((d) => [d.date, d]));
  const first = utc(start);
  const last = utc(end);
  if (Number.isNaN(first) || Number.isNaN(last) || last < first) return [];

  const cells: (GridDay | null)[] = Array.from({ length: weekday(first) }, () => null);
  for (let t = first; t <= last; t += DAY_MS) {
    const date = iso(t);
    cells.push(byDate.get(date) ?? { date, activities: 0, quiz_attempts: 0, reviews: 0 });
  }
  while (cells.length % 7 !== 0) cells.push(null);

  const weeks: (GridDay | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

/** Shade class by how much happened that day; relative to the busiest day in the range. */
export function shade(activities: number, max: number): string {
  if (activities <= 0 || max <= 0) return "bg-muted";
  const ratio = activities / max;
  if (ratio > 0.66) return "bg-green-600 text-white dark:bg-green-500 dark:text-black";
  if (ratio > 0.33) return "bg-green-400 dark:bg-green-700";
  return "bg-green-200 dark:bg-green-900";
}

export function CalendarGrid({ filters = {} }: { filters?: AnalyticsFilters }) {
  const filterKey = JSON.stringify(filters);
  const calendar = useAsync(() => analyticsApi.calendar(filters), [filterKey]);
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useAsync(
    () => (selected ? analyticsApi.day(selected) : Promise.resolve(null)),
    [selected],
  );

  const data = calendar.data;
  const weeks = data ? buildWeeks(data.days, data.start_date, data.end_date) : [];
  const max = data ? Math.max(0, ...data.days.map((d) => d.activities)) : 0;
  const hasActivity = (data?.days.some((d) => d.activities > 0) ?? false) === true;

  return (
    <AsyncSection
      title="Study calendar"
      loading={calendar.loading}
      error={calendar.error}
      onRetry={calendar.reload}
      isEmpty={!data || !hasActivity}
      empty={<p className="text-muted-foreground text-sm">No activity in this period.</p>}
    >
      {data ? (
        <div className="space-y-3">
          <p className="text-foreground text-sm">{data.streak.message}</p>
          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-1 text-xs">
              <caption className="sr-only">
                Study activity per day from {data.start_date} to {data.end_date}. Select a day for
                details.
              </caption>
              <thead>
                <tr>
                  {WEEKDAYS.map((d) => (
                    <th key={d} scope="col" className="text-muted-foreground w-9 font-normal">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {weeks.map((week, wi) => (
                  <tr key={wi}>
                    {week.map((day, di) => (
                      <td key={di} className="p-0">
                        {day ? (
                          <button
                            type="button"
                            onClick={() => setSelected(day.date)}
                            aria-pressed={selected === day.date}
                            aria-label={`${day.date}: ${day.quiz_attempts} quizzes, ${day.reviews} cards reviewed`}
                            className={`h-9 w-9 rounded ${shade(day.activities, max)} ${
                              selected === day.date ? "ring-primary ring-2" : ""
                            }`}
                          >
                            {Number(day.date.slice(8))}
                          </button>
                        ) : (
                          <span className="block h-9 w-9" aria-hidden="true" />
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selected ? (
            <div className="border-border rounded-lg border p-3 text-sm" aria-live="polite">
              <p className="text-foreground font-medium">{selected}</p>
              {detail.loading ? (
                <p className="text-muted-foreground">Loading…</p>
              ) : detail.error ? (
                <p className="text-red-700 dark:text-red-400">{detail.error}</p>
              ) : detail.data ? (
                <p className="text-muted-foreground">
                  {detail.data.quizzes.length} quiz attempts · {detail.data.sessions.length}{" "}
                  revision sessions · {detail.data.reviews} cards reviewed
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </AsyncSection>
  );
}
