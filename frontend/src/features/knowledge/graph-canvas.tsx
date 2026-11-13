"use client";

import "@xyflow/react/dist/style.css";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeMouseHandler,
} from "@xyflow/react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";
import { RELATIONSHIP_LABELS, type KnowledgeEdge, type KnowledgeNode } from "@/lib/api/knowledge";
import { Button } from "@/components/ui/button";

const NODE_W = 150;

/** Stable hue per node type so the legend and the canvas agree. */
const TYPE_HUE: Record<string, number> = {
  concept: 215,
  topic: 265,
  subtopic: 285,
  term: 30,
  algorithm: 150,
  method: 170,
  formula: 45,
  model: 330,
  theory: 245,
  principle: 195,
  entity: 15,
  example: 95,
  application: 120,
};

export function typeColor(type: string): string {
  return `hsl(${TYPE_HUE[type] ?? 0} 65% 45%)`;
}

interface SimNode {
  id: string;
  x: number;
  y: number;
}

/** Deterministic force layout, run to rest synchronously (graph is capped server-side). */
function layout(
  nodes: KnowledgeNode[],
  edges: KnowledgeEdge[],
  previous: Map<string, { x: number; y: number }>,
): Map<string, { x: number; y: number }> {
  const sim: SimNode[] = nodes.map((n, i) => {
    const prev = previous.get(n.id);
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
    return { id: n.id, x: prev?.x ?? Math.cos(angle) * 200, y: prev?.y ?? Math.sin(angle) * 200 };
  });
  const ids = new Set(sim.map((n) => n.id));
  const links = edges
    .filter((e) => ids.has(e.source_node_id) && ids.has(e.target_node_id))
    .map((e) => ({ source: e.source_node_id, target: e.target_node_id }));
  const simulation = forceSimulation(sim)
    .force("charge", forceManyBody().strength(-420))
    .force("collide", forceCollide(NODE_W / 2 + 14))
    .force(
      "link",
      forceLink<SimNode, { source: string; target: string }>(links)
        .id((d) => d.id)
        .distance(190),
    )
    .force("center", forceCenter(0, 0))
    .stop();
  simulation.tick(Math.min(300, 60 + nodes.length * 2));
  return new Map(sim.map((n) => [n.id, { x: n.x, y: n.y }]));
}

interface CanvasProps {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;
}

type Size = { width: number; height: number };
type Point = { x: number; y: number };

const WIDE_QUERY = "(min-width: 768px)";
function subscribeWide(notify: () => void) {
  const mq = window.matchMedia(WIDE_QUERY);
  mq.addEventListener("change", notify);
  return () => mq.removeEventListener("change", notify);
}
const isWide = () => window.matchMedia(WIDE_QUERY).matches;

function Canvas({ nodes, edges, selectedId, onSelect, onExpand }: CanvasProps) {
  const flow = useReactFlow();
  const wide = useSyncExternalStore(subscribeWide, isWide, () => true);

  const positions = useMemo(() => layout(nodes, edges, new Map()), [nodes, edges]);

  // Controlled graph: xyflow measures each node in the DOM and reports it through
  // `onNodesChange`. The minimap (and node dragging) read size and position from OUR node
  // objects, so we must hand the measurements and drag positions back. Without this the minimap
  // finds no node dimensions and draws no nodes, only an empty box sized to the whole graph.
  const [measured, setMeasured] = useState<Record<string, Size>>({});
  // dragged positions only apply to the layout they were made on; a new layout discards them
  const [moved, setMoved] = useState<{ base: unknown; pos: Record<string, Point> }>({
    base: null,
    pos: {},
  });

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const c of changes) {
        if (c.type === "dimensions" && c.dimensions) {
          const size = { width: c.dimensions.width, height: c.dimensions.height };
          setMeasured((prev) => {
            const cur = prev[c.id];
            if (cur && cur.width === size.width && cur.height === size.height) return prev;
            return { ...prev, [c.id]: size };
          });
        } else if (c.type === "position" && c.position) {
          const point = c.position;
          setMoved((prev) => ({
            base: positions,
            pos: { ...(prev.base === positions ? prev.pos : {}), [c.id]: point },
          }));
        }
      }
    },
    [positions],
  );

  const flowNodes: Node[] = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        position: (moved.base === positions ? moved.pos[n.id] : undefined) ??
          positions.get(n.id) ?? { x: 0, y: 0 },
        measured: measured[n.id],
        initialWidth: NODE_W,
        data: { label: n.name, nodeType: n.node_type },
        ariaLabel: `${n.name}, ${n.node_type}, ${n.degree} connections`,
        selected: n.id === selectedId,
        style: {
          width: NODE_W,
          fontSize: 12,
          padding: 6,
          borderRadius: 8,
          border: `2px solid ${typeColor(n.node_type)}`,
          background: "var(--background)",
          color: "var(--foreground)",
          opacity: n.archived_at ? 0.5 : 1,
          boxShadow: n.id === selectedId ? `0 0 0 3px ${typeColor(n.node_type)}55` : undefined,
        },
      })),
    [nodes, positions, selectedId, measured, moved],
  );

  const flowEdges: Edge[] = useMemo(() => {
    const ids = new Set(nodes.map((n) => n.id));
    return edges
      .filter((e) => ids.has(e.source_node_id) && ids.has(e.target_node_id))
      .map((e) => ({
        id: e.id,
        source: e.source_node_id,
        target: e.target_node_id,
        label: RELATIONSHIP_LABELS[e.relationship_type] ?? e.relationship_type,
        labelStyle: { fontSize: 10 },
        labelBgStyle: { fill: "var(--background)" },
        markerEnd:
          e.relationship_type === "RELATED_TO" || e.relationship_type === "CONTRASTS_WITH"
            ? undefined
            : { type: MarkerType.ArrowClosed },
      }));
  }, [nodes, edges]);

  const fit = useCallback(() => {
    void flow.fitView({ padding: 0.2, duration: 250 });
  }, [flow]);

  useEffect(() => {
    // refit when the node set changes
    const t = setTimeout(fit, 50);
    return () => clearTimeout(t);
  }, [nodes.length, fit]);

  const onNodeClick: NodeMouseHandler = (_, node) => onSelect(node.id);
  const onNodeDoubleClick: NodeMouseHandler = (_, node) => onExpand(node.id);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        nodesConnectable={false}
        nodesDraggable
        fitView
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        aria-label="Knowledge graph"
      >
        <Background />
        <Controls showInteractive={false} />
        {nodes.length > 0 ? (
          <MiniMap
            // drag on the minimap pans the main view; the wheel zooms it; a click centres it
            pannable
            zoomable
            ariaLabel="Graph overview"
            onClick={(_, point) =>
              void flow.setCenter(point.x, point.y, { zoom: flow.getZoom(), duration: 200 })
            }
            // size in px (the minimap scales the whole graph into it); smaller on narrow screens
            style={{
              width: wide ? 200 : 130,
              height: wide ? 140 : 90,
              backgroundColor: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              boxShadow: "0 1px 4px rgb(0 0 0 / 0.12)",
              overflow: "hidden",
            }}
            nodeColor={(node) => typeColor(String(node.data?.nodeType ?? ""))}
            nodeStrokeWidth={0}
            nodeBorderRadius={3}
            // dim everything outside the visible area; the visible area keeps a clear outline
            maskColor="color-mix(in srgb, var(--foreground) 10%, transparent)"
            maskStrokeColor="var(--primary)"
            maskStrokeWidth={2}
          />
        ) : null}
      </ReactFlow>
      <div className="absolute top-2 right-2 flex gap-2">
        <Button size="sm" variant="outline" onClick={fit}>
          Reset view
        </Button>
      </div>
    </div>
  );
}

export function GraphCanvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}

export default GraphCanvas;
