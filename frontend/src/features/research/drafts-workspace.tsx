"use client";

import { useMemo, useRef, useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  CHECK_STATUS_LABELS,
  DRAFT_STATUS_LABELS,
  DRAFT_TYPE_LABELS,
  CITATION_STYLES,
  WRITING_ACTION_LABELS,
  WRITING_SECTION_LABELS,
  citeMarker,
  researchApi,
  type DraftCheck,
  type DraftPatch,
  type DraftSummary,
  type DraftVersion,
  type DraftVersionSummary,
  type ResearchDraft,
  type ResearchProject,
  type WritingRequest,
  type WritingSuggestion,
} from "@/lib/api/research";
import { downloadText } from "./download";

const CARD = "border-border bg-card rounded-lg border p-4";
const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";
const MARKER = /\{\{cite:([0-9a-fA-F-]{36})\}\}/g;
const EDIT_ACTIONS = ["rewrite", "tone", "grammar", "clarity", "organise", "expand"];

function errorText(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : "Something went wrong. Try again.";
}

type Paper = { id: string; title: string };

function Editor({
  initial,
  papers,
  readOnly,
  onChanged,
  onClosed,
}: {
  initial: ResearchDraft;
  papers: Paper[];
  readOnly: boolean;
  onChanged: () => void;
  onClosed: () => void;
}) {
  const { toast } = useToast();
  const area = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState(initial);
  const [title, setTitle] = useState(initial.title);
  const [content, setContent] = useState(initial.content);
  const [sel, setSel] = useState<[number, number]>([0, 0]);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [citePaper, setCitePaper] = useState("");
  const [versions, setVersions] = useState<DraftVersionSummary[] | null>(null);
  const [viewed, setViewed] = useState<DraftVersion | null>(null);
  const [check, setCheck] = useState<DraftCheck | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [action, setAction] = useState<WritingRequest["action"]>("draft_section");
  const [section, setSection] = useState<string>("introduction");
  const [instruction, setInstruction] = useState("");
  const [suggestion, setSuggestion] = useState<WritingSuggestion | null>(null);

  const dirty = title !== draft.title || content !== draft.content;
  const titles = useMemo(() => Object.fromEntries(papers.map((p) => [p.id, p.title])), [papers]);
  const cited = useMemo(
    () => [...new Set([...content.matchAll(MARKER)].map((m) => m[1].toLowerCase()))],
    [content],
  );
  const selected = content.slice(sel[0], sel[1]);

  async function save(
    source: "manual" | "ai_suggestion",
    next?: { content: string },
    note?: string,
  ) {
    setBusy(true);
    try {
      const saved = await researchApi.patchDraft(draft.id, {
        title,
        content: next?.content ?? content,
        expected_version: draft.version_number,
        change_source: source,
        change_summary: note,
      });
      setDraft(saved);
      setTitle(saved.title);
      setContent(saved.content);
      setConflict(false);
      setCheck(null);
      setVersions(null);
      onChanged();
    } catch (e) {
      if (e instanceof ApiRequestError && e.code === "RESEARCH_DRAFT_VERSION_CONFLICT") {
        setConflict(true);
      }
      toast({ title: "Could not save", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function reload() {
    try {
      const fresh = await researchApi.getDraft(draft.id);
      setDraft(fresh);
      setTitle(fresh.title);
      setContent(fresh.content);
      setConflict(false);
      setVersions(null);
    } catch (e) {
      toast({ title: "Could not reload", description: errorText(e), variant: "destructive" });
    }
  }

  async function meta(patch: Parameters<typeof researchApi.patchDraft>[1]) {
    try {
      setDraft(await researchApi.patchDraft(draft.id, patch));
      onChanged();
    } catch (e) {
      toast({ title: "Could not update", description: errorText(e), variant: "destructive" });
    }
  }

  function insert(text: string) {
    const [a, b] = sel;
    setContent((c) => c.slice(0, a) + text + c.slice(b));
    setSel([a + text.length, a + text.length]);
  }

  async function run<T>(job: () => Promise<T>, failure: string): Promise<T | undefined> {
    setBusy(true);
    try {
      return await job();
    } catch (e) {
      toast({ title: failure, description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    const body: WritingRequest = {
      action,
      section: section as WritingRequest["section"],
      instruction,
      selected_text: selected,
    };
    const out = await run(() => researchApi.assistDraft(draft.id, body), "AI assistance failed");
    if (out) setSuggestion(out);
  }

  async function accept(mode: "replace" | "insert" | "append") {
    if (!suggestion) return;
    const [a, b] = sel;
    const next =
      mode === "replace"
        ? content.slice(0, a) + suggestion.text + content.slice(b)
        : mode === "insert"
          ? content.slice(0, a) + suggestion.text + content.slice(a)
          : content.replace(/\s*$/, "") + "\n\n" + suggestion.text;
    await save(
      "ai_suggestion",
      { content: next },
      `AI suggestion accepted: ${WRITING_ACTION_LABELS[suggestion.action]}`,
    );
    setSuggestion(null);
  }

  async function exportMarkdown() {
    const out = await run(() => researchApi.exportDraft(draft.id), "Could not export");
    if (out) downloadText(out.filename, out.content, "text/markdown;charset=utf-8");
  }

  const flagged = suggestion?.checks.filter((c) =>
    ["unsupported", "citation_mismatch", "invalid_reference", "cannot_verify"].includes(c.status),
  );

  return (
    <div className={`${CARD} space-y-4`} aria-label="Draft editor">
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-[14rem] flex-1 text-sm">
          <span className="text-muted-foreground">Title</span>
          <input
            className={FIELD}
            value={title}
            maxLength={200}
            disabled={readOnly}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block">Status</span>
          <select
            className={SELECT}
            value={draft.status}
            disabled={readOnly}
            onChange={(e) => meta({ status: e.target.value as DraftPatch["status"] })}
          >
            {Object.entries(DRAFT_STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block">Citation style</span>
          <select
            className={SELECT}
            value={draft.citation_style}
            disabled={readOnly}
            onChange={(e) =>
              meta({ citation_style: e.target.value as DraftPatch["citation_style"] })
            }
          >
            {CITATION_STYLES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <Button variant="outline" onClick={onClosed}>
          Close
        </Button>
      </div>

      {conflict && (
        <p role="alert" className="text-destructive text-sm">
          This draft was changed elsewhere, so your save was refused.{" "}
          <button className="underline" onClick={reload}>
            Reload the saved version
          </button>{" "}
          (your unsaved text stays here until you do).
        </p>
      )}

      {!readOnly && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="text-muted-foreground block">Insert a citation</span>
            <select
              className={SELECT}
              value={citePaper}
              onChange={(e) => setCitePaper(e.target.value)}
            >
              <option value="">Choose a paper…</option>
              {papers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <Button
            size="sm"
            variant="outline"
            disabled={!citePaper}
            onClick={() => insert(citeMarker(citePaper))}
          >
            Insert citation
          </Button>
          <label className="text-sm">
            <span className="text-muted-foreground block">Insert a heading</span>
            <select
              className={SELECT}
              value=""
              onChange={(e) => {
                if (e.target.value) insert(`\n## ${WRITING_SECTION_LABELS[e.target.value]}\n\n`);
              }}
            >
              <option value="">Choose a section…</option>
              {Object.entries(WRITING_SECTION_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <label className="block text-sm">
        <span className="text-muted-foreground">
          Content (Markdown; a citation appears as {"{{cite:…}}"})
        </span>
        <textarea
          ref={area}
          className={`${FIELD} min-h-[18rem] font-mono`}
          value={content}
          readOnly={readOnly}
          onChange={(e) => setContent(e.target.value)}
          onSelect={(e) => {
            const t = e.currentTarget;
            setSel([t.selectionStart, t.selectionEnd]);
          }}
        />
      </label>

      {cited.length > 0 && (
        <div className="text-sm">
          <p className="font-medium">Citations in this draft</p>
          <ul className="text-muted-foreground list-disc pl-5">
            {cited.map((id) => (
              <li key={id}>{titles[id] ?? "A paper that is not in this project"}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {!readOnly && (
          <Button disabled={busy || !dirty || title.trim() === ""} onClick={() => save("manual")}>
            {dirty ? "Save new version" : "Saved"}
          </Button>
        )}
        <Button
          variant="outline"
          disabled={busy || dirty}
          onClick={async () =>
            setCheck((await run(() => researchApi.checkDraft(draft.id), "Check failed")) ?? null)
          }
        >
          Check evidence
        </Button>
        <Button variant="outline" disabled={busy || dirty} onClick={exportMarkdown}>
          Export Markdown
        </Button>
        <Button
          variant="outline"
          onClick={async () =>
            setVersions(
              (await run(() => researchApi.draftVersions(draft.id), "Could not load history")) ??
                null,
            )
          }
        >
          Version history
        </Button>
        {!readOnly && (
          <Button variant="outline" onClick={() => setConfirmDelete(true)}>
            Delete draft
          </Button>
        )}
      </div>
      {dirty && (
        <p className="text-muted-foreground text-xs">
          Save before checking evidence or exporting. Version {draft.version_number} is the latest
          saved.
        </p>
      )}

      {check && (
        <div className="space-y-2" aria-label="Evidence check">
          <p className="text-sm font-medium">
            Evidence check:{" "}
            {Object.entries(check.summary)
              .filter(([, n]) => n > 0)
              .map(([k, n]) => `${n} ${CHECK_STATUS_LABELS[k]?.toLowerCase() ?? k}`)
              .join("; ") || "nothing to check"}
          </p>
          {check.invalid_references.length > 0 && (
            <p className="text-destructive text-sm">
              {check.invalid_references.length} citation(s) point to papers outside this project.
            </p>
          )}
          <ul className="space-y-1 text-sm">
            {check.checks
              .filter((c) => c.status !== "unmarked")
              .map((c, i) => (
                <li key={i}>
                  <span className="font-medium">{CHECK_STATUS_LABELS[c.status] ?? c.status}: </span>
                  {c.text}
                </li>
              ))}
          </ul>
        </div>
      )}

      {versions && (
        <div className="space-y-2" aria-label="Version history">
          <ul className="space-y-1 text-sm">
            {versions.map((v) => (
              <li key={v.version_number} className="flex flex-wrap items-center gap-2">
                <span>
                  Version {v.version_number} · {v.change_summary} ·{" "}
                  {new Date(v.created_at).toLocaleString()}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () =>
                    setViewed(
                      (await run(
                        () => researchApi.draftVersion(draft.id, v.version_number),
                        "Could not open",
                      )) ?? null,
                    )
                  }
                >
                  View
                </Button>
                {!readOnly && v.version_number !== draft.version_number && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={dirty}
                    onClick={async () => {
                      const r = await run(
                        () =>
                          researchApi.restoreDraftVersion(
                            draft.id,
                            v.version_number,
                            draft.version_number,
                          ),
                        "Could not restore",
                      );
                      if (r) {
                        setDraft(r);
                        setTitle(r.title);
                        setContent(r.content);
                        setViewed(null);
                        setVersions(null);
                        onChanged();
                      }
                    }}
                  >
                    Restore
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {viewed && (
            <pre className="border-border bg-muted max-h-64 overflow-auto rounded-md border p-2 text-xs whitespace-pre-wrap">
              {viewed.content}
            </pre>
          )}
        </div>
      )}

      {!readOnly && (
        <div
          className="border-border space-y-3 rounded-md border p-3"
          aria-label="AI writing assistance"
        >
          <p className="text-sm font-medium">AI writing assistance</p>
          <p className="text-muted-foreground text-xs">
            Suggestions use the analysed papers of this project and are shown here first. Nothing
            changes in your draft until you accept it, and accepted text is saved as its own
            version.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="text-muted-foreground block">What to do</span>
              <select
                className={SELECT}
                value={action}
                onChange={(e) => setAction(e.target.value as WritingRequest["action"])}
              >
                {Object.entries(WRITING_ACTION_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="text-muted-foreground block">Section</span>
              <select
                className={SELECT}
                value={section}
                onChange={(e) => setSection(e.target.value)}
              >
                {Object.entries(WRITING_SECTION_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-muted-foreground">Instruction (optional)</span>
            <input
              className={FIELD}
              value={instruction}
              maxLength={1000}
              onChange={(e) => setInstruction(e.target.value)}
            />
          </label>
          {EDIT_ACTIONS.includes(action) && selected.trim() === "" && (
            <p className="text-muted-foreground text-xs">Select the text to work on first.</p>
          )}
          <Button
            disabled={busy || dirty || (EDIT_ACTIONS.includes(action) && selected.trim() === "")}
            onClick={ask}
          >
            {busy ? "Working…" : "Ask AI"}
          </Button>
          {dirty && <p className="text-muted-foreground text-xs">Save your draft first.</p>}

          {suggestion && (
            <div className="space-y-2" aria-label="AI suggestion">
              <p className="text-sm font-medium">AI suggestion (not yet part of your draft)</p>
              <pre className="border-border bg-muted max-h-64 overflow-auto rounded-md border p-2 text-sm whitespace-pre-wrap">
                {suggestion.text}
              </pre>
              {suggestion.notes && (
                <p className="text-muted-foreground text-sm">{suggestion.notes}</p>
              )}
              {suggestion.invalid_markers > 0 && (
                <p className="text-sm">
                  {suggestion.invalid_markers} source number(s) the AI used did not match any source
                  and were removed.
                </p>
              )}
              {flagged && flagged.length > 0 && (
                <div role="alert" className="text-sm">
                  <p className="font-medium">Check these statements before accepting:</p>
                  <ul className="list-disc pl-5">
                    {flagged.map((c, i) => (
                      <li key={i}>
                        {CHECK_STATUS_LABELS[c.status]}: {c.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {suggestion.sources.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    Evidence used ({suggestion.sources.length})
                  </summary>
                  <ul className="mt-1 space-y-1 text-sm">
                    {suggestion.sources.map((s, i) => (
                      <li key={i}>
                        <span className="text-muted-foreground">{s.paper_title}: </span>
                        {s.claim_text}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <div className="flex flex-wrap gap-2">
                {selected.trim() !== "" && (
                  <Button size="sm" disabled={busy} onClick={() => accept("replace")}>
                    Replace selection
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => accept("insert")}
                >
                  Insert at cursor
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => accept("append")}
                >
                  Add to the end
                </Button>
                <Button size="sm" variant="outline" onClick={() => setSuggestion(null)}>
                  Discard
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this draft?"
        description="The draft and all of its versions are deleted. Papers and citations are not affected."
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          setConfirmDelete(false);
          void run(async () => {
            await researchApi.deleteDraft(draft.id);
            onChanged();
            onClosed();
          }, "Could not delete");
        }}
      />
    </div>
  );
}

export function DraftsWorkspace({ project }: { project: ResearchProject }) {
  const { toast } = useToast();
  const readOnly = project.archived_at !== null;
  const list = useAsync(() => researchApi.listDrafts(project.id), [project.id]);
  const papers = useAsync(
    () => researchApi.listPapers(project.id, { archived: false, limit: 100 }),
    [project.id],
  );
  const paperList: Paper[] = (papers.data?.data ?? []).map((p) => ({ id: p.id, title: p.title }));
  const [open, setOpen] = useState<ResearchDraft | null>(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("research_paper");
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    try {
      setOpen(
        await researchApi.createDraft(project.id, { title: title.trim(), document_type: type }),
      );
      setTitle("");
      list.reload();
    } catch (e) {
      toast({ title: "Could not create", description: errorText(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function openSaved(d: DraftSummary) {
    try {
      setOpen(await researchApi.getDraft(d.id));
    } catch (e) {
      toast({ title: "Could not open", description: errorText(e), variant: "destructive" });
    }
  }

  const items = list.data?.data ?? [];
  return (
    <section aria-label="Writing studio" className="space-y-4">
      <h2 className="text-foreground text-lg font-semibold">Writing studio</h2>
      {!readOnly && (
        <div className={`${CARD} flex flex-wrap items-end gap-3`}>
          <label className="min-w-[14rem] flex-1 text-sm">
            <span className="text-muted-foreground">New draft title</span>
            <input
              className={FIELD}
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="text-muted-foreground block">Type</span>
            <select className={SELECT} value={type} onChange={(e) => setType(e.target.value)}>
              {Object.entries(DRAFT_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <Button disabled={busy || title.trim() === ""} onClick={create}>
            Create draft
          </Button>
        </div>
      )}
      <AsyncSection
        title="Drafts"
        loading={list.loading}
        error={list.error}
        onRetry={list.reload}
        isEmpty={items.length === 0}
        empty={<p className="text-muted-foreground text-sm">No drafts yet.</p>}
      >
        <ul className="space-y-2">
          {items.map((d) => (
            <li key={d.id} className={`${CARD} flex flex-wrap items-center justify-between gap-2`}>
              <div>
                <p className="font-medium">{d.title}</p>
                <p className="text-muted-foreground text-xs">
                  {DRAFT_TYPE_LABELS[d.document_type]} · {DRAFT_STATUS_LABELS[d.status]} ·{" "}
                  {d.word_count} words · version {d.version_number}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => openSaved(d)}>
                Open
              </Button>
            </li>
          ))}
        </ul>
      </AsyncSection>
      {open && (
        <Editor
          key={open.id}
          initial={open}
          papers={paperList}
          readOnly={readOnly}
          onChanged={list.reload}
          onClosed={() => setOpen(null)}
        />
      )}
    </section>
  );
}
