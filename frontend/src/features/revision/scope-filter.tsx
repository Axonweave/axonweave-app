"use client";

import { useState } from "react";
import { useAsync } from "@/hooks/use-async";
import { chaptersApi } from "@/lib/api/chapters";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";

export interface ScopeValue {
  subject_id?: string;
  chapter_id?: string;
  /** YYYY-MM-DD, inclusive. */
  start_date?: string;
  end_date?: string;
}

const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";

/**
 * Subject, chapter and date-range filter (spec sections 2.6 and 3). The workspace picker only
 * decides where subjects are listed from; the filter applies once a subject is chosen. The
 * backend still scopes every query to the signed-in user.
 */
export function ScopeFilter({
  value,
  onChange,
}: {
  value: ScopeValue;
  onChange: (next: ScopeValue) => void;
}) {
  const [chosenWorkspace, setWorkspaceId] = useState("");
  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  // until the user picks one, browse subjects of the first workspace
  const workspaceId = chosenWorkspace || workspaces.data?.[0]?.id || "";

  const subjects = useAsync(
    () =>
      workspaceId
        ? subjectsApi.list(workspaceId, { limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [workspaceId],
  );
  const chapters = useAsync(
    () =>
      workspaceId && value.subject_id
        ? chaptersApi.list(workspaceId, value.subject_id, { limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [workspaceId, value.subject_id],
  );

  const set = (patch: Partial<ScopeValue>) => onChange({ ...value, ...patch });
  const hasFilter = !!(value.subject_id || value.chapter_id || value.start_date || value.end_date);

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      aria-label="Filter by subject, chapter and dates"
      onSubmit={(e) => e.preventDefault()}
    >
      {(workspaces.data?.length ?? 0) > 1 ? (
        <label className="text-sm">
          <span className="text-muted-foreground mb-1 block text-xs">Workspace</span>
          <select
            className={SELECT}
            value={workspaceId}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              onChange({ ...value, subject_id: undefined, chapter_id: undefined });
            }}
          >
            {workspaces.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Subject</span>
        <select
          className={SELECT}
          value={value.subject_id ?? ""}
          onChange={(e) => set({ subject_id: e.target.value || undefined, chapter_id: undefined })}
        >
          <option value="">All subjects</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Chapter</span>
        <select
          className={SELECT}
          value={value.chapter_id ?? ""}
          disabled={!value.subject_id}
          onChange={(e) => set({ chapter_id: e.target.value || undefined })}
        >
          <option value="">All chapters</option>
          {chapters.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">From</span>
        <input
          type="date"
          className={SELECT}
          value={value.start_date ?? ""}
          max={value.end_date || undefined}
          onChange={(e) => set({ start_date: e.target.value || undefined })}
        />
      </label>
      <label className="text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">To</span>
        <input
          type="date"
          className={SELECT}
          value={value.end_date ?? ""}
          min={value.start_date || undefined}
          onChange={(e) => set({ end_date: e.target.value || undefined })}
        />
      </label>
      {hasFilter ? (
        <button
          type="button"
          className="text-primary h-9 text-sm underline"
          onClick={() => onChange({})}
        >
          Clear filters
        </button>
      ) : null}
    </form>
  );
}
