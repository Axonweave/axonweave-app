"use client";

import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  CITATION_STYLES,
  researchApi,
  type CitationStyle,
  type ResearchCitation,
  type ResearchProject,
} from "@/lib/api/research";
import { downloadText } from "./download";

const CARD = "border-border bg-card rounded-lg border p-4";
const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";

const SEVERITY_LABELS: Record<string, string> = {
  missing: "Missing",
  warning: "Check",
  info: "Note",
};

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

function CitationRow({
  item,
  readOnly,
  onRegenerate,
  onDelete,
}: {
  item: ResearchCitation;
  readOnly: boolean;
  onRegenerate: () => void;
  onDelete: () => void;
}) {
  const { toast } = useToast();

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast({ title: `${what} copied` });
    } catch {
      toast({ title: "Could not copy", variant: "destructive" });
    }
  }

  const blocking = item.issues.filter((i) => i.severity !== "info");
  const notes = item.issues.filter((i) => i.severity === "info");
  return (
    <li className={`${CARD} space-y-2`} aria-label={item.paper_title}>
      <p className="text-sm">{item.formatted_citation}</p>
      <p className="text-muted-foreground text-xs">
        In text: <span className="text-foreground">{item.in_text_citation}</span>
      </p>
      {item.metadata_changed && (
        <p className="text-sm text-amber-700 dark:text-amber-400" role="status">
          The paper&apos;s details changed after this citation was made.
          {!readOnly && " Regenerate it to use the current details."}
        </p>
      )}
      {blocking.length > 0 && (
        <ul className="space-y-0.5 text-sm" aria-label="Metadata problems">
          {blocking.map((i) => (
            <li key={`${i.code}-${i.message}`}>
              <span className="font-medium">{SEVERITY_LABELS[i.severity] ?? i.severity}: </span>
              {i.message}
            </li>
          ))}
        </ul>
      )}
      {notes.length > 0 && (
        <ul className="text-muted-foreground space-y-0.5 text-xs">
          {notes.map((i) => (
            <li key={`${i.code}-${i.message}`}>{i.message}</li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => copy(item.formatted_citation, "Citation")}
        >
          Copy citation
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => copy(item.in_text_citation, "In-text citation")}
        >
          Copy in-text
        </Button>
        {!readOnly && (
          <>
            <Button size="sm" variant="outline" onClick={onRegenerate}>
              Regenerate
            </Button>
            <Button size="sm" variant="outline" onClick={onDelete}>
              Remove
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

export function CitationsWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const [style, setStyle] = useState<CitationStyle>("apa");
  const [busy, setBusy] = useState(false);
  const list = useAsync(() => researchApi.listCitations(project.id, style), [project.id, style]);

  async function run(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    try {
      await action();
      list.reload();
    } catch (e) {
      toast({ title: failure, description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function exportBib(format: "text" | "bibtex") {
    try {
      const bib = await researchApi.bibliography(project.id, style, format);
      if (bib.count === 0) {
        toast({ title: "Nothing to export", description: "Generate citations first." });
        return;
      }
      downloadText(bib.filename, bib.content, "text/plain;charset=utf-8");
    } catch (e) {
      toast({ title: "Could not export", description: errorText(e), variant: "destructive" });
    }
  }

  const items = list.data ?? [];
  return (
    <section aria-label="Citations" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Citations</h2>
      <div className={`${CARD} space-y-3`}>
        <p className="text-muted-foreground text-sm">
          Citations are formatted from each paper&apos;s recorded details. Missing details are
          listed, never filled in.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="text-muted-foreground block">Style</span>
            <select
              className={SELECT}
              value={style}
              onChange={(e) => setStyle(e.target.value as CitationStyle)}
            >
              {CITATION_STYLES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          {!readOnly && (
            <Button
              disabled={busy}
              onClick={() =>
                run(
                  () => researchApi.generateCitations(project.id, { style }),
                  "Could not generate",
                )
              }
            >
              {busy ? "Working…" : "Generate for all papers"}
            </Button>
          )}
          <Button variant="outline" onClick={() => exportBib("text")}>
            Export bibliography
          </Button>
          <Button variant="outline" onClick={() => exportBib("bibtex")}>
            Export BibTeX
          </Button>
        </div>
      </div>
      <AsyncSection
        title="References"
        loading={list.loading}
        error={list.error}
        onRetry={list.reload}
        isEmpty={items.length === 0}
        empty={
          <p className="text-muted-foreground text-sm">
            No citations in this style yet. Add papers to the library, then generate.
          </p>
        }
      >
        <ul className="space-y-3">
          {items.map((c) => (
            <CitationRow
              key={c.id}
              item={c}
              readOnly={readOnly}
              onRegenerate={() =>
                run(
                  () =>
                    researchApi.generateCitations(project.id, {
                      style,
                      paper_ids: [c.research_paper_id],
                    }),
                  "Could not regenerate",
                )
              }
              onDelete={() => run(() => researchApi.deleteCitation(c.id), "Could not remove")}
            />
          ))}
        </ul>
      </AsyncSection>
    </section>
  );
}
