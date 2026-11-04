"use client";

import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { dashboardApi } from "@/lib/api/dashboard";

export function StatsStrip() {
  const { data, loading, error, reload } = useAsync(() => dashboardApi.stats());
  const entries: Array<[string, number]> = data
    ? [
        ["Workspaces", data.workspace_count],
        ["Subjects", data.subject_count],
        ["Folders", data.folder_count],
        ["Chapters", data.chapter_count],
      ]
    : [];

  return (
    <AsyncSection
      title="Your totals"
      loading={loading}
      error={error}
      onRetry={reload}
      isEmpty={false}
      empty={null}
    >
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {entries.map(([label, value]) => (
          <div key={label} className="border-border rounded-lg border p-4">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="mt-1 text-2xl font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
    </AsyncSection>
  );
}
