import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getRadar,
  refreshRadar,
  setRadarItemStatus,
  streamChat,
  type RadarDoc,
  type RadarItem,
} from "../api";
import { Close } from "../icons";
import NetworkView from "./NetworkView";

interface Props {
  open: boolean;
  theme: "light" | "dark";
  initialPaperId?: string | null;
  onClose(): void;
}

type ChatMsg = { role: "user" | "ai"; text: string };

// A per-paper hue derived from the id, used *subtly* — a faint tinted header and a
// small accent dot — so cards feel distinct without throwing saturated color.
function hue(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}
// Muted, dark, low-saturation header — a tasteful tinted charcoal band, not neon.
function banner(id: string): string {
  const h = hue(id);
  return `linear-gradient(135deg, hsl(${h} 22% 17%), hsl(${(h + 40) % 360} 18% 12%))`;
}
function dot(id: string): string {
  return `hsl(${hue(id)} 45% 55%)`;
}

export default function ResearchRadarModal({ open, theme, initialPaperId, onClose }: Props) {
  const [doc, setDoc] = useState<RadarDoc | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sel, setSel] = useState<RadarItem | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getRadar()
      .then((d) => {
        setDoc(d);
        if (initialPaperId) {
          const hit = (d.items || []).find((i) => i.id === initialPaperId);
          if (hit) setSel(hit);
        }
      })
      .catch(() => setDoc(null))
      .finally(() => setLoading(false));
  }, [open, initialPaperId]);

  async function doRefresh() {
    setRefreshing(true);
    try {
      setDoc(await refreshRadar());
    } finally {
      setRefreshing(false);
    }
  }

  if (!open) return null;
  const items = (doc?.items || []).filter((i) => i.status !== "dismissed");

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal radar-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">
            {sel ? (
              <button className="radar-back" onClick={() => setSel(null)}>← Radar</button>
            ) : (
              "Research Radar"
            )}
          </div>
          {!sel && (
            <div className="radar-head-actions">
              <span className="radar-updated">
                {doc?.generated ? `Updated ${new Date(doc.generated).toLocaleString()}` : ""}
              </span>
              <button className="btn-ghost" onClick={doRefresh} disabled={refreshing}>
                {refreshing ? <><span className="spin" /> Refreshing…</> : "Refresh"}
              </button>
            </div>
          )}
          <button className="modal-x" onClick={onClose}><Close /></button>
        </div>

        {sel ? (
          <RadarDetail item={sel} theme={theme} />
        ) : loading && !doc ? (
          <div className="muted-empty" style={{ padding: 40 }}>Scanning arXiv…</div>
        ) : items.length === 0 ? (
          <div className="muted-empty" style={{ padding: 40 }}>
            No papers yet. Hit Refresh to scan your areas.
          </div>
        ) : (
          <div className="radar-grid">
            {items.map((p) => (
              <button className="radar-card" key={p.id} onClick={() => setSel(p)}>
                <div className="radar-card-top">
                  <span className="radar-chip">
                    <span className="radar-dot" style={{ background: dot(p.id) }} />
                    {p.area}
                  </span>
                  <span className={"radar-tag " + (p.action === "try" ? "try" : "read")}>
                    {p.action === "try" ? "Try" : "Read"}
                  </span>
                </div>
                <div className="radar-card-title">{p.title}</div>
                <div className="radar-card-summary">{p.summary || p.abstract.slice(0, 160)}</div>
                <div className="radar-card-foot">
                  {p.skill && <span className="radar-skill">{p.skill}</span>}
                  <span className="radar-date">{p.published}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RadarDetail({ item, theme }: { item: RadarItem; theme: "light" | "dark" }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeNodes, setActiveNodes] = useState<Set<string>>(new Set());
  const [activeEdges, setActiveEdges] = useState<Set<string>>(new Set());
  const [logs, setLogs] = useState<{ kind: string; text: string }[]>([]);
  const convId = useRef<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Reset the chat thread + graph when the paper changes.
  useEffect(() => {
    setMsgs([]);
    setLogs([]);
    setActiveNodes(new Set());
    setActiveEdges(new Set());
    convId.current = null;
    setRadarItemStatus(item.id, "read").catch(() => {});
  }, [item.id]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [msgs, busy]);

  async function ask() {
    const question = q.trim();
    if (!question || busy) return;
    setQ("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    const ctx =
      `(Paper context — title: "${item.title}"; arXiv: ${item.url}; ` +
      `abstract: ${item.abstract.slice(0, 1200)})\n\n${question}`;
    let answer = "";
    try {
      await streamChat(
        ctx,
        { network: "research_radar", conversationId: convId.current, mode: "assist" },
        {
          onConversation: (info) => (convId.current = info.id),
          onTrace: (node, path) => {
            setActiveNodes((s) => new Set(s).add(node));
            setTimeout(() => setActiveNodes((s) => { const n = new Set(s); n.delete(node); return n; }), 1900);
            const eids: string[] = [];
            for (let i = 0; i + 1 < (path?.length ?? 0); i++) eids.push(`${path[i]}->${path[i + 1]}`);
            if (eids.length) {
              setActiveEdges((s) => { const n = new Set(s); eids.forEach((e) => n.add(e)); return n; });
              setTimeout(() => setActiveEdges((s) => { const n = new Set(s); eids.forEach((e) => n.delete(e)); return n; }), 1900);
            }
          },
          onLog: (entry) => setLogs((l) => [...l, entry].slice(-300)),
          onCommand: (c) => setLogs((l) => [...l, { kind: "command", text: `$ ${c.command} (exit ${c.exit})` }].slice(-300)),
          onAnswer: (t) => (answer = t),
          onError: (msg) => (answer = answer || `⚠️ ${msg}`),
          onDone: () => {},
        }
      );
    } catch {
      answer = answer || "⚠️ Could not reach the Research Radar network.";
    }
    setMsgs((m) => [...m, { role: "ai", text: answer || "(no answer)" }]);
    setBusy(false);
  }

  return (
    <div className="radar-detail">
      {/* Left: paper header + live agent network (like Neura) */}
      <div className="radar-detail-main">
        <div className="radar-detail-head" style={{ background: banner(item.id) }}>
          <div className="radar-detail-top">
            <span className="radar-chip">
              <span className="radar-dot" style={{ background: dot(item.id) }} />
              {item.area}
            </span>
            <span className={"radar-tag " + (item.action === "try" ? "try" : "read")}>
              {item.action === "try" ? "Try" : "Read"}
            </span>
          </div>
          <h2>{item.title}</h2>
          <div className="radar-detail-meta">
            {item.authors.join(", ")}
            {item.authors.length >= 5 ? " et al." : ""} · {item.published} ·{" "}
            <a href={item.url} target="_blank" rel="noreferrer">arXiv ↗</a>
          </div>
          {item.skill && <div className="radar-detail-skill">Strengthens: {item.skill}</div>}
          <p className="radar-detail-summary">{item.summary}</p>
          <details className="radar-abstract">
            <summary>Full abstract</summary>
            <p>{item.abstract}</p>
          </details>
        </div>

        <div className="radar-detail-graph">
          <NetworkView
            open
            floating={false}
            focus
            conversationId={convId.current}
            theme={theme}
            network="research_radar"
            activeNodes={activeNodes}
            activeEdges={activeEdges}
            logs={logs}
            busy={busy}
            onToggle={() => {}}
          />
        </div>
      </div>

      {/* Right: chat about this paper (input pinned at the bottom) */}
      <div className="radar-detail-chat">
        <div className="radar-chat">
          <div className="radar-chat-title">Ask about this paper</div>
          <div className="radar-chat-body" ref={bodyRef}>
            {msgs.length === 0 && (
              <div className="muted-empty">
                e.g. "Explain the method simply", "How does this relate to neuro-san?", "Is it worth trying?"
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "ai" ? (
                <div key={i} className="radar-msg ai md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                </div>
              ) : (
                <div key={i} className="radar-msg user">{m.text}</div>
              )
            )}
            {busy && <div className="radar-msg ai"><span className="spin" /> thinking…</div>}
          </div>
          <div className="radar-chat-input">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="Ask a question about this paper…"
              disabled={busy}
            />
            <button className="btn-primary" onClick={ask} disabled={busy || !q.trim()}>Ask</button>
          </div>
        </div>
      </div>
    </div>
  );
}
