import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Edge } from "@xyflow/react";
import { getGraph } from "../api";
import { NetworkGraph } from "../studio/graph/NetworkGraph";
import { detailToFlow, type AgentFlowNode, type DetailNode, type LayoutMode, type NodeDetails } from "../studio/graph/layout";
import { ChevronDown, Maximize, Minimize } from "../icons";
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
  paperUrl?: string; // when set, a "Paper" tab (embedded PDF) replaces the Code tab
  // When defined, the header control becomes a Maximize/Minimize toggle (driven by
  // this flag) instead of the graph collapse chevron — used by the Radar to make this
  // panel fill the whole left side.
  expanded?: boolean;
  // Click an LLM agent node → edit its model/provider. Only wired in the main Neura view.
  onEditAgent?(agent: string, details: NodeDetails): void;
  // Bump to force a graph refetch (e.g. after an agent's model changed + runtime reload).
  refreshKey?: number;
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
  paperUrl,
  expanded,
  onEditAgent,
  refreshKey,
}: Props) {
  const [tab, setTab] = useState<"agents" | "logs" | "code" | "paper">(paperUrl ? "paper" : "agents");
  const [full, setFull] = useState(false);
  useEffect(() => {
    if (!focus && tab === "code") setTab("agents"); // Code tab only exists in focus mode
    if (!paperUrl && tab === "paper") setTab("agents");
  }, [focus, paperUrl, tab]);
  useEffect(() => {
    if (focus && new URLSearchParams(location.search).get("code")) setTab("code");
  }, [focus]);
  const [detail, setDetail] = useState<DetailNode[]>([]);
  const [layout, setLayout] = useState<LayoutMode>(() =>
    (typeof localStorage !== "undefined" && localStorage.getItem("neura_graph_layout") === "tree") ? "tree" : "free"
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
    // Poll until the graph is available: at (standalone) app startup the UI backend
    // can answer before the neuro-san server has finished loading its networks, so the
    // first fetch may come back empty. Retry with backoff until we get nodes, then stop.
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let tries = 0;
    const poll = () => {
      getGraph(network)
        .then((g) => {
          if (cancelled) return;
          const d = (g.detail || []) as DetailNode[];
          setDetail(d);
          if (d.length === 0 && tries < 20) {
            tries += 1;
            timer = setTimeout(poll, Math.min(500 + tries * 400, 3000));
          }
        })
        .catch(() => {
          if (cancelled) return;
          setDetail([]);
          if (tries < 20) {
            tries += 1;
            timer = setTimeout(poll, Math.min(500 + tries * 400, 3000));
          }
        });
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [network, refreshKey]);

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
      className={"netdock" + (open ? "" : " collapsed") + (floating ? " floating" : "") + (full ? " netdock-full" : "")}
      style={full ? {} : style}
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
          {paperUrl && (
            <button className={tab === "paper" ? "on" : ""} onClick={() => setTab("paper")}>Paper</button>
          )}
          <button className={tab === "agents" ? "on" : ""} onClick={() => setTab("agents")}>Agents</button>
          <button className={tab === "logs" ? "on" : ""} onClick={() => setTab("logs")}>
            Logs {logs.length > 0 && <span className="tabcount">{logs.length}</span>}
          </button>
          {!paperUrl && focus && (
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
        {expanded === undefined && (
          <button
            className="iconbtn sm netfull"
            onClick={() => setFull((v) => !v)}
            title={full ? "Exit full screen" : "Full screen — edit agent models"}
          >
            {full ? <Minimize /> : <Maximize />}
          </button>
        )}
        {expanded === undefined ? (
          <button
            className={"iconbtn sm netcollapse" + (open ? "" : " up")}
            onClick={onToggle}
            title={open ? "Collapse graph" : "Expand graph"}
          >
            <ChevronDown />
          </button>
        ) : (
          <button
            className="iconbtn sm netcollapse"
            onClick={onToggle}
            title={expanded ? "Restore paper details" : "Maximize this panel"}
          >
            {expanded ? <Minimize /> : <Maximize />}
          </button>
        )}
      </div>

      {open && tab === "paper" && paperUrl ? (
        <div className="netpaper">
          <iframe src={paperUrl} title="paper" />
          <a className="netpaper-open" href={paperUrl} target="_blank" rel="noreferrer">Open PDF ↗</a>
        </div>
      ) : open && tab === "code" ? (
        <div className="netcode">
          <CodeView conversationId={conversationId ?? null} theme={theme ?? "dark"} />
        </div>
      ) : open &&
        (tab === "agents" ? (
          <div className="netgraph">
            {nodes.length === 0 ? (
              <div className="muted-empty" style={{ padding: 24 }}>No graph available.</div>
            ) : (
              <NetworkGraph
                nodes={nodes}
                edges={edges}
                activeIds={activeNodes}
                activeEdgeIds={activeEdges}
                onNodePick={
                  onEditAgent
                    ? (id) => {
                        const d = detail.find((n) => n.name === id);
                        // Only LLM agents have a model to change (not coded/toolbox tools).
                        if (!d || !(d.display_as === "front_man" || d.display_as === "llm_agent")) return;
                        onEditAgent(id, {
                          description: d.description ?? undefined,
                          model: d.model,
                          modelInherited: d.modelInherited,
                          provider: d.provider,
                          temperature: d.temperature,
                        });
                      }
                    : undefined
                }
              />
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
