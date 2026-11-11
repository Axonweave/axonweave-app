"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api/client";
import { studyApi, type StudyExport } from "@/lib/api/study";
import { NativeSelect } from "./ui-bits";

type Format = "pdf" | "csv" | "md" | "docx";

/** Formats the backend supports per resource type (D-100). */
export const EXPORT_FORMATS: Record<string, Format[]> = {
  summary: ["pdf", "docx", "md"],
  study_guide: ["pdf", "docx", "md"],
  flashcards: ["csv", "pdf"],
  glossary: ["csv", "pdf"],
  question_bank: ["csv", "pdf"],
  quiz: ["pdf"],
  formula_sheet: ["pdf"],
};

const LABEL: Record<Format, string> = {
  pdf: "PDF",
  csv: "CSV",
  md: "Markdown",
  docx: "Word (DOCX)",
};
const POLL_MS = 2000;
const ERRORS: Record<string, string> = {
  EXPORT_RATE_LIMITED: "You have made too many exports. Try again in a while.",
  EXPORT_UNAVAILABLE: "Exports are not available right now.",
  EXPORT_FORMAT_UNSUPPORTED: "That format is not available for this material.",
  EXPORT_RENDER_FAILED: "The export could not be created. Try again.",
  EXPORT_EXPIRED: "This download link has expired. Export again.",
};

export function ExportMenu({
  materialId,
  resourceType,
}: {
  materialId: string;
  resourceType: string;
}) {
  const formats = EXPORT_FORMATS[resourceType] ?? [];
  const [format, setFormat] = useState<Format | "">(formats[0] ?? "");
  const [record, setRecord] = useState<StudyExport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pending =
    record !== null && (record.status === "pending" || record.status === "processing");
  const exportId = record?.id;
  useEffect(() => {
    if (!pending || !exportId) return;
    const timer = window.setInterval(async () => {
      try {
        setRecord(await studyApi.exportStatus(exportId));
      } catch {
        setError("Could not read the export status.");
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [pending, exportId]);

  if (formats.length === 0) return null;

  async function start() {
    if (!format) return;
    setBusy(true);
    setError(null);
    setRecord(null);
    try {
      setRecord(await studyApi.requestExport(materialId, format));
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? (ERRORS[err.code] ?? err.message)
          : "Could not start the export.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="export-menu">
      <NativeSelect
        aria-label="Export format"
        className="w-40"
        value={format}
        onChange={(e) => {
          setFormat(e.target.value as Format);
          setRecord(null);
        }}
      >
        {formats.map((f) => (
          <option key={f} value={f}>
            {LABEL[f]}
          </option>
        ))}
      </NativeSelect>
      <Button type="button" variant="outline" onClick={start} disabled={busy || pending}>
        <Download aria-hidden="true" />
        {pending ? "Preparing…" : "Export"}
      </Button>
      {record?.status === "completed" ? (
        <a
          className={buttonVariants({ variant: "default" })}
          href={studyApi.downloadUrl(record.id)}
          download
        >
          Download {LABEL[record.format as Format] ?? record.format}
        </a>
      ) : null}
      {record?.status === "failed" ? (
        <span role="alert" className="text-destructive text-sm">
          {ERRORS[record.error_code ?? ""] ?? "The export failed."}
        </span>
      ) : null}
      {record?.status === "expired" ? (
        <span role="alert" className="text-destructive text-sm">
          {ERRORS.EXPORT_EXPIRED}
        </span>
      ) : null}
      {record?.status === "completed" ? (
        <span className="text-muted-foreground text-xs">The link works for about an hour.</span>
      ) : null}
      {error ? (
        <span role="alert" className="text-destructive text-sm">
          {error}
        </span>
      ) : null}
    </div>
  );
}
