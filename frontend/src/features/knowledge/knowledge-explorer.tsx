"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSpinner } from "@/components/ui/loading";
import { Pager } from "@/components/ui/pager";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  NODE_TYPES,
  RELATIONSHIP_LABELS,
  RELATIONSHIP_TYPES,
  knowledgeApi,
  type KnowledgeEdge,
  type KnowledgeNode,
  type NodeType,
} from "@/lib/api/knowledge";
import { subjectsApi } from "@/lib/api/subjects";
import { workspacesApi } from "@/lib/api/workspaces";
import { DuplicatesView } from "./duplicates-view";
import { GenerateSubjectGraph } from "./generate-subject-graph";
import { NodeDetailPanel } from "./node-detail-panel";

const GraphCanvas = dynamic(() => import("./graph-canvas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center" aria-busy="true">
      <LoadingSpinner />
    </div>
  ),
});

const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";
const PAGE = 20;
/** Client-side ceiling for the canvas; expansion stops adding past this. */
const MAX_CANVAS_NODES = 300;

type View = "graph" | "list" | "duplicates";

export function KnowledgeExplorer({ initialNodeId }: { initialNodeId?: string }) {
  const { toast } = useToast();
  const [view, setView] = useState<View>("graph");
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [nodeType, setNodeType] = useState("");
  const [relTypes, setRelTypes] = useState<string[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(initialNodeId ?? null);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  // expansions belong to the base graph they were loaded on; a new base graph discards them
  const [extra, setExtra] = useState<{
    base: unknown;
    nodes: KnowledgeNode[];
    edges: KnowledgeEdge[];
  }>({ base: null, nodes: [], edges: [] });
  const [showAdd, setShowAdd] = useState(false);

  const workspaces = useAsync(() => workspacesApi.list().then((r) => r.data), []);
  const activeWorkspace = workspaceId || workspaces.data?.[0]?.id || "";
  const subjects = useAsync(
    () =>
      activeWorkspace
        ? subjectsApi.list(activeWorkspace, { limit: 100 }).then((r) => r.data)
        : Promise.resolve(null),
    [activeWorkspace],
  );

  // debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(searchInput.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const filters = useMemo(
    () => ({
      workspace_id: activeWorkspace || undefined,
      subject_id: subjectId || undefined,
      node_type: nodeType || undefined,
      q: q || undefined,
    }),
    [activeWorkspace, subjectId, nodeType, q],
  );
  const relKey = relTypes.join(",");

  const graph = useAsync(
    () => (activeWorkspace ? knowledgeApi.graph(filters, relTypes) : Promise.resolve(null)),
    [filters, relKey, version],
  );
  const list = useAsync(
    () =>
      view === "list" && activeWorkspace
        ? knowledgeApi.listNodes({ ...filters, limit: PAGE, offset })
        : Promise.resolve(null),
    [filters, offset, view, version],
  );

  const merged = useMemo(() => {
    const nodes = new Map<string, KnowledgeNode>();
    const edges = new Map<string, KnowledgeEdge>();
    const own = extra.base === graph.data ? extra : { nodes: [], edges: [] };
    for (const n of [...(graph.data?.nodes ?? []), ...own.nodes]) nodes.set(n.id, n);
    for (const e of [...(graph.data?.edges ?? []), ...own.edges]) edges.set(e.id, e);
    return { nodes: [...nodes.values()], edges: [...edges.values()] };
  }, [graph.data, extra]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const expand = useCallback(
    async (id: string) => {
      if (merged.nodes.length >= MAX_CANVAS_NODES) {
        toast({ title: "The graph is full. Narrow the filters to see other concepts." });
        return;
      }
      try {
        const g = await knowledgeApi.expand(id, 1, 40, relTypes);
        const base = graph.data;
        setExtra((prev) => {
          const keep = prev.base === base ? prev : { nodes: [], edges: [] };
          return { base, nodes: [...keep.nodes, ...g.nodes], edges: [...keep.edges, ...g.edges] };
        });
        if (g.truncated) toast({ title: "Showing the strongest connections only." });
      } catch {
        toast({ title: "Could not load neighbours.", variant: "destructive" });
      }
    },
    [merged.nodes.length, relTypes, toast, graph.data],
  );

  const toggleRel = (t: string) => {
    setRelTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));
  };

  const hasFilter = !!(subjectId || nodeType || q || relTypes.length);

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-end gap-3"
        aria-label="Filter concepts"
        onSubmit={(e) => e.preventDefault()}
      >
        {(workspaces.data?.length ?? 0) > 1 ? (
          <label className="text-sm">
            <span className="text-muted-foreground mb-1 block text-xs">Workspace</span>
            <select
              className={SELECT}
              value={activeWorkspace}
              onChange={(e) => {
                setWorkspaceId(e.target.value);
                setSubjectId("");
                setOffset(0);
              }}
            >
              {workspaces.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="text-sm">
          <span className="text-muted-foreground mb-1 block text-xs">Subject</span>
          <select
            className={SELECT}
            value={subjectId}
            onChange={(e) => {
              setSubjectId(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All subjects</option>
            {subjects.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground mb-1 block text-xs">Type</span>
          <select
            className={SELECT}
            value={nodeType}
            onChange={(e) => {
              setNodeType(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All types</option>
            {NODE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground mb-1 block text-xs">Search</span>
          <input
            type="search"
            className={`${SELECT} w-44`}
            placeholder="Concept or alias"
            maxLength={100}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </label>
        <details className="text-sm">
          <summary className="border-input bg-background flex h-9 cursor-pointer items-center rounded-md border px-2">
            Relationships{relTypes.length ? ` (${relTypes.length})` : ""}
          </summary>
          <fieldset className="bg-card absolute z-20 mt-1 space-y-1 rounded-md border p-2 shadow">
            <legend className="sr-only">Relationship types</legend>
            {RELATIONSHIP_TYPES.map((t) => (
              <label key={t} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={relTypes.includes(t)}
                  onChange={() => toggleRel(t)}
                />
                {RELATIONSHIP_LABELS[t]}
              </label>
            ))}
          </fieldset>
        </details>
        {hasFilter ? (
          <button
            type="button"
            className="text-primary h-9 text-sm underline"
            onClick={() => {
              setSubjectId("");
              setNodeType("");
              setSearchInput("");
              setRelTypes([]);
            }}
          >
            Clear filters
          </button>
        ) : null}
        <div className="ml-auto flex gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => setShowAdd((s) => !s)}>
            Add concept
          </Button>
        </div>
      </form>

      {subjectId ? (
        <GenerateSubjectGraph
          key={subjectId} /* a different subject starts from a clean slate */
          subjectId={subjectId}
          subjectName={subjects.data?.find((s) => s.id === subjectId)?.name ?? "this subject"}
          onProgress={refresh}
        />
      ) : null}

      {showAdd && activeWorkspace ? (
        <AddConcept
          workspaceId={activeWorkspace}
          subjectId={subjectId || undefined}
          onDone={(created) => {
            setShowAdd(false);
            if (created) refresh();
          }}
        />
      ) : null}

      <div role="tablist" aria-label="Knowledge views" className="flex gap-1 border-b">
        {(
          [
            ["graph", "Graph"],
            ["list", "List"],
            ["duplicates", "Duplicates"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={view === id}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              view === id
                ? "border-primary text-foreground font-medium"
                : "text-muted-foreground border-transparent"
            }`}
            onClick={() => setView(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0">
          {view === "graph" ? (
            <AsyncSection
              title="Graph"
              loading={graph.loading}
              error={graph.error}
              onRetry={graph.reload}
              isEmpty={!merged.nodes.length}
              empty={
                <EmptyState
                  title={hasFilter ? "No concepts match these filters" : "No concepts yet"}
                  description={
                    hasFilter
                      ? "Try clearing a filter."
                      : "Pick a subject and generate its knowledge graph from your processed documents, or add a concept yourself."
                  }
                />
              }
            >
              {graph.data?.truncated ? (
                <p className="text-muted-foreground mb-2 text-xs" role="status">
                  Showing {merged.nodes.length} of {graph.data.total_nodes} concepts. Narrow the
                  filters or expand a concept to see more.
                </p>
              ) : null}
              <div className="h-[60vh] min-h-[360px] overflow-hidden rounded-lg border">
                <GraphCanvas
                  nodes={merged.nodes}
                  edges={merged.edges}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onExpand={expand}
                />
              </div>
              <p className="text-muted-foreground mt-2 text-xs">
                Select a concept for details. Double-click to load its neighbours. Prefer the List
                tab for keyboard-only use.
              </p>
            </AsyncSection>
          ) : null}

          {view === "list" ? (
            <AsyncSection
              title="Concepts"
              loading={list.loading}
              error={list.error}
              onRetry={list.reload}
              isEmpty={!list.data?.data.length}
              empty={<EmptyState title="No concepts found" />}
            >
              <ul className="divide-y rounded-lg border">
                {list.data?.data.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      className="hover:bg-muted flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm"
                      onClick={() => setSelectedId(n.id)}
                      aria-pressed={selectedId === n.id}
                    >
                      <span className="min-w-0">
                        <span className="block font-medium break-words">{n.name}</span>
                        <span className="text-muted-foreground block text-xs">
                          {n.node_type} · {n.degree} connections · {n.evidence_count} sources
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <Pager
                offset={offset}
                limit={PAGE}
                total={list.data?.total ?? 0}
                onChange={setOffset}
              />
            </AsyncSection>
          ) : null}

          {view === "duplicates" ? (
            <DuplicatesView workspaceId={activeWorkspace || undefined} onChanged={refresh} />
          ) : null}
        </div>

        {selectedId ? (
          <NodeDetailPanel
            key={selectedId}
            nodeId={selectedId}
            onSelect={setSelectedId}
            onChanged={refresh}
            onExpand={expand}
            onClose={() => setSelectedId(null)}
          />
        ) : null}
      </div>
    </div>
  );
}

function AddConcept({
  workspaceId,
  subjectId,
  onDone,
}: {
  workspaceId: string;
  subjectId?: string;
  onDone: (created: boolean) => void;
}) {
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [type, setType] = useState<NodeType>("concept");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await knowledgeApi.createNode({
        workspace_id: workspaceId,
        subject_id: subjectId ?? null,
        name: name.trim(),
        node_type: type,
      });
      toast({ title: "Concept added" });
      onDone(true);
    } catch (err) {
      toast({
        title:
          err instanceof ApiRequestError && err.status === 409
            ? "That concept already exists."
            : "Could not add the concept.",
        variant: "destructive",
      });
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="bg-card flex flex-wrap items-end gap-3 rounded-lg border p-3"
      aria-label="Add concept"
    >
      <label className="text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Name</span>
        <input
          className={`${SELECT} w-56`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={200}
        />
      </label>
      <label className="text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Type</span>
        <select
          className={SELECT}
          value={type}
          onChange={(e) => setType(e.target.value as NodeType)}
        >
          {NODE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" size="sm" disabled={saving || !name.trim()}>
        Add
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={() => onDone(false)}>
        Cancel
      </Button>
    </form>
  );
}
