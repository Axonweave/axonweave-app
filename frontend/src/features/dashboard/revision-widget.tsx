"use client";

import Link from "next/link";
import { AsyncSection } from "@/components/ui/async-section";
import { buttonVariants } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { analyticsApi } from "@/lib/api/revision";

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-border rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-foreground text-xl font-semibold">{value}</p>
    </div>
  );
}

/** Real figures from the analytics overview: what is due for revision and the current streak. */
export function RevisionWidget() {
  const overview = useAsync(() => analyticsApi.overview(), []);
  const o = overview.data;

  return (
    <AsyncSection
      title="Revision"
      loading={overview.loading}
      error={overview.error}
      onRetry={overview.reload}
      isEmpty={false}
      empty={null}
      action={
        <Link className={buttonVariants({ variant: "outline", size: "sm" })} href="/revision">
          Open revision
        </Link>
      }
    >
      {o ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Tile label="Due today" value={String(o.due_today)} />
            <Tile label="Overdue" value={String(o.overdue)} />
            <Tile label="Current streak" value={`${o.current_streak_days} days`} />
            <Tile label="Topics to revisit" value={String(o.topics_needing_attention)} />
          </div>
          {o.due_today + o.overdue === 0 ? (
            <p className="text-muted-foreground text-sm">
              Nothing is due right now. Cards you have not reviewed yet appear under Revision.
            </p>
          ) : null}
        </div>
      ) : null}
    </AsyncSection>
  );
}
