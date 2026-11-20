"use client";

import "@xyflow/react/dist/style.css";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
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
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
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

const MIN_ZOOM = 0.05;
const FIT_OPTIONS = { padding: 0.15, minZoom: MIN_ZOOM } as const;
const GRID_GAP_X = NODE_W + 30;
const GRID_GAP_Y = 80;

/**
 * Deterministic layout, run to rest synchronously (graph is capped server-side).
 * Connected nodes get a force layout with a weak pull to the centre, so separate clusters stay
 * near each other instead of drifting apart. Nodes with no relationship are NOT part of the
 * simulation (repulsion with nothing to hold them pushes them far away); they sit in a tidy grid
 * under the connected part.
 */
function layout(
  nodes: KnowledgeNode[],
  edges: KnowledgeEdge[],
  previous: Map<string, { x: number; y: number }>,
): Map<string, { x: number; y: number }> {
  const ids = new Set(nodes.map((n) => n.id));
  const links = edges
    .filter((e) => ids.has(e.source_node_id) && ids.has(e.target_node_id))
    .map((e) => ({ source: e.source_node_id, target: e.target_node_id }));
  const linked = new Set<string>();
  for (const l of links) {
    linked.add(l.source);
    linked.add(l.target);
  }
  const connected = nodes.filter((n) => linked.has(n.id));
  const isolated = nodes.filter((n) => !linked.has(n.id));

  const sim: SimNode[] = connected.map((n, i) => {
    const prev = previous.get(n.id);
    const angle = (i / Math.max(connected.length, 1)) * Math.PI * 2;
    return { id: n.id, x: prev?.x ?? Math.cos(angle) * 200, y: prev?.y ?? Math.sin(angle) * 200 };
  });
  if (sim.length > 0) {
    const simulation = forceSimulation(sim)
      .force("charge", forceManyBody().strength(-420).distanceMax(600))
      .force("collide", forceCollide(NODE_W / 2 + 14))
      .force(
        "link",
        forceLink<SimNode, { source: string; target: string }>(links)
          .id((d) => d.id)
          .distance(190),
      )
      .force("x", forceX(0).strength(0.08))
      .force("y", forceY(0).strength(0.08))
      .stop();
    simulation.tick(Math.min(300, 60 + sim.length * 2));
  }
  const out = new Map(sim.map((n) => [n.id, { x: n.x, y: n.y }]));

  // isolated nodes: a grid roughly as wide as the connected part, below it
  let minX = 0;
  let maxX = 0;
  let maxY = 0;
  for (const p of out.values()) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  }
  const cols = Math.max(
    1,
    Math.min(isolated.length, Math.max(4, Math.round((maxX - minX) / GRID_GAP_X) + 1)),
  );
  const startX = sim.length > 0 ? (minX + maxX) / 2 - ((cols - 1) * GRID_GAP_X) / 2 : 0;
  const startY = sim.length > 0 ? maxY + 140 : 0;
  isolated.forEach((n, i) => {
    out.set(n.id, {
      x: startX + (i % cols) * GRID_GAP_X,
      y: startY + Math.floor(i / cols) * GRID_GAP_Y,
    });
  });
  return out;
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
    void flow.fitView({ ...FIT_OPTIONS, duration: 250 });
  }, [flow]);

  // Real full screen for the graph (the +/-/fit buttons only change the view).
  const frame = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    const onChange = () => {
      setFullscreen(document.fullscreenElement === frame.current);
      setTimeout(fit, 100); // the canvas just changed size
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, [fit]);
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void frame.current?.requestFullscreen?.();
    }
  }, []);

  useEffect(() => {
    // refit when the node set changes
    const t = setTimeout(fit, 50);
    return () => clearTimeout(t);
  }, [nodes.length, fit]);

  const onNodeClick: NodeMouseHandler = (_, node) => onSelect(node.id);
  const onNodeDoubleClick: NodeMouseHandler = (_, node) => onExpand(node.id);

  return (
    <div ref={frame} className="bg-background relative h-full w-full">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        nodesConnectable={false}
        nodesDraggable
        fitView
        fitViewOptions={FIT_OPTIONS}
        minZoom={MIN_ZOOM}
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
        <Button size="sm" variant="outline" onClick={toggleFullscreen} aria-pressed={fullscreen}>
          {fullscreen ? "Exit full screen" : "Full screen"}
        </Button>
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
