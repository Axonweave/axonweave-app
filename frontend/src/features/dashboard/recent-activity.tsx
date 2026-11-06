"use client";

import Link from "next/link";
import { AsyncSection } from "@/components/ui/async-section";
import { EmptyState } from "@/components/ui/empty-state";
import { ActivityList } from "@/features/activity/activity-list";
import { useAsync } from "@/hooks/use-async";
import { dashboardApi } from "@/lib/api/dashboard";

export function RecentActivity() {
  const { data, loading, error, reload } = useAsync(() => dashboardApi.activity(8, 0));
  const items = data?.data ?? [];

  return (
    <AsyncSection
      title="Recent activity"
      loading={loading}
      error={error}
      onRetry={reload}
      isEmpty={items.length === 0}
      empty={
        <EmptyState
          title="No activity yet"
          description="Your actions, like creating or archiving items, will be listed here."
        />
      }
      action={
        <Link
          href="/activity"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring rounded-sm text-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          View all
        </Link>
      }
    >
      <ActivityList items={items} />
    </AsyncSection>
  );
}
