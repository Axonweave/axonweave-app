"use client";

import { useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAsync } from "@/hooks/use-async";
import type { BankQuestion, GlossaryTerm, MaterialSource } from "@/lib/api/study";
import { studyApi } from "@/lib/api/study";
import { Markdown } from "@/features/ai-tutor/markdown";
import { Latex } from "./latex";
import { SourceRefs } from "./sources";
import { Chip, NativeSelect } from "./ui-bits";

export interface ViewProps<P> {
  payload: P;
  sources: MaterialSource[];
  unavailable: string[];
}

/* ───────── summary ───────── */

interface SummaryPayload {
  title: string;
  sections: {
    heading: string;
    kind?: string;
    body?: string;
    bullets?: string[];
    additional_explanation?: boolean;
    source_refs?: number[];
  }[];
}

export function SummaryView({
  payload,
  sources,
  unavailable,
  onRegenerateSection,
}: ViewProps<SummaryPayload> & { onRegenerateSection?: (index: number) => void }) {
  return (
    <div className="space-y-6">
      {payload.sections.map((s, i) => (
        <section key={i} aria-labelledby={`sum-${i}`} className="space-y-2">
          <div className="flex items-start justify-between gap-2">
            <h2 id={`sum-${i}`} className="text-lg font-semibold break-words">
              {s.heading}
            </h2>
            {onRegenerateSection ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Regenerate section ${s.heading}`}
                onClick={() => onRegenerateSection(i)}
              >
                <RefreshCw aria-hidden="true" />
                Regenerate
              </Button>
            ) : null}
          </div>
          {s.additional_explanation ? (
            <Chip>Added explanation (not directly in your source)</Chip>
          ) : null}
          {s.body ? <Markdown content={s.body} /> : null}
          {s.bullets?.length ? (
            <ul className="list-disc space-y-1 pl-6">
              {s.bullets.map((b, j) => (
                <li key={j} className="break-words">
                  {b}
                </li>
              ))}
            </ul>
          ) : null}
          <SourceRefs refs={s.source_refs} sources={sources} unavailable={unavailable} />
        </section>
      ))}
    </div>
  );
}

/* ───────── study guide ───────── */

interface GuidePayload {
  title: string;
  overview?: string;
  learning_objectives?: {
    text: string;
    generated_recommendation?: boolean;
    source_refs?: number[];
  }[];
  prerequisites?: string[];
  sections: {
    heading: string;
    level?: number;
    body?: string;
    bullets?: string[];
    source_refs?: number[];
  }[];
  key_takeaways?: string[];
  practice_questions?: { question: string; source_refs?: number[] }[];
}

export function GuideView({ payload, sources, unavailable }: ViewProps<GuidePayload>) {
  return (
    <div className="space-y-6">
      {payload.overview ? <Markdown content={payload.overview} /> : null}
      {payload.learning_objectives?.length ? (
        <section aria-labelledby="g-obj">
          <h2 id="g-obj" className="text-lg font-semibold">
            Learning objectives
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            {payload.learning_objectives.map((o, i) => (
              <li key={i} className="break-words">
                {o.text}
                {o.generated_recommendation ? (
                  <span className="ml-2">
                    <Chip>Suggested by the AI, not from your source</Chip>
                  </span>
                ) : null}
                <SourceRefs refs={o.source_refs} sources={sources} unavailable={unavailable} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {payload.prerequisites?.length ? (
        <section aria-labelledby="g-pre">
          <h2 id="g-pre" className="text-lg font-semibold">
            Prerequisites
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            {payload.prerequisites.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {payload.sections.map((s, i) => {
        const H = (s.level ?? 1) >= 2 ? "h3" : "h2";
        return (
          <section key={i} className="space-y-2">
            <H
              className={(s.level ?? 1) >= 2 ? "text-base font-semibold" : "text-lg font-semibold"}
            >
              {s.heading}
            </H>
            {s.body ? <Markdown content={s.body} /> : null}
            {s.bullets?.length ? (
              <ul className="list-disc space-y-1 pl-6">
                {s.bullets.map((b, j) => (
                  <li key={j}>{b}</li>
                ))}
              </ul>
            ) : null}
            <SourceRefs refs={s.source_refs} sources={sources} unavailable={unavailable} />
          </section>
        );
      })}
      {payload.key_takeaways?.length ? (
        <section aria-labelledby="g-key">
          <h2 id="g-key" className="text-lg font-semibold">
            Key takeaways
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            {payload.key_takeaways.map((k, i) => (
              <li key={i}>{k}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {payload.practice_questions?.length ? (
        <section aria-labelledby="g-pq">
          <h2 id="g-pq" className="text-lg font-semibold">
            Practice questions
          </h2>
          <ol className="mt-2 list-decimal space-y-2 pl-6">
            {payload.practice_questions.map((p, i) => (
              <li key={i}>
                {p.question}
                <SourceRefs refs={p.source_refs} sources={sources} unavailable={unavailable} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

/* ───────── glossary (server-side search) ───────── */

export function GlossaryView({
  materialId,
  sources,
  unavailable,
}: {
  materialId: string;
  sources: MaterialSource[];
  unavailable: string[];
}) {
  const [q, setQ] = useState("");
  const [topic, setTopic] = useState("");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const all = useAsync(() => studyApi.glossary(materialId), [materialId]);
  const found = useAsync(
    () =>
      studyApi.glossary(materialId, { q: q.trim() || undefined, topic: topic || undefined, order }),
    [materialId, q, topic, order],
  );
  const topics = Array.from(
    new Set((all.data?.data ?? []).map((t: GlossaryTerm) => t.topic).filter(Boolean)),
  ) as string[];
  const terms = found.data?.data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          type="search"
          aria-label="Search terms"
          placeholder="Search terms and definitions"
          maxLength={100}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {topics.length > 0 ? (
          <NativeSelect
            aria-label="Filter by topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="sm:w-48"
          >
            <option value="">All topics</option>
            {topics.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </NativeSelect>
        ) : null}
        <NativeSelect
          aria-label="Sort order"
          value={order}
          onChange={(e) => setOrder(e.target.value as "asc" | "desc")}
          className="sm:w-40"
        >
          <option value="asc">A to Z</option>
          <option value="desc">Z to A</option>
        </NativeSelect>
      </div>
      <p className="text-muted-foreground text-sm" aria-live="polite">
        {found.loading ? "Searching…" : `${terms.length} term${terms.length === 1 ? "" : "s"}`}
      </p>
      <dl className="space-y-4">
        {terms.map((t, i) => (
          <div key={`${t.term}-${i}`} className="border-border rounded-lg border p-3">
            <dt className="font-semibold break-words">
              {t.term} {t.topic ? <Chip>{t.topic}</Chip> : null}
            </dt>
            <dd className="mt-1 space-y-1 text-sm">
              <p className="break-words">{t.definition}</p>
              {t.explanation ? <p className="text-muted-foreground">{t.explanation}</p> : null}
              {t.example ? (
                <p>
                  <span className="font-medium">Example: </span>
                  {t.example}
                </p>
              ) : null}
              {t.related_terms?.length ? (
                <p className="text-muted-foreground">Related: {t.related_terms.join(", ")}</p>
              ) : null}
              <SourceRefs refs={t.source_refs} sources={sources} unavailable={unavailable} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/* ───────── formula sheet ───────── */

interface FormulaPayload {
  title: string;
  verification?: string;
  flagged_count?: number;
  formulas: {
    name: string;
    expression: string;
    explanation?: string;
    variables?: { symbol: string; meaning: string; unit?: string }[];
    conditions?: string;
    example?: string;
    topic?: string;
    needs_review?: boolean;
    review_notes?: string[];
    source_refs?: number[];
  }[];
}

export function FormulaView({ payload, sources, unavailable }: ViewProps<FormulaPayload>) {
  return (
    <div className="space-y-4">
      <p
        className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        role="note"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          Not verified. Valid formula syntax does not mean the formula is correct. Check each one
          against your source before you rely on it.
          {payload.flagged_count ? ` ${payload.flagged_count} flagged for review.` : ""}
        </span>
      </p>
      {payload.formulas.map((f, i) => (
        <article key={i} className="border-border space-y-2 rounded-lg border p-3">
          <h2 className="font-semibold break-words">
            {f.name} {f.topic ? <Chip>{f.topic}</Chip> : null}
          </h2>
          <Latex expression={f.expression} />
          {f.needs_review ? (
            <p role="status" className="text-sm text-amber-700 dark:text-amber-400">
              Needs review{f.review_notes?.length ? `: ${f.review_notes.join("; ")}` : ""}
            </p>
          ) : null}
          {f.explanation ? <p className="text-sm">{f.explanation}</p> : null}
          {f.variables?.length ? (
            <table className="w-full text-sm">
              <caption className="sr-only">Variables for {f.name}</caption>
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th className="pr-2 font-medium">Symbol</th>
                  <th className="pr-2 font-medium">Meaning</th>
                  <th className="font-medium">Unit</th>
                </tr>
              </thead>
              <tbody>
                {f.variables.map((v, j) => (
                  <tr key={j}>
                    <td className="pr-2 align-top">
                      <Latex expression={v.symbol} block={false} />
                    </td>
                    <td className="pr-2 align-top break-words">{v.meaning}</td>
                    <td className="align-top">{v.unit || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {f.conditions ? <p className="text-sm">Conditions: {f.conditions}</p> : null}
          {f.example ? <p className="text-sm">Example: {f.example}</p> : null}
          <SourceRefs refs={f.source_refs} sources={sources} unavailable={unavailable} />
        </article>
      ))}
    </div>
  );
}

/* ───────── question bank (no answer keys exist in this view) ───────── */

export function BankView({
  materialId,
  quizId,
  sources,
  unavailable,
}: {
  materialId: string;
  quizId: string | null;
  sources: MaterialSource[];
  unavailable: string[];
}) {
  const [q, setQ] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [qtype, setQtype] = useState("");
  const [topic, setTopic] = useState("");
  const all = useAsync(() => studyApi.questions(materialId), [materialId]);
  const found = useAsync(
    () =>
      studyApi.questions(materialId, {
        q: q.trim() || undefined,
        difficulty: difficulty || undefined,
        question_type: qtype || undefined,
        topic: topic || undefined,
      }),
    [materialId, q, difficulty, qtype, topic],
  );
  const topics = Array.from(
    new Set((all.data?.data ?? []).map((x: BankQuestion) => x.topic).filter(Boolean)),
  ) as string[];
  const items = found.data?.data ?? [];
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        Answers and explanations are not shown here.{" "}
        {quizId ? "Practise these as a quiz to get a score and see the answers." : ""}
      </p>
      <div className="grid gap-2 sm:grid-cols-4">
        <Input
          type="search"
          aria-label="Search questions"
          placeholder="Search questions"
          maxLength={100}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <NativeSelect
          aria-label="Filter by difficulty"
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value)}
        >
          <option value="">Any difficulty</option>
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by type"
          value={qtype}
          onChange={(e) => setQtype(e.target.value)}
        >
          <option value="">Any type</option>
          <option value="multiple_choice">Multiple choice</option>
          <option value="multiple_select">Multiple select</option>
          <option value="true_false">True / false</option>
          <option value="fill_in_the_blank">Fill in the blank</option>
          <option value="short_answer">Short answer</option>
          <option value="descriptive">Descriptive</option>
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        >
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </NativeSelect>
      </div>
      <p className="text-muted-foreground text-sm" aria-live="polite">
        {items.length} question{items.length === 1 ? "" : "s"}
      </p>
      <ol className="space-y-3">
        {items.map((it, i) => (
          <li key={i} className="border-border rounded-lg border p-3">
            <p className="font-medium break-words">{it.question}</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Chip>{it.question_type.replace(/_/g, " ")}</Chip>
              <Chip>{it.difficulty}</Chip>
              {it.topic ? <Chip>{it.topic}</Chip> : null}
            </div>
            {it.options?.length ? (
              <ul className="mt-2 space-y-1 text-sm">
                {it.options.map((o) => (
                  <li key={o.id}>
                    <span className="font-medium">{o.id}.</span> {o.text}
                  </li>
                ))}
              </ul>
            ) : null}
            <SourceRefs refs={it.source_refs} sources={sources} unavailable={unavailable} />
          </li>
        ))}
      </ol>
    </div>
  );
}
