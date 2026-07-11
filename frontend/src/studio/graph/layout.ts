import type { Edge, Node } from "@xyflow/react";
import dagre from "@dagrejs/dagre";

export interface AgentDef {
  instructions?: string;
  description?: string;
  tools?: string[];
  toolbox?: string;
  class?: string;
  command?: string;
  args?: Record<string, unknown>;
}
export type Definition = Record<string, AgentDef>;

export type NodeKind = "frontman" | "agent" | "tool" | "subnetwork" | "middleware";

export interface NodeParam {
  name: string;
  type: string;
  required: boolean;
}
export interface NodeDetails {
  description?: string;
  model?: string;
  modelInherited?: boolean;
  fallbacks?: string[];
  calls?: string[];
  params?: NodeParam[];
  toolClass?: string;
  toolbox?: string;
}

export interface AgentNodeData extends Record<string, unknown> {
  name: string;
  kind: NodeKind;
  subtitle: string;
  details?: NodeDetails;
  active?: boolean;
  selected?: boolean;
  transient?: boolean;
  dimmed?: boolean;
}
export type AgentFlowNode = Node<AgentNodeData, "agent">;

export type LayoutMode = "tree" | "free";

interface Spec {
  name: string;
  kind: NodeKind;
  subtitle: string;
  tools: string[];
  details?: NodeDetails;
}

const NODE_W = 260;
const NODE_H = 172;

function dagreLayout(
  names: string[],
  downstream: Record<string, string[]>,
): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "TB",
    nodesep: 90,
    ranksep: 170,
    ranker: "network-simplex",
    marginx: 60,
    marginy: 60,
  });
  g.setDefaultEdgeLabel(() => ({}));
  names.forEach((n) => g.setNode(n, { width: NODE_W, height: NODE_H }));
  for (const n of names)
    for (const t of downstream[n] ?? []) if (names.includes(t)) g.setEdge(n, t);
  dagre.layout(g);
  const pos: Record<string, { x: number; y: number }> = {};
  names.forEach((n) => {
    const nd = g.node(n);
    pos[n] = { x: nd.x - NODE_W / 2, y: nd.y - NODE_H / 2 };
  });
  return pos;
}

function radialLayout(
  names: string[],
  downstream: Record<string, string[]>,
): Record<string, { x: number; y: number }> {
  const pos: Record<string, { x: number; y: number }> = {};
  if (!names.length) return pos;

  const referenced = new Set<string>();
  for (const n of names) (downstream[n] ?? []).forEach((t) => referenced.add(t));
  const root = names.find((n) => !referenced.has(n)) ?? names[0];

  const depth: Record<string, number> = { [root]: 0 };
  const children: Record<string, string[]> = Object.fromEntries(names.map((n) => [n, []]));
  const seen = new Set([root]);
  const queue = [root];
  while (queue.length) {
    const cur = queue.shift() as string;
    for (const t of downstream[cur] ?? []) {
      if (!seen.has(t)) {
        seen.add(t);
        depth[t] = depth[cur] + 1;
        children[cur].push(t);
        queue.push(t);
      }
    }
  }
  for (const n of names) if (!seen.has(n)) { seen.add(n); depth[n] = 1; children[root].push(n); }

  const totalLeaves = Math.max(1, names.filter((n) => children[n].length === 0).length);
  let cursor = 0;
  const angle: Record<string, number> = {};
  const assign = (node: string): void => {
    const ch = children[node];
    if (!ch.length) {
      angle[node] = ((cursor + 0.5) / totalLeaves) * 2 * Math.PI;
      cursor++;
      return;
    }
    ch.forEach(assign);
    angle[node] = ch.reduce((s, c) => s + angle[c], 0) / ch.length;
  };
  assign(root);

  const maxDepth = names.reduce((m, n) => Math.max(m, depth[n]), 0);
  const byDepth: Record<number, string[]> = {};
  names.forEach((n) => (byDepth[depth[n]] ??= []).push(n));
  const SLOT = NODE_W + 96;
  const RING_GAP = NODE_H + 220;
  const radiusAt: Record<number, number> = { 0: 0 };
  for (let d = 1; d <= maxDepth; d++) {
    const count = byDepth[d]?.length ?? 0;
    const fit = (count * SLOT) / (2 * Math.PI);
    radiusAt[d] = Math.max(fit, (radiusAt[d - 1] ?? 0) + RING_GAP, d * 420);
  }

  names.forEach((n) => {
    const r = radiusAt[depth[n]] ?? 0;
    const x = r * Math.cos(angle[n]);
    const y = r * Math.sin(angle[n]);
    pos[n] = { x: x - NODE_W / 2, y: y - NODE_H / 2 };
  });
  return pos;
}

function separateNodes(
  pos: Record<string, { x: number; y: number }>,
  names: string[],
  gap = 48,
): void {
  const minX = NODE_W + gap;
  const minY = NODE_H + gap;
  for (let iter = 0; iter < 240; iter++) {
    let moved = false;
    for (let a = 0; a < names.length; a++) {
      for (let b = a + 1; b < names.length; b++) {
        const pa = pos[names[a]];
        const pb = pos[names[b]];
        if (!pa || !pb) continue;
        const dx = pa.x - pb.x;
        const dy = pa.y - pb.y;
        const ox = minX - Math.abs(dx);
        const oy = minY - Math.abs(dy);
        if (ox > 0 && oy > 0) {
          if (ox <= oy) {
            const s = (ox / 2) * (dx < 0 ? -1 : 1);
            pa.x += s;
            pb.x -= s;
          } else {
            const s = (oy / 2) * (dy < 0 ? -1 : 1);
            pa.y += s;
            pb.y -= s;
          }
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
}

function computeByLevel(
  names: string[],
  downstream: Record<string, string[]>,
): { root: string | null; byLevel: Record<number, string[]> } {
  const referenced = new Set<string>();
  for (const n of names) (downstream[n] ?? []).forEach((t) => referenced.add(t));
  const roots = names.filter((n) => !referenced.has(n));
  const root = roots[0] ?? names[0] ?? null;

  const level: Record<string, number> = {};
  const queue: string[] = [];
  (roots.length ? roots : root ? [root] : []).forEach((r) => {
    level[r] = 0;
    queue.push(r);
  });
  let guard = 0;
  while (queue.length && guard++ < 10_000) {
    const cur = queue.shift() as string;
    for (const t of downstream[cur] ?? []) {
      const next = level[cur] + 1;
      if (!(t in level) || next > level[t]) {
        level[t] = next;
        queue.push(t);
      }
    }
  }
  names.forEach((n) => {
    if (!(n in level)) level[n] = 0;
  });
  const byLevel: Record<number, string[]> = {};
  names.forEach((n) => (byLevel[level[n]] ??= []).push(n));
  return { root, byLevel };
}

function buildFlow(
  specs: Spec[],
  mode: LayoutMode,
): { nodes: AgentFlowNode[]; edges: Edge[] } {
  specs = specs.filter((s) => s.name && s.name.trim());
  if (specs.length === 0) return { nodes: [], edges: [] };
  const present = new Set(specs.map((s) => s.name));
  const subRefs = new Set<string>();
  for (const s of specs)
    for (const t of s.tools)
      if (typeof t === "string" && t.startsWith("/") && !present.has(t)) subRefs.add(t);
  if (subRefs.size)
    specs = [
      ...specs,
      ...[...subRefs].map((name) => ({
        name,
        kind: "subnetwork" as NodeKind,
        subtitle: "sub-network",
        tools: [] as string[],
      })),
    ];
  const names = specs.map((s) => s.name);
  const known = new Set(names);
  const byName = Object.fromEntries(specs.map((s) => [s.name, s]));
  const downstream = Object.fromEntries(
    specs.map((s) => [s.name, s.tools.filter((t) => known.has(t))]),
  );
  const pos = mode === "free" ? radialLayout(names, downstream) : dagreLayout(names, downstream);
  separateNodes(pos, names);

  const nodes: AgentFlowNode[] = names.map((n) => ({
    id: n,
    type: "agent",
    position: pos[n] ?? { x: 0, y: 0 },
    data: { name: n, kind: byName[n].kind, subtitle: byName[n].subtitle, details: byName[n].details },
  }));
  const curve = mode === "free" ? "floatCurve" : "float";
  const edges: Edge[] = [];
  for (const n of names)
    for (const t of downstream[n])
      edges.push({ id: `${n}->${t}`, source: n, target: t, type: "glow", data: { curve } });
  return { nodes, edges };
}

function kindOf(entry: AgentDef, name: string, root: string): NodeKind {
  const hasBody =
    !!entry &&
    (!!entry.instructions?.length ||
      !!entry.description?.length ||
      (Array.isArray(entry.tools) && entry.tools.length > 0));
  if (!hasBody) return "tool";
  return name === root ? "frontman" : "agent";
}

export function definitionToFlow(
  def: Definition,
  mode: LayoutMode = "tree",
  networkLlm?: Record<string, unknown>,
) {
  const names = Object.keys(def ?? {});
  if (names.length === 0) return { nodes: [], edges: [] };
  const downstream = Object.fromEntries(
    names.map((n) => [n, (def[n].tools ?? []).filter((t) => def[t] !== undefined)]),
  );
  const { root } = computeByLevel(names, downstream);
  const fbRaw = (networkLlm?.fallbacks as { model_name?: string; class?: string }[] | undefined) ?? [];
  const fallbacks = Array.isArray(fbRaw)
    ? fbRaw.map((f) => f?.model_name || f?.class || "").filter(Boolean)
    : [];
  const model = (networkLlm?.model_name as string) || undefined;
  const specs: Spec[] = names.map((n) => {
    const kind = kindOf(def[n], n, root ?? "");
    const isTool = kind === "tool";
    return {
      name: n,
      kind,
      subtitle: def[n].description ?? "",
      tools: def[n].tools ?? [],
      details: {
        description: def[n].description ?? undefined,
        calls: def[n].tools ?? [],
        toolClass: def[n].class,
        toolbox: def[n].toolbox,
        model: isTool ? undefined : model,
        modelInherited: isTool || !model ? undefined : true,
        fallbacks: isTool || !fallbacks.length ? undefined : fallbacks,
      },
    };
  });
  return buildFlow(specs, mode);
}

const DISPLAY_TO_KIND: Record<string, NodeKind> = {
  front_man: "frontman",
  llm_agent: "agent",
  coded_tool: "tool",
  toolbox: "tool",
  subnetwork: "subnetwork",
};

export interface DetailNode {
  name: string;
  display_as: string;
  description?: string | null;
  tools?: string[];
  model?: string;
  modelInherited?: boolean;
  fallbacks?: string[];
  params?: NodeParam[];
  class?: string | null;
  toolbox?: string | null;
}

export function detailToFlow(nodes: DetailNode[], mode: LayoutMode = "tree") {
  if (!nodes.length) return { nodes: [], edges: [] };
  const specs: Spec[] = nodes.map((n) => ({
    name: n.name,
    kind: DISPLAY_TO_KIND[n.display_as] ?? "agent",
    subtitle: n.description ?? "",
    tools: n.tools ?? [],
    details: {
      description: n.description ?? undefined,
      model: n.model,
      modelInherited: n.modelInherited,
      fallbacks: n.fallbacks,
      calls: n.tools ?? [],
      params: n.params,
      toolClass: n.class ?? undefined,
      toolbox: n.toolbox ?? undefined,
    },
  }));
  return buildFlow(specs, mode);
}
