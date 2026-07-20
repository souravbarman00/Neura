import { useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  Panel,
  useReactFlow,
  useNodesState,
  useEdgesState,
  useStore,
  type Edge,
  type ReactFlowState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Crosshair, Lightbulb, Maximize2 } from "lucide-react";
import { useAliveTheme } from "@/theme";
import { FlowNode } from "./FlowNode";
import { GlowEdge } from "./GlowEdge";
import type { AgentFlowNode } from "./layout";

const nodeTypes = { agent: FlowNode };
const edgeTypes = { glow: GlowEdge };

function usePersistedToggle(key: string, defaultOn = false): [boolean, () => void] {
  const [on, setOn] = useState(() => {
    try {
      const v = localStorage.getItem(key);
      return v === null ? defaultOn : v === "1";
    } catch {
      return defaultOn;
    }
  });
  const toggle = () =>
    setOn((v) => {
      const next = !v;
      try {
        localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  return [on, toggle];
}

function Flow({
  inNodes,
  inEdges,
  activeIds,
  activeEdgeIds,
  reverseEdgeIds,
  onNodePick,
}: {
  inNodes: AgentFlowNode[];
  inEdges: Edge[];
  activeIds?: Set<string>;
  activeEdgeIds?: Set<string>;
  reverseEdgeIds?: Set<string>;
  onNodePick?: (id: string) => void;
}) {
  const { fitView } = useReactFlow();
  const { mode } = useAliveTheme();
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentFlowNode>(inNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(inEdges);

  const traceable = activeEdgeIds !== undefined;
  const [follow, toggleFollow] = usePersistedToggle("alive-graph-follow", true);
  const [spotlight, toggleSpotlight] = usePersistedToggle("alive-graph-spotlight");
  const [magnify, toggleMagnify] = usePersistedToggle("alive-graph-magnify");

  const transientPos = useRef(new Map<string, { x: number; y: number }>());

  useEffect(() => {
    transientPos.current.clear();
    setNodes(inNodes);
  }, [inNodes, setNodes]);
  useEffect(() => setEdges(inEdges), [inEdges, setEdges]);

  useEffect(() => {
    const baseIds = new Set(inNodes.map((n) => n.id));
    const NODE_W = 260;
    const phantomParent = new Map<string, string>();
    for (const id of [...(activeEdgeIds ?? []), ...(reverseEdgeIds ?? [])]) {
      const i = id.indexOf("->");
      if (i < 0) continue;
      const tgt = id.slice(i + 2);
      if (tgt && !baseIds.has(tgt) && !phantomParent.has(tgt)) phantomParent.set(tgt, id.slice(0, i));
    }
    const fresh = [...phantomParent.keys()].filter((c) => !transientPos.current.has(c));
    if (fresh.length) {
      const xs = inNodes.map((n) => (n.position?.x ?? 0) + NODE_W);
      const ys = inNodes.map((n) => n.position?.y ?? 0);
      const colX = (xs.length ? Math.max(...xs) : 0) + 140;
      const topY = ys.length ? Math.min(...ys) : 0;
      for (const c of fresh) {
        const slot = transientPos.current.size;
        transientPos.current.set(c, { x: colX, y: topY + slot * 150 });
      }
    }
    const focus = new Set<string>(activeIds ?? []);
    for (const id of [...(activeEdgeIds ?? []), ...(reverseEdgeIds ?? [])]) {
      const i = id.indexOf("->");
      if (i >= 0) {
        focus.add(id.slice(0, i));
        focus.add(id.slice(i + 2));
      }
    }
    const traceOn = spotlight && focus.size > 0;
    setNodes((prev) => {
      const kept = prev
        .filter((n) => !n.data?.transient || phantomParent.has(n.id))
        .map((n) => {
          const on = !!activeIds?.has(n.id);
          const dim = traceOn && !focus.has(n.id);
          return n.data.active === on && !!n.data.dimmed === dim
            ? n
            : { ...n, data: { ...n.data, active: on, dimmed: dim } };
        });
      const have = new Set(kept.map((n) => n.id));
      const added: AgentFlowNode[] = [];
      for (const child of phantomParent.keys()) {
        if (have.has(child)) continue;
        added.push({
          id: child,
          type: "agent",
          position: transientPos.current.get(child) ?? { x: 0, y: 0 },
          data: {
            name: child,
            kind: "middleware",
            subtitle: /middleware/i.test(child) ? "middleware" : "middleware tool",
            active: true,
            transient: true,
          },
        });
      }
      return [...kept, ...added];
    });
  }, [activeIds, activeEdgeIds, reverseEdgeIds, inNodes, setNodes, spotlight]);

  const focusSig =
    [...(activeIds ?? [])].sort().join(",") +
    "|" +
    [...(activeEdgeIds ?? [])].sort().join(",") +
    "|" +
    [...(reverseEdgeIds ?? [])].sort().join(",");
  useEffect(() => {
    const ids = new Set<string>(activeIds ?? []);
    for (const eid of [...(activeEdgeIds ?? []), ...(reverseEdgeIds ?? [])]) {
      const i = eid.indexOf("->");
      if (i >= 0) {
        ids.add(eid.slice(0, i));
        ids.add(eid.slice(i + 2));
      }
    }
    const active = ids.size > 0;
    if (!active) {
      const t = setTimeout(() => fitView({ padding: 0.15, duration: 550, minZoom: 0.05 }), 650);
      return () => clearTimeout(t);
    }
    if (follow) {
      const t = setTimeout(
        () => fitView({ nodes: [...ids].map((id) => ({ id })), padding: 0.5, duration: 550, minZoom: 0.05, maxZoom: 1.25 }),
        140,
      );
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => fitView({ padding: 0.15, duration: 400, minZoom: 0.05 }), 180);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusSig, follow, fitView]);

  useEffect(() => {
    const baseIds = new Set(inEdges.map((e) => e.id));
    const activeSet = activeEdgeIds ?? new Set<string>();
    const revSet = reverseEdgeIds ?? new Set<string>();
    const traceOn = spotlight && (activeSet.size > 0 || revSet.size > 0);
    setEdges((prev) => {
      const kept = prev
        .filter((e) => !e.data?.transient || activeSet.has(e.id) || revSet.has(e.id))
        .map((e) => {
          const on = activeSet.has(e.id);
          const rev = revSet.has(e.id);
          const dim = traceOn && !on && !rev;
          if (!!e.data?.active === on && !!e.data?.reverse === rev && !!e.data?.dimmed === dim) return e;
          return { ...e, data: { ...e.data, active: on, reverse: rev, dimmed: dim } };
        });
      const have = new Set(kept.map((e) => e.id));
      const added: Edge[] = [];
      for (const id of new Set([...activeSet, ...revSet])) {
        if (baseIds.has(id) || have.has(id)) continue;
        const i = id.indexOf("->");
        if (i < 0) continue;
        added.push({
          id,
          source: id.slice(0, i),
          target: id.slice(i + 2),
          type: "glow",
          data: { curve: "float", active: activeSet.has(id), reverse: revSet.has(id), transient: true },
        });
      }
      return [...kept, ...added];
    });
  }, [activeEdgeIds, reverseEdgeIds, inEdges, setEdges, spotlight]);

  useEffect(() => {
    if (inNodes.length) {
      const id = setTimeout(() => fitView({ padding: 0.15, duration: 300, minZoom: 0.05 }), 80);
      return () => clearTimeout(id);
    }
  }, [inNodes, fitView]);

  // Refit whenever the pane itself resizes (e.g. the extension panel opening or the
  // window changing width) so the whole network stays framed in small containers.
  const paneW = useStore((s: ReactFlowState) => Math.round(s.width || 0));
  const paneH2 = useStore((s: ReactFlowState) => Math.round(s.height || 0));
  useEffect(() => {
    if (paneW > 0 && paneH2 > 0 && inNodes.length) {
      const id = setTimeout(() => fitView({ padding: 0.15, minZoom: 0.05, duration: 250 }), 60);
      return () => clearTimeout(id);
    }
  }, [paneW, paneH2, inNodes.length, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      colorMode={mode}
      className={magnify ? "alive-magnify-active" : undefined}
      onNodeClick={onNodePick ? (_, n) => onNodePick(n.id) : undefined}
      fitView
      fitViewOptions={{ padding: 0.15, minZoom: 0.05 }}
      minZoom={0.05}
      nodesDraggable
      nodesConnectable={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
      <Controls showInteractive={false} />
      {traceable && (
        <Panel position="top-right" className="flex flex-col items-end gap-1.5">
          <button
            type="button"
            onClick={toggleFollow}
            aria-pressed={follow}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-semibold shadow-alive-sm transition-colors ${
              follow ? "border-accent bg-accent/15 text-accent" : "border-line-strong bg-panel text-fg-soft hover:bg-hover"
            }`}
          >
            <Crosshair size={13} /> Follow
          </button>
          <button
            type="button"
            onClick={toggleSpotlight}
            aria-pressed={spotlight}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-semibold shadow-alive-sm transition-colors ${
              spotlight ? "border-accent bg-accent/15 text-accent" : "border-line-strong bg-panel text-fg-soft hover:bg-hover"
            }`}
          >
            <Lightbulb size={13} /> Spotlight
          </button>
          <button
            type="button"
            onClick={toggleMagnify}
            aria-pressed={magnify}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-semibold shadow-alive-sm transition-colors ${
              magnify ? "border-accent bg-accent/15 text-accent" : "border-line-strong bg-panel text-fg-soft hover:bg-hover"
            }`}
          >
            <Maximize2 size={13} /> Magnify
          </button>
        </Panel>
      )}
    </ReactFlow>
  );
}

export function NetworkGraph({
  nodes,
  edges,
  activeIds,
  activeEdgeIds,
  reverseEdgeIds,
  onNodePick,
}: {
  nodes: AgentFlowNode[];
  edges: Edge[];
  activeIds?: Set<string>;
  activeEdgeIds?: Set<string>;
  reverseEdgeIds?: Set<string>;
  onNodePick?: (id: string) => void;
}) {
  return (
    <div className="h-full w-full">
      <ReactFlowProvider>
        <Flow
          inNodes={nodes}
          inEdges={edges}
          activeIds={activeIds}
          activeEdgeIds={activeEdgeIds}
          reverseEdgeIds={reverseEdgeIds}
          onNodePick={onNodePick}
        />
      </ReactFlowProvider>
    </div>
  );
}
