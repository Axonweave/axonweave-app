"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AsyncSection } from "@/components/ui/async-section";
import { EmptyState } from "@/components/ui/empty-state";
import { useAsync } from "@/hooks/use-async";
import { formatDate } from "@/lib/activity";
import { dashboardApi } from "@/lib/api/dashboard";

export function WorkspaceOverview({ onCreateWorkspace }: { onCreateWorkspace: () => void }) {
  const { data, loading, error, reload } = useAsync(() => dashboardApi.workspaces(6));
  const items = data?.data ?? [];

  return (
    <AsyncSection
      title="Workspaces"
      loading={loading}
      error={error}
      onRetry={reload}
      isEmpty={items.length === 0}
      empty={
        <EmptyState
          title="No workspaces yet"
          description="Create your first workspace to start organising your learning."
          action={<Button onClick={onCreateWorkspace}>Create workspace</Button>}
        />
      }
      action={
        <Link
          href="/workspaces"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring rounded-sm text-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          Manage workspaces
        </Link>
      }
    >
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((ws) => (
          <li key={ws.id} className="border-border min-w-0 rounded-lg border p-4">
            <h3 className="truncate font-medium">{ws.name}</h3>
            {ws.description && (
              <p className="text-muted-foreground mt-1 line-clamp-2 text-sm">{ws.description}</p>
            )}
            <p className="mt-3 text-sm">
              {ws.subject_count} {ws.subject_count === 1 ? "subject" : "subjects"}
            </p>
            <p className="text-muted-foreground text-xs">Updated {formatDate(ws.updated_at)}</p>
          </li>
        ))}
      </ul>
    </AsyncSection>
  );
}
