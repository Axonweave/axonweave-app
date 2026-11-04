"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { EmptyState } from "@/components/ui/empty-state";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { dashboardApi } from "@/lib/api/dashboard";
import { ActivityList } from "./activity-list";

const PAGE_SIZE = 20;

export function ActivityFeed() {
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useAsync(
    () => dashboardApi.activity(PAGE_SIZE, offset),
    [offset],
  );
  const items = data?.data ?? [];

  return (
    <div className="space-y-4">
      <AsyncSection
        title="All activity"
        loading={loading}
        error={error}
        onRetry={reload}
        isEmpty={items.length === 0}
        empty={
          <EmptyState
            title="No activity yet"
            description="When you create, update, archive or delete items, it is recorded here."
          />
        }
      >
        <ActivityList items={items} />
      </AsyncSection>
      {!loading && !error && (
        <Pager offset={offset} limit={PAGE_SIZE} total={data?.total ?? 0} onChange={setOffset} />
      )}
    </div>
  );
}
