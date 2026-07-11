import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type NodeKind = "frontman" | "agent" | "tool" | "external" | "subnetwork" | "middleware";

interface KindStyle {
  bar: string;
  chip: string;
  icon: string;
  border: string;
  type: string;
}

const kindStyles: Record<NodeKind, KindStyle> = {
  frontman: { bar: "bg-node-frontman", chip: "bg-node-frontman/16", icon: "text-node-frontman", border: "border-node-frontman/70", type: "text-node-frontman" },
  agent: { bar: "bg-node-agent", chip: "bg-node-agent/16", icon: "text-node-agent", border: "border-node-agent/70", type: "text-node-agent" },
  tool: { bar: "bg-node-tool", chip: "bg-node-tool/16", icon: "text-node-tool", border: "border-node-tool/75", type: "text-node-tool" },
  external: { bar: "bg-node-external", chip: "bg-node-external/16", icon: "text-node-external", border: "border-node-external/75", type: "text-node-external" },
  subnetwork: { bar: "bg-node-subnetwork", chip: "bg-node-subnetwork/16", icon: "text-node-subnetwork", border: "border-node-subnetwork/75", type: "text-node-subnetwork" },
  middleware: { bar: "bg-node-external", chip: "bg-node-external/16", icon: "text-node-external", border: "border-node-external/75", type: "text-node-external" },
};

export interface AgentNodeProps {
  kind: NodeKind;
  title: string;
  typeLabel: string;
  subtitle?: string;
  icon: ReactNode;
  badge?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function AgentNode({ kind, title, typeLabel, subtitle, icon, badge, className, style }: AgentNodeProps) {
  const s = kindStyles[kind];
  const glowVar = {
    frontman: "--alive-node-frontman",
    agent: "--alive-node-agent",
    tool: "--alive-node-tool",
    external: "--alive-node-external",
    subnetwork: "--alive-node-subnetwork",
    middleware: "--alive-node-external",
  }[kind];
  return (
    <div
      style={{
        boxShadow: `inset 0 0 26px rgb(var(${glowVar}) / 0.16), 0 0 24px -6px rgb(var(${glowVar}) / 0.55), var(--alive-node-lift)`,
        ...style,
      }}
      className={cn("flex overflow-hidden rounded-lg border bg-elevated", s.border, className)}
    >
      <div className={cn("w-1 shrink-0", s.bar)} />
      <div className="flex min-w-0 flex-1 flex-col gap-2 px-3.5 py-3">
        <div className="flex items-center gap-2.5">
          <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", s.chip, s.icon)}>
            {icon}
          </span>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-fg leading-tight break-words">{title}</div>
            <div className={cn("text-[9.5px] font-semibold tracking-wide", s.type)}>{typeLabel}</div>
          </div>
        </div>
        {subtitle && <div className="line-clamp-3 text-xs text-fg-soft break-words">{subtitle}</div>}
        {badge}
      </div>
    </div>
  );
}
