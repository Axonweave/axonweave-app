"use client";

import { useEffect, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAsync } from "@/hooks/use-async";
import { aiApi } from "@/lib/api/ai";
import { ApiRequestError } from "@/lib/api/client";
import { chaptersApi } from "@/lib/api/chapters";
import { documentsApi } from "@/lib/api/documents";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import {
  explainError,
  studyApi,
  type GenerationJob,
  type GenerationType,
  type SourceSpec,
} from "@/lib/api/study";
import { JobProgress } from "./job-progress";
import { useJob } from "./use-job";
import { Field, NativeSelect, Textarea } from "./ui-bits";

export const MAX_PASTED_CHARS = 200_000;

export interface PresetSource {
  type: "document" | "chapter" | "subject";
  id: string;
  label: string;
}

type FieldDef =
  | { key: string; label: string; kind: "select"; options: [string, string][] }
  | { key: string; label: string; kind: "number"; min: number; max: number }
  | { key: string; label: string; kind: "check" }
  | { key: string; label: string; kind: "multi"; options: [string, string][] };

const DIFFICULTY: [string, string][] = [
  ["easy", "Easy"],
  ["medium", "Medium"],
  ["hard", "Hard"],
  ["mixed", "Mixed"],
];
const QUESTION_TYPES: [string, string][] = [
  ["multiple_choice", "Multiple choice"],
  ["multiple_select", "Multiple select"],
  ["true_false", "True / false"],
  ["fill_in_the_blank", "Fill in the blank"],
  ["short_answer", "Short answer"],
  ["descriptive", "Descriptive"],
];

/** Only the settings the selected generator supports are shown (spec 20.2). */
export const GENERATORS: {
  type: GenerationType;
  label: string;
  hint: string;
  fields: FieldDef[];
}[] = [
  {
    type: "summary",
    label: "Summary",
    hint: "Key ideas in a structured form.",
    fields: [
      {
        key: "summary_type",
        label: "Summary type",
        kind: "select",
        options: [
          ["quick", "Quick"],
          ["detailed", "Detailed"],
          ["section_wise", "Section-wise"],
          ["exam_oriented", "Exam-oriented"],
          ["beginner_friendly", "Beginner-friendly"],
          ["key_point", "Key points"],
        ],
      },
      {
        key: "detail_level",
        label: "Detail level",
        kind: "select",
        options: [
          ["brief", "Brief"],
          ["standard", "Standard"],
          ["detailed", "Detailed"],
        ],
      },
      { key: "include_examples", label: "Include examples", kind: "check" },
      { key: "include_formulas", label: "Include formulas", kind: "check" },
    ],
  },
  {
    type: "flashcards",
    label: "Flashcards",
    hint: "Cards for active recall.",
    fields: [
      { key: "count", label: "Number of cards", kind: "number", min: 1, max: 50 },
      {
        key: "card_type",
        label: "Card type",
        kind: "select",
        options: [
          ["mixed", "Mixed"],
          ["basic", "Question and answer"],
          ["definition", "Definition"],
          ["concept", "Concept"],
          ["comparison", "Comparison"],
          ["fill_in_the_blank", "Fill in the blank"],
          ["application", "Application"],
        ],
      },
      { key: "difficulty", label: "Difficulty", kind: "select", options: DIFFICULTY },
    ],
  },
  {
    type: "quiz",
    label: "Quiz",
    hint: "Questions you answer, then see your results.",
    fields: [
      { key: "count", label: "Number of questions", kind: "number", min: 1, max: 50 },
      { key: "difficulty", label: "Difficulty", kind: "select", options: DIFFICULTY },
      { key: "question_types", label: "Question types", kind: "multi", options: QUESTION_TYPES },
      {
        key: "time_limit_minutes",
        label: "Time limit (minutes)",
        kind: "number",
        min: 1,
        max: 300,
      },
      { key: "randomize_order", label: "Randomise question order", kind: "check" },
    ],
  },
  {
    type: "study_guide",
    label: "Study guide",
    hint: "Objectives, sections and key takeaways.",
    fields: [
      {
        key: "level",
        label: "Level",
        kind: "select",
        options: [
          ["beginner", "Beginner"],
          ["intermediate", "Intermediate"],
          ["advanced", "Advanced"],
        ],
      },
      {
        key: "focus",
        label: "Focus",
        kind: "select",
        options: [
          ["exam_preparation", "Exam preparation"],
          ["conceptual_understanding", "Conceptual understanding"],
          ["practical_application", "Practical application"],
        ],
      },
      { key: "max_sections", label: "Maximum sections", kind: "number", min: 3, max: 40 },
    ],
  },
  {
    type: "glossary",
    label: "Glossary",
    hint: "Key terms and definitions.",
    fields: [{ key: "max_terms", label: "Maximum terms", kind: "number", min: 1, max: 100 }],
  },
  {
    type: "formula_sheet",
    label: "Formula sheet",
    hint: "Formulas with variables. Always check them against your source.",
    fields: [{ key: "max_formulas", label: "Maximum formulas", kind: "number", min: 1, max: 60 }],
  },
  {
    type: "question_bank",
    label: "Question bank",
    hint: "Practice questions to filter and reuse.",
    fields: [
      { key: "count", label: "Number of questions", kind: "number", min: 1, max: 100 },
      { key: "difficulty", label: "Difficulty", kind: "select", options: DIFFICULTY },
      { key: "question_types", label: "Question types", kind: "multi", options: QUESTION_TYPES },
    ],
  },
];

type SourceKind = "document" | "subject" | "chapter" | "text";

/** Builds the request. Only settings the user touched are sent, so saved preferences still apply. */
export function buildSettings(
  fields: FieldDef[],
  values: Record<string, string | boolean | string[]>,
  language: string,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.key];
    if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    if (f.kind === "number") {
      const n = Number(v);
      if (Number.isFinite(n)) out[f.key] = Math.min(f.max, Math.max(f.min, Math.round(n)));
    } else out[f.key] = v;
  }
  if (language.trim()) out.language = language.trim();
  return out;
}

export function GenerateDialog({
  open,
  onOpenChange,
  preset,
  defaultType = "summary",
  onStarted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preset?: PresetSource;
  defaultType?: GenerationType;
  onStarted?: (job: GenerationJob) => void;
}) {
  const [type, setType] = useState<GenerationType>(defaultType);
  const gen = GENERATORS.find((g) => g.type === type) ?? GENERATORS[0];
  const [values, setValues] = useState<Record<string, string | boolean | string[]>>({});
  const [language, setLanguage] = useState("");
  const [kind, setKind] = useState<SourceKind>(preset?.type ?? "document");
  const [documentId, setDocumentId] = useState(preset?.type === "document" ? preset.id : "");
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState(preset?.type === "subject" ? preset.id : "");
  const [chapterId, setChapterId] = useState(preset?.type === "chapter" ? preset.id : "");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setType(defaultType);
    }
  }, [open, defaultType]);

  const needPickers = !preset;
  const docs = useAsync(
    () =>
      open && needPickers
        ? documentsApi.list({ status: "completed", limit: 100 })
        : Promise.resolve(null),
    [open, needPickers],
  );
  const workspaces = useAsync(
    () => (open && needPickers ? workspacesApi.list().then((r) => r.data) : Promise.resolve(null)),
    [open, needPickers],
  );
  const subjects = useAsync(
    () =>
      open && needPickers && workspaceId
        ? subjectsApi.list(workspaceId, { limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [open, needPickers, workspaceId],
  );
  const chapters = useAsync(
    () =>
      open && needPickers && workspaceId && subjectId && kind === "chapter"
        ? chaptersApi.list(workspaceId, subjectId, { limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [open, needPickers, workspaceId, subjectId, kind],
  );
  const usage = useAsync(
    () => (open ? aiApi.usageSummary(30).catch(() => null) : Promise.resolve(null)),
    [open],
  );

  const { job, error: jobError, cancel } = useJob(jobId);

  const source: SourceSpec | null = useMemo(() => {
    if (preset) return { type: preset.type, id: preset.id };
    if (kind === "document" && documentId) return { type: "document", id: documentId };
    if (kind === "subject" && subjectId) return { type: "subject", id: subjectId };
    if (kind === "chapter" && chapterId) return { type: "chapter", id: chapterId };
    if (kind === "text" && text.trim() && workspaceId)
      return { type: "text", text: text.trim(), workspace_id: workspaceId };
    return null;
  }, [preset, kind, documentId, subjectId, chapterId, text, workspaceId]);

  async function start() {
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      const started = await studyApi.generate({
        generation_type: type,
        source,
        settings: buildSettings(gen.fields, values, language),
      });
      setJobId(started.id);
      onStarted?.(started);
    } catch (err) {
      setError(
        err instanceof ApiRequestError ? explainError(err.code, err.message) : "Could not start.",
      );
    } finally {
      setBusy(false);
    }
  }

  function close(next: boolean) {
    if (!next) setJobId(null);
    onOpenChange(next);
  }

  const set = (key: string, value: string | boolean | string[]) =>
    setValues((v) => ({ ...v, [key]: value }));
  const running = Boolean(jobId);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Generate study material</DialogTitle>
          <DialogDescription>
            The selected text is sent to the AI provider to write this. AI output can contain
            mistakes: check it against your source.
          </DialogDescription>
        </DialogHeader>

        {running ? (
          <div className="space-y-3">
            {job ? (
              <JobProgress job={job} onCancel={cancel} />
            ) : (
              <p className="text-muted-foreground text-sm">Starting…</p>
            )}
            {jobError ? (
              <p role="alert" className="text-destructive text-sm">
                {jobError}
              </p>
            ) : null}
            <p className="text-muted-foreground text-xs">
              You can close this window; the job keeps running and appears in Study materials.
            </p>
          </div>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void start();
            }}
          >
            <Field label="What to generate" htmlFor="gen-type" hint={gen.hint}>
              <NativeSelect
                id="gen-type"
                value={type}
                onChange={(e) => {
                  setType(e.target.value as GenerationType);
                  setValues({});
                }}
              >
                {GENERATORS.map((g) => (
                  <option key={g.type} value={g.type}>
                    {g.label}
                  </option>
                ))}
              </NativeSelect>
            </Field>

            {preset ? (
              <p className="text-sm">
                <span className="text-muted-foreground">From: </span>
                <span className="font-medium break-words">{preset.label}</span>
              </p>
            ) : (
              <fieldset className="space-y-3">
                <legend className="text-sm font-medium">Source</legend>
                <NativeSelect
                  aria-label="Source type"
                  value={kind}
                  onChange={(e) => setKind(e.target.value as SourceKind)}
                >
                  <option value="document">A document</option>
                  <option value="subject">A whole subject</option>
                  <option value="chapter">A chapter</option>
                  <option value="text">Pasted text</option>
                </NativeSelect>
                {kind === "document" ? (
                  <NativeSelect
                    aria-label="Document"
                    value={documentId}
                    onChange={(e) => setDocumentId(e.target.value)}
                  >
                    <option value="">Choose a processed document…</option>
                    {(docs.data?.data ?? []).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.display_name}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <>
                    <NativeSelect
                      aria-label="Workspace"
                      value={workspaceId}
                      onChange={(e) => {
                        setWorkspaceId(e.target.value);
                        setSubjectId("");
                        setChapterId("");
                      }}
                    >
                      <option value="">Choose a workspace…</option>
                      {(workspaces.data ?? []).map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name}
                        </option>
                      ))}
                    </NativeSelect>
                    {kind !== "text" && workspaceId ? (
                      <NativeSelect
                        aria-label="Subject"
                        value={subjectId}
                        onChange={(e) => {
                          setSubjectId(e.target.value);
                          setChapterId("");
                        }}
                      >
                        <option value="">Choose a subject…</option>
                        {(subjects.data ?? []).map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </NativeSelect>
                    ) : null}
                    {kind === "chapter" && subjectId ? (
                      <NativeSelect
                        aria-label="Chapter"
                        value={chapterId}
                        onChange={(e) => setChapterId(e.target.value)}
                      >
                        <option value="">Choose a chapter…</option>
                        {(chapters.data ?? []).map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.title}
                          </option>
                        ))}
                      </NativeSelect>
                    ) : null}
                  </>
                )}
                {kind === "text" ? (
                  <div className="space-y-1">
                    <Textarea
                      aria-label="Pasted text"
                      rows={6}
                      maxLength={MAX_PASTED_CHARS}
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      placeholder="Paste the text to study from"
                    />
                    <p className="text-muted-foreground text-xs">
                      {text.length.toLocaleString()} / {MAX_PASTED_CHARS.toLocaleString()}{" "}
                      characters. Pasted text is not stored, so this cannot be regenerated later.
                    </p>
                  </div>
                ) : null}
              </fieldset>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              {gen.fields.map((f) => {
                const id = `gen-${f.key}`;
                if (f.kind === "select")
                  return (
                    <Field key={f.key} label={f.label} htmlFor={id}>
                      <NativeSelect
                        id={id}
                        value={String(values[f.key] ?? "")}
                        onChange={(e) => set(f.key, e.target.value)}
                      >
                        <option value="">Default</option>
                        {f.options.map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </NativeSelect>
                    </Field>
                  );
                if (f.kind === "number")
                  return (
                    <Field key={f.key} label={f.label} htmlFor={id}>
                      <Input
                        id={id}
                        type="number"
                        inputMode="numeric"
                        min={f.min}
                        max={f.max}
                        placeholder="Default"
                        value={String(values[f.key] ?? "")}
                        onChange={(e) => set(f.key, e.target.value)}
                      />
                    </Field>
                  );
                if (f.kind === "check")
                  return (
                    <label key={f.key} className="flex items-center gap-2 self-end text-sm">
                      <input
                        type="checkbox"
                        checked={Boolean(values[f.key])}
                        onChange={(e) => set(f.key, e.target.checked)}
                      />
                      {f.label}
                    </label>
                  );
                const chosen = (values[f.key] as string[] | undefined) ?? [];
                return (
                  <fieldset key={f.key} className="sm:col-span-2">
                    <legend className="mb-1 text-sm font-medium">{f.label}</legend>
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                      {f.options.map(([v, l]) => (
                        <label key={v} className="flex items-center gap-1.5 text-sm">
                          <input
                            type="checkbox"
                            checked={chosen.includes(v)}
                            onChange={(e) =>
                              set(
                                f.key,
                                e.target.checked ? [...chosen, v] : chosen.filter((c) => c !== v),
                              )
                            }
                          />
                          {l}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                );
              })}
              <Field label="Language" htmlFor="gen-language">
                <Input
                  id="gen-language"
                  maxLength={40}
                  placeholder="Default"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                />
              </Field>
            </div>

            {usage.data ? (
              <p className="text-muted-foreground text-xs" data-testid="quota-hint">
                Generation uses your AI allowance. You made {usage.data.requests} AI request
                {usage.data.requests === 1 ? "" : "s"} in the last {usage.data.days} days. If the
                limit is reached you will see a message here.
              </p>
            ) : null}
            {error ? (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!source || busy}>
                <Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />
                {busy ? "Starting…" : "Generate"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
