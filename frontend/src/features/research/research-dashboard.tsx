"use client";

import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { researchApi } from "@/lib/api/research";

const ACTIVITY_LABELS: Record<string, string> = {
  paper_added: "Paper added",
  comparison_saved: "Comparison saved",
  matrix_updated: "Evidence matrix updated",
  draft_updated: "Draft updated",
};

/** Real counts and recent activity: for one project, or across the user's active projects. */
export function ResearchDashboardPanel({
  workspaceId,
  projectId,
}: {
  workspaceId?: string;
  projectId?: string;
}) {
  const dash = useAsync(
    () =>
      projectId ? researchApi.projectDashboard(projectId) : researchApi.dashboard(workspaceId),
    [workspaceId, projectId],
  );
  const d = dash.data;
  const c = d?.counts;
  const stats: [string, number | null | undefined][] = [
    ...(projectId ? [] : ([["Active projects", c?.active_projects]] as [string, number | null][])),
    ["Papers", c?.papers],
    ["Analysed papers", c?.papers_analysed],
    ["Awaiting analysis", c?.papers_awaiting],
    ["Literature comparisons", c?.comparisons],
    ["Evidence matrices", c?.matrices],
    ["Candidate research gaps", c?.candidate_gaps],
    ["Contradictions to review", c?.contradictions_to_review],
    ["Drafts in progress", c?.drafts_in_progress],
  ];
  return (
    <AsyncSection
      title={projectId ? "Project dashboard" : "Research dashboard"}
      loading={dash.loading}
      error={dash.error}
      onRetry={dash.reload}
      isEmpty={false}
      empty={null}
    >
      {d && (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {stats.map(([label, value]) => (
              <div key={label} className="border-border bg-card rounded-lg border p-3">
                <dt className="text-muted-foreground text-xs">{label}</dt>
                <dd className="text-foreground text-2xl font-semibold">{value ?? 0}</dd>
              </div>
            ))}
          </dl>
          {(c?.papers_failed ?? 0) > 0 && (
            <p className="text-sm">
              {c?.papers_failed} paper{c?.papers_failed === 1 ? "" : "s"} could not be analysed.
              Open the paper library to retry.
            </p>
          )}
          <div>
            <h3 className="text-sm font-semibold">Recent research activity</h3>
            {d.recent.length === 0 ? (
              <p className="text-muted-foreground mt-1 text-sm">
                Nothing yet. Add a paper or start a draft and it will appear here.
              </p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm">
                {d.recent.map((r, i) => (
                  <li key={`${r.kind}-${r.at}-${i}`}>
                    <span className="text-muted-foreground">
                      {ACTIVITY_LABELS[r.kind] ?? r.kind}:
                    </span>{" "}
                    {r.title}
                    {!projectId && (
                      <span className="text-muted-foreground"> · {r.project_title}</span>
                    )}
                    <span className="text-muted-foreground text-xs">
                      {" "}
                      · {new Date(r.at).toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </AsyncSection>
  );
}
