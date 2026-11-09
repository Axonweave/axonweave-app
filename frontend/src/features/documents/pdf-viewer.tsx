"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { documentsApi } from "@/lib/api/documents";

// Minimal shapes of the pdf.js objects used here (the library is loaded on demand, client-side).
interface PdfPage {
  getViewport: (o: { scale: number }) => { width: number; height: number };
  render: (o: { canvas: HTMLCanvasElement; viewport: unknown }) => { promise: Promise<void> };
  getTextContent: () => Promise<{ items: Array<{ str?: string }> }>;
}
interface PdfDoc {
  numPages: number;
  getPage: (n: number) => Promise<PdfPage>;
  destroy: () => Promise<void>;
}

/** A passage rectangle: PDF points, origin top-left (as stored by the extractor). */
export interface Region {
  page: number;
  bbox: number[];
}

export function regionsOnPage(regions: Region[], page: number): Region[] {
  return regions.filter((r) => r.page === page && r.bbox.length === 4);
}

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;

/** Pages whose text contains `term`. Runs in the browser on the user's own document. */
export interface TextSource {
  numPages: number;
  getPage: (n: number) => Promise<Pick<PdfPage, "getTextContent">>;
}

export async function findPages(doc: TextSource, term: string) {
  const needle = term.trim().toLowerCase();
  if (!needle) return [];
  const hits: number[] = [];
  for (let n = 1; n <= doc.numPages; n += 1) {
    const content = await (await doc.getPage(n)).getTextContent();
    const text = content.items.map((i) => i.str ?? "").join(" ");
    if (text.toLowerCase().includes(needle)) hits.push(n);
  }
  return hits;
}

/**
 * PDF viewer (D-72): bytes come from the owner-only inline endpoint and are rendered to a canvas by
 * pdf.js in a worker. No iframe, no storage URL. `initialPage` lets a citation open on its page.
 */
export function PdfViewer({
  documentId,
  initialPage = 1,
  regions = [],
}: {
  documentId: string;
  initialPage?: number;
  regions?: Region[];
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [doc, setDoc] = useState<PdfDoc | null>(null);
  const [page, setPage] = useState(initialPage);
  const [zoom, setZoom] = useState(1.2);
  const [error, setError] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [hits, setHits] = useState<number[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    let loaded: PdfDoc | null = null;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        const response = await fetch(documentsApi.inlineUrl(documentId), {
          credentials: "include",
        });
        if (!response.ok) throw new Error("fetch");
        const data = new Uint8Array(await response.arrayBuffer());
        loaded = (await pdfjs.getDocument({ data }).promise) as unknown as PdfDoc;
        if (cancelled) return void loaded.destroy();
        setDoc(loaded);
        setPage((p) => Math.min(Math.max(1, p), loaded!.numPages));
      } catch {
        if (!cancelled) setError("The PDF could not be shown. You can still read the text below.");
      }
    })();
    return () => {
      cancelled = true;
      void loaded?.destroy();
    };
  }, [documentId]);

  useEffect(() => {
    if (!doc || !canvas.current) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await doc.getPage(page);
        const viewport = p.getViewport({ scale: zoom });
        const el = canvas.current;
        if (!el || cancelled) return;
        el.width = Math.floor(viewport.width);
        el.height = Math.floor(viewport.height);
        await p.render({ canvas: el, viewport }).promise;
      } catch {
        /* a superseded render is cancelled by pdf.js; nothing to show */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [doc, page, zoom]);

  const go = useCallback(
    (n: number) => doc && setPage(Math.min(Math.max(1, n), doc.numPages)),
    [doc],
  );

  if (error) {
    return (
      <p role="alert" className="text-muted-foreground text-sm">
        {error}
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="PDF controls">
        <Button
          variant="outline"
          size="sm"
          disabled={!doc || page <= 1}
          onClick={() => go(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <label className="flex items-center gap-1 text-sm">
          Page
          <input
            type="number"
            min={1}
            max={doc?.numPages ?? 1}
            value={page}
            onChange={(e) => go(Number(e.target.value) || 1)}
            className="border-input bg-background h-8 w-16 rounded-md border px-2"
            aria-label="Page number"
          />
          <span className="text-muted-foreground">of {doc?.numPages ?? "…"}</span>
        </label>
        <Button
          variant="outline"
          size="sm"
          disabled={!doc || page >= (doc?.numPages ?? 1)}
          onClick={() => go(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - 0.2).toFixed(1)))}
          aria-label="Zoom out"
        >
          <ZoomOut className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setZoom((z) => Math.min(MAX_ZOOM, +(z + 0.2).toFixed(1)))}
          aria-label="Zoom in"
        >
          <ZoomIn className="h-4 w-4" aria-hidden="true" />
        </Button>
        <form
          className="flex items-center gap-1"
          onSubmit={async (e) => {
            e.preventDefault();
            if (doc) setHits(await findPages(doc, term));
          }}
        >
          <input
            type="search"
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setHits(null);
            }}
            placeholder="Find in document"
            aria-label="Find in document"
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          />
          <Button type="submit" variant="outline" size="sm" disabled={!doc || !term.trim()}>
            Find
          </Button>
        </form>
      </div>
      {hits !== null && (
        <p className="text-sm" aria-live="polite">
          {hits.length === 0 ? (
            "No matches."
          ) : (
            <>
              Found on pages:{" "}
              {hits.map((n) => (
                <button
                  key={n}
                  type="button"
                  className="text-primary mr-2 underline"
                  onClick={() => go(n)}
                >
                  {n}
                </button>
              ))}
            </>
          )}
        </p>
      )}
      <div className="border-border max-h-[70vh] overflow-auto rounded-md border">
        <div className="relative inline-block">
          <canvas ref={canvas} aria-label={`Page ${page} of the document`} role="img" />
          {regionsOnPage(regions, page).map((r, i) => (
            <div
              key={i}
              data-testid="cited-region"
              aria-hidden="true"
              className="pointer-events-none absolute rounded-sm bg-yellow-300/40 ring-1 ring-yellow-500"
              style={{
                left: r.bbox[0] * zoom,
                top: r.bbox[1] * zoom,
                width: (r.bbox[2] - r.bbox[0]) * zoom,
                height: (r.bbox[3] - r.bbox[1]) * zoom,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
