"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Archive, ArchiveRestore, Copy, Sparkles, Trash2 } from "lucide-react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { formatDate } from "@/lib/activity";
import { ApiRequestError } from "@/lib/api/client";
import {
  isJobDone,
  RESOURCE_LABELS,
  resourceLabel,
  studyApi,
  type LibraryItem,
} from "@/lib/api/study";
import { GenerateDialog } from "./generate-dialog";
import { JobProgress } from "./job-progress";
import { Chip, NativeSelect } from "./ui-bits";

const PAGE_SIZE = 25;
const TYPES = [
  "summary",
  "flashcards",
  "quiz",
  "study_guide",
  "glossary",
  "formula_sheet",
  "question_bank",
];
const NOT_DUPLICABLE = ["quiz", "question_bank"];

/** Jobs that are running now, polled until they finish; finished ones refresh the list. */
function ActiveJobs({ onFinished }: { onFinished: () => void }) {
  const jobs = useAsync(
    () => studyApi.jobs({ limit: 10 }).catch(() => ({ data: [], total: 0 })),
    [],
  );
  const list = jobs.data?.data ?? [];
  const active = list.some((j) => !isJobDone(j.status));
  const prevActive = useRef(false);
  const reload = jobs.reload;
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, 2500);
    return () => window.clearInterval(id);
  }, [active, reload]);
  useEffect(() => {
    if (prevActive.current && !active) onFinished();
    prevActive.current = active;
  }, [active, onFinished]);

  const shown = list.filter(
    (j) => !isJobDone(j.status) || (j.status === "failed" && recent(j.completed_at)),
  );
  if (shown.length === 0) return null;
  return (
    <section aria-label="Generation jobs" className="space-y-2">
      <h2 className="text-sm font-semibold">Generation jobs</h2>
      {shown.map((j) => (
        <JobProgress
          key={j.id}
          job={j}
          onCancel={async () => {
            await studyApi.cancel(j.id).catch(() => undefined);
            reload();
          }}
        />
      ))}
    </section>
  );
}

function recent(iso: string | null): boolean {
  return iso ? Date.now() - new Date(iso).getTime() < 10 * 60 * 1000 : false;
}

export function StudyLibrary() {
  const { toast } = useToast();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [target, setTarget] = useState<LibraryItem | null>(null);

  const { data, loading, error, reload } = useAsync(
    () =>
      studyApi.list({
        q: q.trim() || undefined,
        resource_type: type || undefined,
        archived: archived || undefined,
        sort_by: "updated_at",
        sort_dir: "desc",
        limit: PAGE_SIZE,
        offset,
      }),
    [q, type, archived, offset],
  );
  const items = data?.data ?? [];

  async function run(action: () => Promise<unknown>, done: string) {
    try {
      await action();
      toast({ title: done });
      reload();
    } catch (err) {
      toast({
        title: "Action failed",
        description: err instanceof ApiRequestError ? err.message : "Something went wrong.",
        variant: "destructive",
      });
    }
  }

  return (
    <div className="space-y-5">
      <nav aria-label="Library sections" className="flex gap-2 text-sm">
        <Link
          href="/library"
          className="text-muted-foreground hover:text-foreground rounded-md px-3 py-1.5 font-medium"
        >
          Documents
        </Link>
        <span
          aria-current="page"
          className="bg-accent text-accent-foreground rounded-md px-3 py-1.5 font-medium"
        >
          Study materials
        </span>
      </nav>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="search"
          aria-label="Search study materials"
          placeholder="Search study materials"
          value={q}
          maxLength={100}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          className="border-input bg-background h-8 min-w-0 flex-1 rounded-lg border px-2.5 text-sm"
        />
        <NativeSelect
          aria-label="Filter by type"
          className="sm:w-48"
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All types</option>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {RESOURCE_LABELS[t]}
            </option>
          ))}
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => {
              setArchived(e.target.checked);
              setOffset(0);
            }}
          />
          Archived
        </label>
        <Button type="button" onClick={() => setGenerating(true)}>
          <Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />
          Generate
        </Button>
      </div>

      <ActiveJobs onFinished={reload} />

      <AsyncSection
        title="Study materials"
        loading={loading}
        error={error}
        onRetry={reload}
        isEmpty={items.length === 0}
        empty={
          <EmptyState
            title={q || type || archived ? "Nothing matches" : "No study materials yet"}
            description={
              q || type || archived
                ? "Try a different search or filter."
                : "Generate a summary, flashcards or a quiz from your documents."
            }
            action={
              q || type || archived ? undefined : (
                <Button type="button" onClick={() => setGenerating(true)}>
                  Generate study material
                </Button>
              )
            }
          />
        }
      >
        <ul className="divide-border border-border divide-y rounded-lg border">
          {items.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <Link
                  href={`/study/${item.id}`}
                  className="text-foreground font-medium break-words underline-offset-2 hover:underline"
                >
                  {item.title}
                </Link>
                <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <Chip>{resourceLabel(item.resource_type)}</Chip>
                  {item.archived_at ? <Chip>Archived</Chip> : null}
                  <span>Updated {formatDate(item.updated_at)}</span>
                  <span>
                    {item.source_document_count}{" "}
                    {item.source_document_count === 1 ? "source" : "sources"}
                  </span>
                  {item.unavailable_source_count > 0 ? (
                    <span className="text-amber-700 dark:text-amber-400">
                      {item.unavailable_source_count} source
                      {item.unavailable_source_count === 1 ? "" : "s"} deleted
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="flex gap-1">
                {!NOT_DUPLICABLE.includes(item.resource_type) ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Duplicate ${item.title}`}
                    onClick={() => run(() => studyApi.duplicate(item.id), "Duplicated")}
                  >
                    <Copy aria-hidden="true" />
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`${item.archived_at ? "Unarchive" : "Archive"} ${item.title}`}
                  onClick={() =>
                    run(
                      () =>
                        item.archived_at ? studyApi.unarchive(item.id) : studyApi.archive(item.id),
                      item.archived_at ? "Restored" : "Archived",
                    )
                  }
                >
                  {item.archived_at ? (
                    <ArchiveRestore aria-hidden="true" />
                  ) : (
                    <Archive aria-hidden="true" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${item.title}`}
                  onClick={() => setTarget(item)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-3">
          <Pager offset={offset} limit={PAGE_SIZE} total={data?.total ?? 0} onChange={setOffset} />
        </div>
      </AsyncSection>

      <GenerateDialog open={generating} onOpenChange={setGenerating} onStarted={() => reload()} />
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(o) => !o && setTarget(null)}
        title="Delete this study material?"
        description={`"${target?.title ?? ""}" and all its versions and exports will be permanently deleted. Your documents are not affected. This cannot be undone.`}
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          const id = target?.id;
          setTarget(null);
          if (id) void run(() => studyApi.remove(id), "Deleted");
        }}
      />
    </div>
  );
}
