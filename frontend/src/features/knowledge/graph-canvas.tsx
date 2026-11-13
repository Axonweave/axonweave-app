"use client";

import "@xyflow/react/dist/style.css";

import { useCallback, useEffect, useMemo } from "react";
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

function Canvas({ nodes, edges, selectedId, onSelect, onExpand }: CanvasProps) {
  const flow = useReactFlow();

  const positions = useMemo(() => layout(nodes, edges, new Map()), [nodes, edges]);

  const flowNodes: Node[] = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        position: positions.get(n.id) ?? { x: 0, y: 0 },
        data: { label: n.name },
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
    [nodes, positions, selectedId],
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
        <MiniMap pannable zoomable className="!hidden md:!block" />
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
