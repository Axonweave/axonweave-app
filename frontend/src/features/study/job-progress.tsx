"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { explainError, isJobDone, resourceLabel, type GenerationJob } from "@/lib/api/study";

const STATUS_TEXT: Record<string, string> = {
  pending: "Waiting to start",
  retrieving_sources: "Reading your sources",
  generating: "Generating",
  validating: "Checking the result",
  saving: "Saving",
  completed: "Finished",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function JobProgress({
  job,
  onCancel,
  showLink = true,
}: {
  job: GenerationJob;
  onCancel?: () => void;
  showLink?: boolean;
}) {
  const done = isJobDone(job.status);
  return (
    <div className="border-border space-y-2 rounded-lg border p-3" data-testid="job-progress">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {resourceLabel(job.generation_type)} · {STATUS_TEXT[job.status] ?? job.status}
        </p>
        {!done && onCancel ? (
          <Button variant="outline" size="sm" type="button" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
      {!done ? (
        <div className="flex items-center gap-2">
          <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" aria-hidden="true" />
          <div
            role="progressbar"
            aria-label="Generation progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={job.progress}
            className="bg-muted h-2 flex-1 overflow-hidden rounded"
          >
            <div className="bg-primary h-full" style={{ width: `${job.progress}%` }} />
          </div>
        </div>
      ) : null}
      {job.status === "failed" ? (
        <p role="alert" className="text-destructive text-sm">
          {explainError(job.error_code, job.error_message)}
        </p>
      ) : null}
      {job.status === "completed" && job.study_material_id && showLink ? (
        <Link
          className="text-primary text-sm underline underline-offset-2"
          href={`/study/${job.study_material_id}`}
        >
          Open the result
        </Link>
      ) : null}
    </div>
  );
}
