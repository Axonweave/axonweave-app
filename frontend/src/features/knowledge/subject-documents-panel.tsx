"use client";

import { AsyncSection } from "@/components/ui/async-section";
import { useAsync } from "@/hooks/use-async";
import { documentsApi, type DocumentRecord } from "@/lib/api/documents";
import type { ExtractionJob } from "@/lib/api/knowledge";

const ACTIVE = new Set(["pending", "retrieving_sources", "extracting", "validating", "saving"]);
const DOC_LIMIT = 100;

type Tone = "done" | "busy" | "bad" | "idle";

export interface DocumentRow {
  id: string;
  name: string;
  label: string;
  detail: string | null;
  tone: Tone;
}

function count(stats: ExtractionJob["result_stats"], ...keys: string[]): number {
  return keys.reduce((sum, k) => {
    const v = stats?.[k];
    return sum + (typeof v === "number" ? v : 0);
  }, 0);
}

/** Newest job per document (the list is newest first) joined with the subject's documents. */
export function documentRows(docs: DocumentRecord[], jobs: ExtractionJob[]): DocumentRow[] {
  const latest = new Map<string, ExtractionJob>();
  for (const j of jobs) {
    if (j.document_id && !latest.has(j.document_id)) latest.set(j.document_id, j);
  }
  return docs.map((d) => {
    const job = latest.get(d.id);
    const base = { id: d.id, name: d.display_name };
    if (!job) {
      return d.processing_status === "completed"
        ? { ...base, label: "Not extracted yet", detail: null, tone: "idle" as const }
        : {
            ...base,
            label: "Not ready",
            detail: "Still being processed, or processing did not finish.",
            tone: "idle" as const,
          };
    }
    if (job.status === "completed") {
      const concepts = count(job.result_stats, "nodes_created", "nodes_matched");
      const links = count(job.result_stats, "edges_created", "edges_matched");
      return {
        ...base,
        label: "Extracted",
        detail: `${concepts} concepts, ${links} relationships`,
        tone: "done" as const,
      };
    }
    if (ACTIVE.has(job.status)) {
      return {
        ...base,
        label: job.status === "pending" ? "Waiting" : "Extracting",
        detail: job.status === "pending" ? null : `${job.progress}%`,
        tone: "busy" as const,
      };
    }
    return {
      ...base,
      label: job.status === "cancelled" ? "Cancelled" : "Failed",
      detail: job.error_message ?? null,
      tone: "bad" as const,
    };
  });
}

/** The newest web-search run for the subject, shown as its own row (it has no document). */
export function webResearchRow(jobs: ExtractionJob[]): DocumentRow | null {
  const job = jobs.find((j) => j.source_kind === "web");
  if (!job) return null;
  const base = { id: job.id, name: "Web research" };
  if (job.status === "completed") {
    const concepts = count(job.result_stats, "nodes_created", "nodes_matched");
    const links = count(job.result_stats, "edges_created", "edges_matched");
    return {
      ...base,
      label: "Done",
      detail: `${concepts} concepts, ${links} relationships`,
      tone: "done",
    };
  }
  if (ACTIVE.has(job.status)) {
    return { ...base, label: "Searching", detail: `${job.progress}%`, tone: "busy" };
  }
  return {
    ...base,
    label: job.status === "cancelled" ? "Cancelled" : "Failed",
    detail: job.error_message ?? null,
    tone: "bad",
  };
}

const TONE: Record<Tone, string> = {
  done: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100",
  busy: "bg-blue-100 text-blue-900 dark:bg-blue-900/40 dark:text-blue-100",
  bad: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100",
  idle: "bg-muted text-muted-foreground",
};

/**
 * Which documents of a subject have been turned into graph concepts, and which have not. The
 * status comes from the extraction jobs the parent is already polling, so it updates live while a
 * generation runs.
 */
export function SubjectDocumentsPanel({
  subjectId,
  jobs,
}: {
  subjectId: string;
  jobs: ExtractionJob[];
}) {
  const docs = useAsync(
    () => documentsApi.list({ subject_id: subjectId, limit: DOC_LIMIT }),
    [subjectId],
  );
  const rows = documentRows(docs.data?.data ?? [], jobs);
  const extracted = rows.filter((r) => r.tone === "done").length;
  const web = webResearchRow(jobs);

  return (
    <div className="w-full basis-full" data-testid="subject-documents">
      <AsyncSection
        title="Documents in this subject"
        loading={docs.loading}
        error={docs.error}
        onRetry={docs.reload}
        isEmpty={!rows.length && !web}
        empty={<p className="text-muted-foreground text-xs">No documents in this subject yet.</p>}
      >
        <p className="text-muted-foreground mb-2 text-xs" role="status">
          {extracted} of {rows.length} documents extracted
          {(docs.data?.total ?? 0) > DOC_LIMIT ? ` (showing the first ${DOC_LIMIT})` : ""}.
        </p>
        <ul className="divide-y rounded-md border">
          {[...(web ? [web] : []), ...rows].map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
              <span className="min-w-0 flex-1 truncate font-medium" title={r.name}>
                {r.name}
              </span>
              <span className={`rounded-full px-2 py-0.5 ${TONE[r.tone]}`}>{r.label}</span>
              {r.detail ? <span className="text-muted-foreground">{r.detail}</span> : null}
            </li>
          ))}
        </ul>
      </AsyncSection>
    </div>
  );
}
