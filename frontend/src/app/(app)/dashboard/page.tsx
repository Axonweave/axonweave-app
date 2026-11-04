"use client";

import { useState } from "react";
import { CreateWorkspaceDialog } from "@/features/workspaces/create-workspace-dialog";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { RecentActivity } from "@/features/dashboard/recent-activity";
import { RecentSubjects } from "@/features/dashboard/recent-subjects";
import { StatsStrip } from "@/features/dashboard/stats-strip";
import { WelcomeHeader } from "@/features/dashboard/welcome-header";
import { WorkspaceOverview } from "@/features/dashboard/workspace-overview";

export default function DashboardPage() {
  const [createOpen, setCreateOpen] = useState(false);
  // Bumping the key remounts the data sections so they re-fetch after a workspace is created.
  const [version, setVersion] = useState(0);

  return (
    <div className="min-w-0 space-y-8">
      <WelcomeHeader />
      <QuickActions onCreateWorkspace={() => setCreateOpen(true)} />
      <div key={version} className="space-y-8">
        <StatsStrip />
        <WorkspaceOverview onCreateWorkspace={() => setCreateOpen(true)} />
        <div className="grid gap-8 lg:grid-cols-2">
          <RecentSubjects />
          <RecentActivity />
        </div>
      </div>
      <CreateWorkspaceDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => setVersion((v) => v + 1)}
      />
    </div>
  );
}
