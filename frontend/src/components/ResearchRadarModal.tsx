import { useEffect, useRef, useState } from "react";
import {
  getRadar,
  refreshRadar,
  setRadarItemStatus,
  streamChat,
  type RadarDoc,
  type RadarItem,
} from "../api";
import { Close } from "../icons";

interface Props {
  open: boolean;
  onClose(): void;
}

type ChatMsg = { role: "user" | "ai"; text: string };

// A stable, pretty gradient "banner" per paper (arXiv has no thumbnails) — derived
// from the id so each paper looks distinct without any external image dependency.
function banner(id: string): string {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  const h2 = (h + 40) % 360;
  return `linear-gradient(135deg, hsl(${h} 70% 45%), hsl(${h2} 70% 38%))`;
}

export default function ResearchRadarModal({ open, onClose }: Props) {
  const [doc, setDoc] = useState<RadarDoc | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sel, setSel] = useState<RadarItem | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getRadar()
      .then((d) => setDoc(d))
      .catch(() => setDoc(null))
      .finally(() => setLoading(false));
  }, [open]);

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
          <RadarDetail item={sel} />
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
                <div className="radar-card-banner" style={{ background: banner(p.id) }}>
                  <span className="radar-card-area">{p.area}</span>
                  <span className={"radar-badge " + (p.action === "try" ? "try" : "read")}>
                    {p.action === "try" ? "🧪 Try" : "📖 Read"}
                  </span>
                </div>
                <div className="radar-card-body">
                  <div className="radar-card-title">{p.title}</div>
                  <div className="radar-card-summary">{p.summary || p.abstract.slice(0, 160)}</div>
                  <div className="radar-card-foot">
                    {p.skill && <span className="radar-skill">{p.skill}</span>}
                    <span className="radar-date">{p.published}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RadarDetail({ item }: { item: RadarItem }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const convId = useRef<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Reset the chat thread when the paper changes.
  useEffect(() => {
    setMsgs([]);
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
    // Ground the network on THIS paper.
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
          onAnswer: (t) => {
            answer = t;
          },
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
      <div className="radar-detail-banner" style={{ background: banner(item.id) }}>
        <span className={"radar-badge " + (item.action === "try" ? "try" : "read")}>
          {item.action === "try" ? "🧪 Try" : "📖 Read"}
        </span>
        <span className="radar-detail-area">{item.area}</span>
      </div>
      <div className="radar-detail-head">
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

      <div className="radar-chat">
        <div className="radar-chat-title">Ask about this paper</div>
        <div className="radar-chat-body" ref={bodyRef}>
          {msgs.length === 0 && (
            <div className="muted-empty">
              e.g. "Explain the method simply", "How does this relate to neuro-san?", "Is it worth trying?"
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={"radar-msg " + m.role}>{m.text}</div>
          ))}
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
  );
}
