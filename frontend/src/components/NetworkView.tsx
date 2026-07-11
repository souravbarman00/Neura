import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Edge } from "@xyflow/react";
import { getGraph } from "../api";
import { NetworkGraph } from "../studio/graph/NetworkGraph";
import { detailToFlow, type AgentFlowNode, type DetailNode, type LayoutMode } from "../studio/graph/layout";
import { ChevronDown } from "../icons";
import CodeView from "./CodeView";

interface Props {
  open: boolean; // expanded (true) vs collapsed to just the header strip (false)
  floating: boolean; // when the rail is collapsed, the graph becomes a movable window
  focus?: boolean; // in focus mode the Code tab is available
  conversationId?: string | null;
  theme?: "light" | "dark";
  network: string;
  activeNodes: Set<string>;
  activeEdges: Set<string>;
  logs: { kind: string; text: string }[];
  busy: boolean;
  onToggle(): void;
}

interface Win {
  x: number;
  y: number;
  w: number;
  h: number;
}
const DEFAULT_WIN: Win = { x: 292, y: 88, w: 500, h: 440 };

function loadWin(): Win {
  try {
    const raw = localStorage.getItem("neura_graph_win");
    if (raw) return { ...DEFAULT_WIN, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return DEFAULT_WIN;
}

export default function NetworkView({
  open,
  floating,
  focus,
  conversationId,
  theme,
  network,
  activeNodes,
  activeEdges,
  logs,
  busy,
  onToggle,
}: Props) {
  const [tab, setTab] = useState<"agents" | "logs" | "code">("agents");
  useEffect(() => {
    if (!focus && tab === "code") setTab("agents"); // Code tab only exists in focus mode
  }, [focus, tab]);
  useEffect(() => {
    if (focus && new URLSearchParams(location.search).get("code")) setTab("code");
  }, [focus]);
  const [detail, setDetail] = useState<DetailNode[]>([]);
  const [layout, setLayout] = useState<LayoutMode>(() =>
    (typeof localStorage !== "undefined" && localStorage.getItem("neura_graph_layout") === "free") ? "free" : "tree"
  );
  const [win, setWin] = useState<Win>(loadWin);

  function chooseLayout(m: LayoutMode) {
    setLayout(m);
    try {
      localStorage.setItem("neura_graph_layout", m);
    } catch {
      /* ignore */
    }
  }
  const dragRef = useRef<
    null | { mode: "move" | "resize"; sx: number; sy: number; ox: number; oy: number; ow: number; oh: number }
  >(null);

  useEffect(() => {
    getGraph(network)
      .then((g) => setDetail((g.detail || []) as DetailNode[]))
      .catch(() => setDetail([]));
  }, [network]);

  const { nodes, edges } = useMemo(() => {
    if (!detail.length) return { nodes: [] as AgentFlowNode[], edges: [] as Edge[] };
    return detailToFlow(detail, layout);
  }, [detail, layout]);

  useEffect(() => {
    if (floating) {
      try {
        localStorage.setItem("neura_graph_win", JSON.stringify(win));
      } catch {
        /* ignore */
      }
    }
  }, [win, floating]);

  const onMove = useCallback((e: PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (d.mode === "move") {
      const maxX = window.innerWidth - 140;
      const maxY = window.innerHeight - 60;
      setWin((w) => ({
        ...w,
        x: Math.min(Math.max(8, d.ox + dx), maxX),
        y: Math.min(Math.max(8, d.oy + dy), maxY),
      }));
    } else {
      setWin((w) => ({ ...w, w: Math.max(380, d.ow + dx), h: Math.max(220, d.oh + dy) }));
    }
  }, []);

  const endDrag = useCallback(() => {
    dragRef.current = null;
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", endDrag);
    document.body.style.userSelect = "";
  }, [onMove]);

  function begin(mode: "move" | "resize", e: React.PointerEvent) {
    dragRef.current = { mode, sx: e.clientX, sy: e.clientY, ox: win.x, oy: win.y, ow: win.w, oh: win.h };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", endDrag);
    document.body.style.userSelect = "none";
  }

  function startMove(e: React.PointerEvent) {
    if (!floating) return;
    if ((e.target as HTMLElement).closest("button")) return; // let header controls work
    begin("move", e);
  }
  function startResize(e: React.PointerEvent) {
    e.stopPropagation();
    begin("resize", e);
  }

  const style: React.CSSProperties = floating
    ? { left: win.x, top: win.y, width: win.w, height: open ? win.h : undefined }
    : {};

  return (
    <div
      className={"netdock" + (open ? "" : " collapsed") + (floating ? " floating" : "")}
      style={style}
    >
      <div
        className="netdock-head"
        onPointerDown={startMove}
        style={floating ? { cursor: "move" } : undefined}
      >
        <span className={"live-badge" + (busy ? " on" : "")}>
          <span className="live-dot" /> LIVE
        </span>
        <div className="nettabs">
          <button className={tab === "agents" ? "on" : ""} onClick={() => setTab("agents")}>Agents</button>
          <button className={tab === "logs" ? "on" : ""} onClick={() => setTab("logs")}>
            Logs {logs.length > 0 && <span className="tabcount">{logs.length}</span>}
          </button>
          {focus && (
            <button className={tab === "code" ? "on" : ""} onClick={() => setTab("code")}>Code</button>
          )}
        </div>
        <div className="grow" />
        {open && tab === "agents" && (
          <div className="nettabs netlayout" title="Graph layout">
            <button className={layout === "tree" ? "on" : ""} onClick={() => chooseLayout("tree")}>Tree</button>
            <button className={layout === "free" ? "on" : ""} onClick={() => chooseLayout("free")}>Free flow</button>
          </div>
        )}
        <button
          className={"iconbtn sm netcollapse" + (open ? "" : " up")}
          onClick={onToggle}
          title={open ? "Collapse graph" : "Expand graph"}
        >
          <ChevronDown />
        </button>
      </div>

      {open && tab === "code" ? (
        <div className="netcode">
          <CodeView conversationId={conversationId ?? null} theme={theme ?? "dark"} />
        </div>
      ) : open &&
        (tab === "agents" ? (
          <div className="netgraph">
            {nodes.length === 0 ? (
              <div className="muted-empty" style={{ padding: 24 }}>No graph available.</div>
            ) : (
              <NetworkGraph nodes={nodes} edges={edges} activeIds={activeNodes} activeEdgeIds={activeEdges} />
            )}
          </div>
        ) : (
          <div className="netlogs">
            {logs.length === 0 ? (
              <div className="muted-empty" style={{ padding: 24 }}>Ask Neura something to see the live trace.</div>
            ) : (
              logs.map((l, i) => (
                <div className={`logrow k-${l.kind}`} key={i}>
                  <span className="logkind">{l.kind}</span>
                  <span className="logtext">{l.text}</span>
                </div>
              ))
            )}
          </div>
        ))}

      {floating && open && <div className="netresize" onPointerDown={startResize} title="Resize" />}
    </div>
  );
}
