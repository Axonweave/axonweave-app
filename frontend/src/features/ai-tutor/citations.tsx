"use client";

import Link from "next/link";
import { FileText } from "lucide-react";
import type { CitationView } from "./sse";

export function locationLabel(c: CitationView): string {
  const parts: string[] = [];
  if (c.page) parts.push(`page ${c.page}`);
  if (c.slide) parts.push(`slide ${c.slide}`);
  return parts.join(", ");
}

/**
 * Sources of a document-grounded answer. Everything shown comes from the database (the server maps
 * the model's [n] markers to retrieved passages); the snippet is rendered as plain text.
 */
export function Citations({ citations }: { citations: CitationView[] }) {
  if (citations.length === 0) return null;
  return (
    <section aria-label="Sources" className="mt-3 space-y-1">
      <h3 className="text-muted-foreground text-xs font-medium">Sources</h3>
      <ol className="space-y-1">
        {citations.map((c) => (
          <li
            key={`${c.rank}-${c.id ?? c.documentName}`}
            className="border-border rounded-md border text-xs"
          >
            <details>
              <summary className="flex cursor-pointer items-center gap-2 px-2 py-1.5">
                <span className="bg-muted rounded px-1.5 font-medium">[{c.rank}]</span>
                <FileText className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1 break-words">
                  {c.documentName}
                  {locationLabel(c) ? ` · ${locationLabel(c)}` : ""}
                </span>
                {!c.available && <span className="text-muted-foreground">Source deleted</span>}
              </summary>
              <div className="border-border space-y-2 border-t px-2 py-2">
                {c.heading && <p className="text-muted-foreground">{c.heading}</p>}
                {c.snippet ? (
                  <p className="break-words whitespace-pre-wrap">{c.snippet}</p>
                ) : (
                  <p className="text-muted-foreground">
                    {c.available ? "No preview available." : "The original document was deleted."}
                  </p>
                )}
                {c.available && c.documentId && (
                  <Link href={documentHref(c)} className="text-primary underline">
                    Open document
                  </Link>
                )}
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Opens the document on the cited page; `source` lets the PDF viewer mark the cited passage. */
export function documentHref(c: CitationView): string {
  const q = new URLSearchParams();
  if (c.page) q.set("page", String(c.page));
  if (c.chunkId) q.set("source", c.chunkId);
  const qs = q.toString();
  return `/documents/${c.documentId}${qs ? `?${qs}` : ""}`;
}
