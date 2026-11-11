"use client";

import Link from "next/link";
import { FileText } from "lucide-react";
import type { MaterialSource } from "@/lib/api/study";

/**
 * Source references: the numbers stored on generated items map to the material's own source
 * list (chunk -> document and page). A document deleted later shows as "unavailable" rather than
 * a broken link.
 */
export function SourceRefs({
  refs,
  sources,
  unavailable = [],
}: {
  refs?: number[] | null;
  sources: MaterialSource[];
  unavailable?: string[];
}) {
  const items = (refs ?? [])
    .map((n) => sources.find((s) => s.rank === n))
    .filter((s): s is MaterialSource => Boolean(s));
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Sources">
      {items.map((s) => {
        const label = s.page_number
          ? `Page ${s.page_number}`
          : s.slide_number
            ? `Slide ${s.slide_number}`
            : s.kind === "text"
              ? "Pasted text"
              : "Document";
        const gone = s.document_id ? unavailable.includes(s.document_id) : false;
        const params = new URLSearchParams();
        if (s.page_number) params.set("page", String(s.page_number));
        const qs = params.toString();
        return (
          <li key={s.rank}>
            {s.document_id && !gone ? (
              <Link
                href={`/documents/${s.document_id}${qs ? `?${qs}` : ""}`}
                className="bg-muted text-muted-foreground hover:text-foreground inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs underline-offset-2 hover:underline"
              >
                <FileText className="h-3 w-3" aria-hidden="true" />[{s.rank}] {label}
              </Link>
            ) : (
              <span className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs">
                [{s.rank}] {gone ? "Source unavailable" : label}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
