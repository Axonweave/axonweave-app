"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download } from "lucide-react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { formatDate } from "@/lib/activity";
import { documentsApi, errorText } from "@/lib/api/documents";
import { StatusBadge, formatBytes } from "./status-badge";
import { useStatusPolling } from "./use-status-polling";

const PAGE_SIZE = 20;

/**
 * Document detail: metadata, processing info and the extracted text by page or slide. The text is
 * the user's own extracted content, rendered as plain text (never as HTML). `highlightChunk` marks
 * a passage opened from a citation.
 */
export function DocumentDetail({
  documentId,
  highlightChunk,
}: {
  documentId: string;
  highlightChunk?: number;
}) {
  const [offset, setOffset] = useState(0);
  const [part, setPart] = useState<number | null>(null);

  const doc = useAsync(() => documentsApi.get(documentId), [documentId]);
  const details = useAsync(() => documentsApi.processing(documentId), [documentId]);
  useStatusPolling(doc.data ? [doc.data.processing_status] : [], () => {
    doc.reload();
    details.reload();
  });
  const ready = doc.data?.processing_status === "completed";
  const pages = useAsync(
    () => (ready ? documentsApi.pages(documentId) : Promise.resolve([])),
    [documentId, ready],
  );
  const isSlides = (pages.data ?? [])[0]?.kind === "slide";
  const content = useAsync(
    () =>
      ready
        ? documentsApi.content(documentId, {
            ...(part ? (isSlides ? { slide: part } : { page: part }) : {}),
            offset,
          })
        : Promise.resolve({ data: [], total: 0 }),
    [documentId, ready, part, offset, isSlides],
  );

  const d = doc.data;
  const p = details.data;
  const failure = p?.jobs.find((j) => j.error_code)?.error_code;

  return (
    <div className="min-w-0 space-y-6">
      <Link
        href="/library"
        className="text-muted-foreground inline-flex items-center gap-1 text-sm hover:underline"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Library
      </Link>
      <AsyncSection
        title={d?.display_name ?? "Document"}
        loading={doc.loading && !d}
        error={doc.error}
        onRetry={doc.reload}
        isEmpty={!d}
        empty={null}
        action={d ? <StatusBadge status={d.processing_status} /> : undefined}
      >
        {d && (
          <div className="space-y-4">
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <Meta label="Type" value={d.file_type.toUpperCase()} />
              <Meta label="Size" value={formatBytes(d.file_size)} />
              <Meta label="Uploaded" value={formatDate(d.created_at)} />
              <Meta label="Version" value={String(d.active_version ?? d.latest_version)} />
              {p?.page_count != null && <Meta label="Pages" value={String(p.page_count)} />}
              {p?.slide_count != null && <Meta label="Slides" value={String(p.slide_count)} />}
              {p?.word_count != null && <Meta label="Words" value={String(p.word_count)} />}
              {p?.extraction_method && <Meta label="Read with" value={p.extraction_method} />}
              {p?.ocr_used && (
                <Meta
                  label="OCR"
                  value={
                    p.ocr_mean_confidence != null
                      ? `Used (confidence ${Math.round(p.ocr_mean_confidence)}%)`
                      : "Used"
                  }
                />
              )}
            </dl>
            {p && p.warnings.length > 0 && (
              <ul className="text-muted-foreground list-disc pl-5 text-sm">
                {p.warnings.map((w) => (
                  <li key={w}>{warningText(w)}</li>
                ))}
              </ul>
            )}
            {d.processing_status === "failed" && (
              <p role="alert" className="text-destructive text-sm">
                {errorText(failure)}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <a
                href={documentsApi.downloadUrl(d.id)}
                className="inline-flex"
                download
                aria-label={`Download original ${d.display_name}`}
              >
                <Button variant="outline" size="sm" type="button">
                  <Download className="mr-1 h-4 w-4" aria-hidden="true" />
                  Download original
                </Button>
              </a>
              {d.processing_status === "failed" && (
                <Button
                  size="sm"
                  type="button"
                  onClick={() => documentsApi.retry(d.id).then(() => doc.reload())}
                >
                  Retry processing
                </Button>
              )}
            </div>
          </div>
        )}
      </AsyncSection>

      {ready && (
        <AsyncSection
          title="Extracted text"
          loading={content.loading && !content.data}
          error={content.error}
          onRetry={content.reload}
          isEmpty={(content.data?.data.length ?? 0) === 0}
          empty={<p className="text-muted-foreground text-sm">No text to show.</p>}
          action={
            (pages.data?.length ?? 0) > 1 ? (
              <select
                aria-label={isSlides ? "Jump to slide" : "Jump to page"}
                className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                value={part ?? ""}
                onChange={(e) => {
                  setOffset(0);
                  setPart(e.target.value ? Number(e.target.value) : null);
                }}
              >
                <option value="">{isSlides ? "All slides" : "All pages"}</option>
                {(pages.data ?? []).map((pg) => (
                  <option key={pg.number} value={pg.number}>
                    {isSlides ? "Slide" : "Page"} {pg.number}
                  </option>
                ))}
              </select>
            ) : undefined
          }
        >
          <ol className="space-y-3">
            {(content.data?.data ?? []).map((c) => (
              <li
                key={c.chunk_index}
                id={`chunk-${c.chunk_index}`}
                className={`border-border rounded-md border p-3 ${
                  highlightChunk === c.chunk_index ? "bg-muted ring-primary ring-2" : ""
                }`}
              >
                <p className="text-muted-foreground mb-1 text-xs">
                  {c.page_number
                    ? `Page ${c.page_number}`
                    : c.slide_number
                      ? `Slide ${c.slide_number}`
                      : ""}
                  {c.section_heading ? ` · ${c.section_heading}` : ""}
                </p>
                <p className="text-sm break-words whitespace-pre-wrap">{c.text}</p>
              </li>
            ))}
          </ol>
        </AsyncSection>
      )}
      {ready && (
        <Pager
          offset={offset}
          limit={PAGE_SIZE}
          total={content.data?.total ?? 0}
          onChange={setOffset}
        />
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

const WARNINGS: Record<string, string> = {
  OCR_USED: "Some text was read with OCR and may contain mistakes.",
  TEXT_TRUNCATED: "This document was very long, so only the first part was indexed.",
  EMBEDDINGS_UNAVAILABLE:
    "Semantic search was unavailable when this was indexed; keyword search still works.",
};
export const warningText = (code: string) => WARNINGS[code] ?? "Processing note.";
