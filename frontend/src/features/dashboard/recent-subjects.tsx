"use client";

import Link from "next/link";
import { AsyncSection } from "@/components/ui/async-section";
import { EmptyState } from "@/components/ui/empty-state";
import { useAsync } from "@/hooks/use-async";
import { formatDate } from "@/lib/activity";
import { dashboardApi } from "@/lib/api/dashboard";

export function RecentSubjects() {
  const { data, loading, error, reload } = useAsync(() => dashboardApi.recentSubjects(5));
  const items = data ?? [];

  return (
    <AsyncSection
      title="Recent subjects"
      loading={loading}
      error={error}
      onRetry={reload}
      isEmpty={items.length === 0}
      empty={
        <EmptyState
          title="No subjects yet"
          description="Subjects you create or update will appear here."
        />
      }
      action={
        <Link
          href="/subjects"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring rounded-sm text-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          All subjects
        </Link>
      }
    >
      <ul className="divide-border border-border divide-y rounded-lg border">
        {items.map((s) => (
          <li key={s.id} className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:justify-between">
            <Link
              href={`/workspaces/${s.workspace_id}/subjects/${s.id}`}
              className="focus-visible:ring-ring min-w-0 truncate rounded-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
            >
              {s.name}
            </Link>
            <span className="text-muted-foreground text-xs">
              {s.workspace_name} · Updated {formatDate(s.updated_at)}
            </span>
          </li>
        ))}
      </ul>
    </AsyncSection>
  );
}
