import type { CSSProperties, ReactNode } from "react";
import { Handle, Position, useStore, type NodeProps } from "@xyflow/react";
import { MessageCircle, Cpu, Wrench, Network, Blocks } from "lucide-react";
import { AgentNode } from "@/components";
import type { AgentFlowNode, NodeKind, NodeDetails } from "./layout";

const FISHEYE_TARGET = 0.9;
const FISHEYE_MAX = 6;

const META: Record<NodeKind, { label: string; icon: ReactNode }> = {
  frontman: { label: "FRONT MAN", icon: <MessageCircle size={18} /> },
  agent: { label: "LLM AGENT", icon: <Cpu size={18} /> },
  tool: { label: "TOOL", icon: <Wrench size={18} /> },
  subnetwork: { label: "SUB-NETWORK", icon: <Network size={18} /> },
  middleware: { label: "MIDDLEWARE", icon: <Blocks size={18} /> },
};

const HIGHLIGHT: Record<NodeKind, string> = {
  frontman: "251 191 36",
  agent: "251 146 60",
  tool: "236 72 153",
  subnetwork: "129 140 248",
  middleware: "245 158 11",
};

const NODE_VAR: Record<NodeKind, string> = {
  frontman: "--alive-node-frontman",
  agent: "--alive-node-agent",
  tool: "--alive-node-tool",
  subnetwork: "--alive-node-subnetwork",
  middleware: "--alive-node-external",
};

export function FlowNode({ data, positionAbsoluteY = 0 }: NodeProps<AgentFlowNode>) {
  const meta = META[data.kind];
  const zoom = useStore((s) => s.transform[2]) || 1;
  const panY = useStore((s) => s.transform[1]) || 0;
  const paneH = useStore((s) => s.height || 800);
  const magnify = Math.min(Math.max(FISHEYE_TARGET / zoom, 1), FISHEYE_MAX);
  const nodeTopScreen = panY + positionAbsoluteY * zoom;
  const tipBelow = nodeTopScreen < paneH * 0.5;
  const scaleCls = [
    "alive-node-scale rounded-lg",
    data.active ? "alive-node-active" : "",
    data.selected ? "alive-node-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const dimmed = !!data.dimmed;
  const style = {
    width: 260,
    "--node-hl": HIGHLIGHT[data.kind],
    "--node-color": `var(${NODE_VAR[data.kind]})`,
    "--magnify": magnify,
    opacity: dimmed ? 0.22 : 1,
    transition: "opacity 140ms ease",
  } as CSSProperties;
  return (
    <div style={style} className="group relative">
      <Handle type="target" position={Position.Top} className="alive-handle" />
      <div className={`${scaleCls} relative`}>
        <AgentNode
          className="w-full"
          kind={data.kind}
          title={data.name}
          typeLabel={meta.label}
          subtitle={data.subtitle || undefined}
          icon={meta.icon}
        />
        <NodeTooltip name={data.name} label={meta.label} details={data.details} below={tipBelow} />
      </div>
      <Handle type="source" position={Position.Bottom} className="alive-handle" />
    </div>
  );
}

function NodeTooltip({ name, label, details, below }: { name: string; label: string; details?: NodeDetails; below?: boolean }) {
  if (!details) return null;
  const { description, model, modelInherited, fallbacks, calls, params, toolClass, toolbox } = details;
  const hasBody =
    description || model || (fallbacks && fallbacks.length) || (calls && calls.length) || (params && params.length) || toolClass || toolbox;
  if (!hasBody) return null;
  const place = below ? "top-full mt-2" : "bottom-full mb-2";
  return (
    <div className={`pointer-events-none absolute ${place} left-1/2 z-[100] hidden w-[290px] -translate-x-1/2 rounded-lg border border-line-strong bg-panel p-3 text-left shadow-alive-lg group-hover:block`}>
      <div className="mb-1 flex items-center gap-1.5">
        <span className="font-mono text-[12px] font-semibold text-fg">{name}</span>
        <span className="rounded-full bg-hover px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-fg-muted">
          {label}
        </span>
      </div>
      {description && <p className="mb-2 text-[11px] leading-snug text-fg-soft">{description}</p>}
      <div className="flex flex-col gap-1 text-[10.5px]">
        {(toolClass || toolbox) && (
          <Row label={toolClass ? "Class" : "Toolbox"} value={<span className="font-mono">{toolClass || toolbox}</span>} />
        )}
        {model && (
          <Row
            label="Model"
            value={
              <span className="font-mono">
                {model}
                {modelInherited && <span className="ml-1 not-italic text-fg-muted">(inherited)</span>}
              </span>
            }
          />
        )}
        {fallbacks && fallbacks.length > 0 && (
          <Row label="Fallbacks" value={<span className="font-mono">{fallbacks.join(" → ")}</span>} />
        )}
        {calls && calls.length > 0 && (
          <Row
            label="Calls"
            value={
              <span className="flex flex-wrap gap-1">
                {calls.map((c) => (
                  <span key={c} className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[10px] text-accent">
                    {c}
                  </span>
                ))}
              </span>
            }
          />
        )}
        {params && params.length > 0 && (
          <Row
            label="Receives"
            value={
              <span className="flex flex-col gap-0.5">
                {params.map((p) => (
                  <span key={p.name} className="font-mono text-[10px]">
                    {p.name}
                    <span className="text-fg-muted"> : {p.type}</span>
                    {p.required && <span className="text-danger"> *</span>}
                  </span>
                ))}
              </span>
            }
          />
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="w-16 shrink-0 font-semibold text-fg-muted">{label}</span>
      <span className="min-w-0 flex-1 text-fg-soft">{value}</span>
    </div>
  );
}
