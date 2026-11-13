"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { knowledgeApi, evidenceHref } from "@/lib/api/knowledge";
import {
  STATE_LABELS,
  STATE_ORDER,
  learnerApi,
  recommendationHref,
  type GapConcept,
  type LearnerConceptRow,
  type LearnerDashboard,
  type LearnerRecommendation,
} from "@/lib/api/learner";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";

const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const CARD = "border-border bg-card rounded-lg border p-4";

const STATE_COLOUR: Record<string, string> = {
  STRONG: "bg-emerald-600",
  PROFICIENT: "bg-emerald-400",
  DEVELOPING: "bg-amber-400",
  LEARNING: "bg-red-500",
  INSUFFICIENT_EVIDENCE: "bg-slate-400",
  NOT_ASSESSED: "bg-slate-300",
};

type Tab = "overview" | "subjects" | "gaps" | "concepts";
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "subjects", label: "Subjects" },
  { id: "gaps", label: "Learning gaps" },
  { id: "concepts", label: "Concepts" },
];

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "No score" : `${Math.round(v * 100)}%`;
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className={CARD}>
      <div className="text-foreground text-2xl font-semibold">{value}</div>
      <div className="text-muted-foreground text-sm">{label}</div>
      {hint && <div className="text-muted-foreground mt-1 text-xs">{hint}</div>}
    </div>
  );
}

function StateBadge({ state }: { state: string }) {
  return (
    <span className="bg-muted text-foreground inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs">
      <span
        aria-hidden
        className={`h-2 w-2 rounded-full ${STATE_COLOUR[state] ?? "bg-slate-300"}`}
      />
      {STATE_LABELS[state] ?? state}
    </span>
  );
}

function Distribution({ counts, total }: { counts: Record<string, number>; total: number }) {
  if (total === 0) return null;
  return (
    <div>
      <div
        className="flex h-3 w-full overflow-hidden rounded-full"
        role="img"
        aria-label={STATE_ORDER.map((s) => `${STATE_LABELS[s]}: ${counts[s] ?? 0}`).join(", ")}
      >
        {STATE_ORDER.map((s) =>
          counts[s] ? (
            <div
              key={s}
              className={STATE_COLOUR[s]}
              style={{ width: `${((counts[s] ?? 0) / total) * 100}%` }}
            />
          ) : null,
        )}
      </div>
      <ul className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {STATE_ORDER.map((s) => (
          <li key={s} className="flex items-center gap-1.5">
            <span aria-hidden className={`h-2 w-2 rounded-full ${STATE_COLOUR[s]}`} />
            {STATE_LABELS[s]} {counts[s] ?? 0}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecommendationList({
  items,
  onChanged,
}: {
  items: LearnerRecommendation[];
  onChanged: () => void;
}) {
  const { toast } = useToast();
  async function act(id: string, kind: "complete" | "dismiss") {
    try {
      if (kind === "complete") await learnerApi.completeRecommendation(id);
      else await learnerApi.dismissRecommendation(id);
      onChanged();
    } catch {
      toast({ title: "Could not update the recommendation", variant: "destructive" });
    }
  }
  return (
    <ul className="space-y-3">
      {items.map((r) => (
        <li key={r.id} className={CARD}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-foreground font-medium">{r.topic_name ?? "Recommendation"}</span>
            <span className="bg-muted rounded-full px-2 py-0.5 text-xs capitalize">
              {r.priority} priority
            </span>
          </div>
          <p className="text-muted-foreground mt-1 text-sm">{r.reason}</p>
          {r.suggested_action && <p className="mt-1 text-sm">{r.suggested_action}</p>}
          <details className="text-muted-foreground mt-2 text-xs">
            <summary className="cursor-pointer">Why this was suggested</summary>
            <pre className="mt-1 whitespace-pre-wrap">{JSON.stringify(r.evidence, null, 2)}</pre>
          </details>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              href={recommendationHref(r)}
              className="bg-primary text-primary-foreground inline-flex h-8 items-center rounded-md px-3 text-sm"
            >
              Go
            </Link>
            <Button size="sm" variant="outline" onClick={() => act(r.id, "complete")}>
              Done
            </Button>
            <Button size="sm" variant="ghost" onClick={() => act(r.id, "dismiss")}>
              Dismiss
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function GapList({
  title,
  note,
  items,
  onOpen,
  extra,
}: {
  title: string;
  note: string;
  items: GapConcept[];
  onOpen: (id: string) => void;
  extra?: (g: GapConcept) => string | null;
}) {
  return (
    <section className={CARD} aria-label={title}>
      <h3 className="text-foreground font-semibold">{title}</h3>
      <p className="text-muted-foreground mb-2 text-xs">{note}</p>
      {items.length === 0 ? (
        <p className="text-muted-foreground text-sm">Nothing here.</p>
      ) : (
        <ul className="divide-border divide-y">
          {items.map((g) => (
            <li key={g.node_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <button
                  type="button"
                  className="text-foreground text-left text-sm font-medium underline-offset-2 hover:underline"
                  onClick={() => onOpen(g.node_id)}
                >
                  {g.name}
                </button>
                {extra?.(g) && <div className="text-muted-foreground text-xs">{extra(g)}</div>}
              </div>
              <StateBadge state={g.state} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ConceptPanel({ nodeId, onClose }: { nodeId: string; onClose: () => void }) {
  const detail = useAsync(() => knowledgeApi.node(nodeId), [nodeId]);
  const state = useAsync(() => learnerApi.state(nodeId), [nodeId]);
  const history = useAsync(() => learnerApi.evidence(nodeId, 10), [nodeId]);
  const miscs = useAsync(() => learnerApi.misconceptions(nodeId), [nodeId]);
  const materials = useAsync(() => knowledgeApi.nodeEvidence(nodeId, 5), [nodeId]);
  const recs = useAsync(() => learnerApi.recommendations(), [nodeId]);
  const n = detail.data;
  const st = state.data;
  const mine = (recs.data?.items ?? []).filter((r) => r.knowledge_node_id === nodeId);
  return (
    <section className={`${CARD} space-y-4`} aria-label="Concept details">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-foreground text-lg font-semibold">{n?.name ?? "Concept"}</h2>
          {st && <StateBadge state={st.state} />}
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      {n?.definition && <p className="text-sm">{n.definition}</p>}
      {n?.description && <p className="text-muted-foreground text-sm">{n.description}</p>}
      {st && (
        <div>
          <h3 className="text-sm font-semibold">Mastery</h3>
          <p className="text-sm">
            Estimate: {pct(st.mastery_estimate)} · Confidence: {pct(st.confidence)} · Evidence:{" "}
            {st.evidence_count}
          </p>
          <p className="text-muted-foreground text-xs">{st.explanation}</p>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">Prerequisites</h3>
          <ul className="text-sm">
            {(n?.prerequisites ?? []).map((p) => (
              <li key={p.node.id}>{p.node.name}</li>
            ))}
            {(n?.prerequisites ?? []).length === 0 && (
              <li className="text-muted-foreground">None recorded.</li>
            )}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold">Related concepts</h3>
          <ul className="text-sm">
            {(n?.related ?? []).map((p) => (
              <li key={p.node.id}>{p.node.name}</li>
            ))}
            {(n?.related ?? []).length === 0 && (
              <li className="text-muted-foreground">None recorded.</li>
            )}
          </ul>
        </div>
      </div>
      <div>
        <h3 className="text-sm font-semibold">Supporting materials</h3>
        <ul className="text-sm">
          {(materials.data?.data ?? []).map((e) => (
            <li key={e.id}>
              <Link className="underline" href={evidenceHref(e)}>
                {e.document_name}
              </Link>
            </li>
          ))}
          {(materials.data?.data ?? []).length === 0 && (
            <li className="text-muted-foreground">No supporting passages.</li>
          )}
        </ul>
      </div>
      <div>
        <h3 className="text-sm font-semibold">Assessment and flashcard history</h3>
        <ul className="text-sm">
          {(history.data?.data ?? []).map((e) => (
            <li key={e.id} className="text-muted-foreground">
              {new Date(e.occurred_at).toLocaleDateString()} ·{" "}
              {e.source_type === "quiz_answer" ? "Quiz answer" : "Flashcard review"} ·{" "}
              {pct(e.evidence_value)}
            </li>
          ))}
          {(history.data?.data ?? []).length === 0 && (
            <li className="text-muted-foreground">
              No quiz or flashcard results are linked to this concept yet.
            </li>
          )}
        </ul>
      </div>
      <div>
        <h3 className="text-sm font-semibold">Misconceptions</h3>
        <ul className="text-sm">
          {(miscs.data?.data ?? [])
            .filter((m) => m.status !== "dismissed")
            .map((m) => (
              <li key={m.id}>
                {m.tentative ? "Possibly: " : ""}
                {m.description}
              </li>
            ))}
          {(miscs.data?.data ?? []).filter((m) => m.status !== "dismissed").length === 0 && (
            <li className="text-muted-foreground">None detected.</li>
          )}
        </ul>
      </div>
      {mine.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Recommended actions</h3>
          <RecommendationList items={mine} onChanged={recs.reload} />
        </div>
      )}
      <Link className="text-sm underline" href={`/knowledge?node=${nodeId}`}>
        Open in the knowledge graph
      </Link>
    </section>
  );
}

function ConceptTable({
  rows,
  onOpen,
}: {
  rows: LearnerConceptRow[];
  onOpen: (id: string) => void;
}) {
  const [state, setState] = useState("");
  const [q, setQ] = useState("");
  const shown = rows.filter(
    (r) =>
      (!state || r.state === state) &&
      (!q || r.name.toLowerCase().includes(q.trim().toLowerCase())),
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          placeholder="Search concepts"
          aria-label="Search concepts"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className={SELECT}
          aria-label="Filter by state"
          value={state}
          onChange={(e) => setState(e.target.value)}
        >
          <option value="">All states</option>
          {STATE_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATE_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-muted-foreground text-xs">
            <tr>
              <th className="py-1 pr-3">Concept</th>
              <th className="py-1 pr-3">State</th>
              <th className="py-1 pr-3">Mastery</th>
              <th className="py-1 pr-3">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.node_id} className="border-border border-t">
                <td className="py-2 pr-3">
                  <button
                    type="button"
                    className="underline-offset-2 hover:underline"
                    onClick={() => onOpen(r.node_id)}
                  >
                    {r.name}
                  </button>
                  {r.subject_name && (
                    <span className="text-muted-foreground ml-2 text-xs">{r.subject_name}</span>
                  )}
                </td>
                <td className="py-2 pr-3">
                  <StateBadge state={r.state} />
                </td>
                <td className="py-2 pr-3">{pct(r.mastery)}</td>
                <td className="py-2 pr-3">{r.evidence_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && (
          <p className="text-muted-foreground py-4 text-sm">No concepts match these filters.</p>
        )}
      </div>
    </div>
  );
}

function Body({
  data,
  recs,
  reloadRecs,
  onOpen,
  tab,
}: {
  data: LearnerDashboard;
  recs: LearnerRecommendation[];
  reloadRecs: () => void;
  onOpen: (id: string) => void;
  tab: Tab;
}) {
  const o = data.overview;
  if (tab === "overview")
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Concepts tracked" value={o.tracked} />
          <Stat label="Assessed" value={o.assessed} hint="Have any quiz or flashcard result" />
          <Stat
            label="Enough evidence"
            value={o.sufficient_evidence}
            hint="Scored with confidence"
          />
          <Stat label="Not assessed" value={o.unassessed} hint="No evidence, not a weakness" />
          <Stat label="Strong" value={o.strong} />
          <Stat label="Developing" value={o.developing} />
          <Stat label="Weak" value={o.weak} hint="Demonstrated by results" />
          <Stat label="Misconceptions" value={o.misconceptions} />
        </div>
        <div className={CARD}>
          <Distribution
            counts={{
              STRONG: o.strong,
              PROFICIENT: o.proficient,
              DEVELOPING: o.developing,
              LEARNING: o.weak,
              INSUFFICIENT_EVIDENCE: o.insufficient_evidence,
              NOT_ASSESSED: o.unassessed,
            }}
            total={o.tracked}
          />
        </div>
        <section aria-label="Recommended actions">
          <h2 className="text-foreground mb-2 text-lg font-semibold">Recommended actions</h2>
          {recs.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No recommendations yet. They appear once quizzes or flashcards give evidence about
              your concepts.
            </p>
          ) : (
            <RecommendationList items={recs} onChanged={reloadRecs} />
          )}
        </section>
      </div>
    );
  if (tab === "subjects")
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {data.subjects.map((s) => (
          <section key={s.subject_id ?? "none"} className={`${CARD} space-y-2`}>
            <h3 className="text-foreground font-semibold">{s.subject_name ?? "No subject"}</h3>
            <p className="text-muted-foreground text-sm">
              {s.total} concepts · {s.assessed} assessed · {s.unassessed} not assessed
            </p>
            <Distribution counts={s.distribution} total={s.total} />
            {s.weak.length > 0 && <p className="text-sm">Weak: {s.weak.join(", ")}</p>}
            {s.strong.length > 0 && <p className="text-sm">Strong: {s.strong.join(", ")}</p>}
            {s.missing_prerequisites > 0 && (
              <p className="text-sm">Prerequisites needing attention: {s.missing_prerequisites}</p>
            )}
          </section>
        ))}
      </div>
    );
  if (tab === "gaps") {
    const g = data.gaps;
    return (
      <div className="space-y-4">
        <p className="text-muted-foreground text-sm">
          Weak concepts and misconceptions are demonstrated by your results. “Not assessed” items
          only mean there is no evidence yet.
        </p>
        <GapList
          title="Weak concepts"
          note="Demonstrated by your quiz or flashcard results."
          items={g.weak}
          onOpen={onOpen}
          extra={(i) => `Estimate ${pct(i.mastery)} from ${i.evidence_count ?? 0} results`}
        />
        <GapList
          title="Prerequisites to revisit"
          note="Prerequisites of concepts you are struggling with."
          items={g.missing_prerequisites}
          onOpen={onOpen}
          extra={(i) =>
            `${i.kind === "demonstrated" ? "Weak or developing" : "Not assessed"} · needed for ${(i.needed_for ?? []).join(", ")}`
          }
        />
        <section className={CARD} aria-label="Repeated misconceptions">
          <h3 className="text-foreground font-semibold">Repeated misconceptions</h3>
          {g.misconceptions.length === 0 ? (
            <p className="text-muted-foreground text-sm">None detected.</p>
          ) : (
            <ul className="divide-border divide-y">
              {g.misconceptions.map((m) => (
                <li key={m.id} className="py-2 text-sm">
                  <button
                    type="button"
                    className="font-medium underline-offset-2 hover:underline"
                    onClick={() => onOpen(m.node_id)}
                  >
                    {m.name}
                  </button>
                  : {m.tentative ? "Possibly " : ""}
                  {m.description}{" "}
                  <span className="text-muted-foreground text-xs">
                    ({m.evidence_count} wrong answers)
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <GapList
          title="Important concepts not assessed yet"
          note="Well connected in your material but with no results. This is missing evidence, not weakness."
          items={g.unassessed_important}
          onOpen={onOpen}
          extra={(i) => `Connected to ${i.connections ?? 0} concepts`}
        />
        <GapList
          title="Topics needing revision"
          note="A flashcard covering the concept is due."
          items={g.needs_revision}
          onOpen={onOpen}
          extra={(i) =>
            i.next_review_at ? `Due ${new Date(i.next_review_at).toLocaleDateString()}` : null
          }
        />
      </div>
    );
  }
  return <ConceptTable rows={data.concepts} onOpen={onOpen} />;
}

export function IntelligenceView({ initialConceptId }: { initialConceptId?: string }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [conceptId, setConceptId] = useState<string | null>(initialConceptId ?? null);

  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  const activeWorkspace = workspaceId || workspaces.data?.[0]?.id || "";
  const subjects = useAsync(
    () =>
      activeWorkspace
        ? subjectsApi.list(activeWorkspace, { limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [activeWorkspace],
  );
  // recommendations are synced on read, so load them first: the dashboard counts pending ones
  const recs = useAsync(() => learnerApi.recommendations(), []);
  const dash = useAsync(
    () =>
      learnerApi.dashboard({
        workspace_id: activeWorkspace || undefined,
        subject_id: subjectId || undefined,
      }),
    [activeWorkspace, subjectId, recs.data],
  );
  const ids = new Set(dash.data?.concepts.map((c) => c.node_id));
  const visibleRecs = (recs.data?.items ?? []).filter(
    (r) => !r.knowledge_node_id || ids.has(r.knowledge_node_id),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {(workspaces.data?.length ?? 0) > 1 && (
          <select
            className={SELECT}
            aria-label="Workspace"
            value={activeWorkspace}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              setSubjectId("");
            }}
          >
            {workspaces.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        )}
        <select
          className={SELECT}
          aria-label="Subject"
          value={subjectId}
          onChange={(e) => setSubjectId(e.target.value)}
        >
          <option value="">All subjects</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <Link className="text-muted-foreground ml-auto text-sm underline" href="/progress">
          Activity and quiz trends are on the Progress page
        </Link>
      </div>

      <div role="tablist" className="border-border flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === t.id
                ? "border-foreground text-foreground font-medium"
                : "text-muted-foreground border-transparent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {conceptId && (
        <ConceptPanel key={conceptId} nodeId={conceptId} onClose={() => setConceptId(null)} />
      )}

      <AsyncSection
        title="Learner intelligence"
        loading={dash.loading}
        error={dash.error}
        onRetry={dash.reload}
        isEmpty={(dash.data?.overview.tracked ?? 0) === 0}
        empty={
          <p className="text-muted-foreground py-8 text-center text-sm">
            No concepts yet. Upload a document and build its knowledge graph, then take quizzes or
            review flashcards to see your understanding here.
          </p>
        }
      >
        {dash.data && (
          <>
            <p className="text-muted-foreground mb-3 text-xs">{dash.data.note}</p>
            <Body
              data={dash.data}
              recs={visibleRecs}
              reloadRecs={recs.reload}
              onOpen={setConceptId}
              tab={tab}
            />
          </>
        )}
      </AsyncSection>
    </div>
  );
}
