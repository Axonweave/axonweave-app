"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { ApiRequestError } from "@/lib/api/client";
import { materialParts, studyApi, type StudyMaterial } from "@/lib/api/study";
import { JobProgress } from "./job-progress";
import { renderBody } from "./render-body";
import { useJob } from "./use-job";

/**
 * Regeneration never overwrites anything (D-92): the new text is shown here next to the current
 * version and only replaces it when the user applies it. A preview made before a later edit is
 * refused by the server (PREVIEW_STALE), so an edit is never lost.
 */
export function RegenerationReview({
  material,
  jobId,
  section,
  onClose,
}: {
  material: StudyMaterial;
  jobId: string;
  section: number | null;
  onClose: (applied: boolean) => void;
}) {
  const { job, error, cancel } = useJob(jobId);
  const preview = useAsync(
    () => (job?.status === "completed" ? studyApi.preview(jobId) : Promise.resolve(null)),
    [job?.status, jobId],
  );
  const [message, setMessage] = useState<string | null>(null);
  const data = preview.data;
  const next = data
    ? materialParts<Record<string, unknown>>({ ...material, content: data.content })
    : null;
  const current = materialParts<Record<string, unknown>>(material);

  async function apply() {
    setMessage(null);
    try {
      await studyApi.applyPreview(jobId);
      onClose(true);
    } catch (err) {
      setMessage(
        err instanceof ApiRequestError && err.code === "PREVIEW_STALE"
          ? "You edited this material after starting the regeneration, so the new version was not applied. Your edits are safe."
          : err instanceof ApiRequestError
            ? err.message
            : "Could not apply the new version.",
      );
    }
  }

  const sectionOf = (payload: Record<string, unknown>) => {
    if (section === null) return payload;
    const sections = (payload.sections as unknown[] | undefined) ?? [];
    return { ...payload, sections: sections[section] ? [sections[section]] : sections };
  };

  return (
    <section
      aria-label="Regeneration preview"
      className="border-border space-y-3 rounded-lg border p-3"
      data-testid="regeneration-review"
    >
      <h2 className="text-sm font-semibold">
        {section === null
          ? "Regenerated version (preview)"
          : `Regenerated section ${section + 1} (preview)`}
      </h2>
      <p className="text-muted-foreground text-xs">
        Nothing is replaced until you choose to apply it. Compare it with what you have now.
      </p>
      {job && job.status !== "completed" ? (
        <JobProgress job={job} onCancel={cancel} showLink={false} />
      ) : null}
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      {data && next ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="min-w-0">
            <h3 className="mb-2 text-sm font-medium">
              Current (version {material.current_version})
            </h3>
            {renderBody(
              material,
              section === null ? current.payload : sectionOf(current.payload),
              current.sources,
            )}
          </div>
          <div className="min-w-0">
            <h3 className="mb-2 text-sm font-medium">New</h3>
            {renderBody(material, next.payload, next.sources)}
          </div>
        </div>
      ) : null}
      {data?.stale ? (
        <p role="alert" className="text-sm text-amber-700 dark:text-amber-400">
          This material was edited after the preview was made, so it can no longer be applied.
        </p>
      ) : null}
      {message ? (
        <p role="alert" className="text-destructive text-sm">
          {message}
        </p>
      ) : null}
      <div className="flex gap-2">
        {job?.status === "completed" ? (
          <Button type="button" onClick={apply} disabled={!data || data.stale}>
            Apply the new version
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          onClick={async () => {
            if (job?.status === "completed")
              await studyApi.discardPreview(jobId).catch(() => undefined);
            onClose(false);
          }}
        >
          {job?.status === "completed" ? "Discard" : "Close"}
        </Button>
      </div>
    </section>
  );
}
