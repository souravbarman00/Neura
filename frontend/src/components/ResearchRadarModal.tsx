import { useEffect, useState } from "react";
import {
  getRadar,
  getRadarPaper,
  listConversations,
  refreshRadar,
  setRadarAreas,
  setRadarItemStatus,
  type Conversation,
  type RadarArea,
  type RadarDoc,
  type RadarItem,
} from "../api";
import { Close } from "../icons";
import NetworkView from "./NetworkView";
import RadarCard from "./RadarCard";
import Thread from "./Thread";
import { useChat } from "../useChat";
import { dot, banner } from "./radarColors";

interface Props {
  open: boolean;
  theme: "light" | "dark";
  initialPaperId?: string | null;
  onClose(): void;
}

export default function ResearchRadarModal({ open, theme, initialPaperId, onClose }: Props) {
  const [doc, setDoc] = useState<RadarDoc | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sel, setSel] = useState<RadarItem | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

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
      <div className={"modal radar-modal" + (fullscreen ? " fullscreen" : "")} onClick={(e) => e.stopPropagation()}>
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
          <button
            className="radar-fs-btn"
            onClick={() => setFullscreen((v) => !v)}
            title={fullscreen ? "Exit full screen" : "Full screen"}
          >
            {fullscreen ? "⤡" : "⤢"}
          </button>
          <button className="modal-x" onClick={onClose}><Close /></button>
        </div>

        {sel ? (
          <RadarDetail item={sel} theme={theme} />
        ) : (
          <div className="radar-body">
            <RadarSetup doc={doc} onDoc={setDoc} onOpenPaper={setSel} />
            {loading && !doc ? (
              <div className="muted-empty" style={{ padding: 40 }}>Scanning arXiv…</div>
            ) : items.length === 0 ? (
              <div className="muted-empty" style={{ padding: 40 }}>
                No papers yet. Add an area above (or hit Refresh) to scan.
              </div>
            ) : (
              <div className="radar-grid">
                {items.map((p) => (
                  <RadarCard key={p.id} item={p} onOpen={() => setSel(p)} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Quick-add suggestions (arXiv queries tuned per area). Users can also type any area.
const SUGGESTED: RadarArea[] = [
  { label: "Multi-agent LLM systems", query: 'all:"multi-agent" AND all:"language model"' },
  { label: "Agent orchestration", query: 'all:"agent orchestration" OR all:"agentic"' },
  { label: "LLM reasoning & tool use", query: 'all:"tool use" AND all:"large language model"' },
  { label: "Retrieval-augmented generation", query: 'all:"retrieval-augmented generation"' },
  { label: "LLM evaluation", query: 'all:"evaluation" AND all:"large language model"' },
  { label: "Diffusion models", query: 'all:"diffusion model"' },
  { label: "Reinforcement learning", query: 'all:"reinforcement learning"' },
  { label: "Speech & audio", query: 'all:"speech recognition" OR all:"text to speech"' },
];

/** Two ways to drive the radar: manage your areas of interest (with quick-add chips),
 *  or paste a specific paper link to jump straight into it. */
function RadarSetup({
  doc,
  onDoc,
  onOpenPaper,
}: {
  doc: RadarDoc | null;
  onDoc(d: RadarDoc): void;
  onOpenPaper(item: RadarItem): void;
}) {
  const areas = doc?.areas || [];
  const [newArea, setNewArea] = useState("");
  const [savingAreas, setSavingAreas] = useState(false);
  const [link, setLink] = useState("");
  const [opening, setOpening] = useState(false);
  const [err, setErr] = useState("");

  const has = (label: string) => areas.some((a) => a.label.toLowerCase() === label.toLowerCase());

  async function saveAreas(next: RadarArea[]) {
    setSavingAreas(true);
    try {
      onDoc(await setRadarAreas(next));
    } finally {
      setSavingAreas(false);
    }
  }
  const add = (a: RadarArea) => {
    if (!has(a.label)) void saveAreas([...areas, a]);
  };
  const addCustom = () => {
    const t = newArea.trim();
    if (!t) return;
    setNewArea("");
    add({ label: t, query: t });
  };
  const remove = (label: string) => void saveAreas(areas.filter((a) => a.label !== label));

  async function openPaper() {
    const v = link.trim();
    if (!v || opening) return;
    setErr("");
    setOpening(true);
    try {
      const r = await getRadarPaper(v);
      if (r.item) {
        setLink("");
        onOpenPaper(r.item);
      } else {
        setErr(r.error || "No paper found for that link/id.");
      }
    } catch {
      setErr("Could not fetch that paper.");
    } finally {
      setOpening(false);
    }
  }

  const suggestions = SUGGESTED.filter((s) => !has(s.label));

  return (
    <div className="radar-setup">
      <div className="radar-setup-row">
        <span className="radar-setup-label">Your areas</span>
        <div className="radar-chips">
          {areas.map((a) => (
            <span className="radar-area-chip" key={a.label}>
              {a.label}
              <button onClick={() => remove(a.label)} disabled={savingAreas} title="Remove area">×</button>
            </span>
          ))}
          <input
            className="radar-area-input"
            placeholder="add an area…"
            value={newArea}
            onChange={(e) => setNewArea(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
            disabled={savingAreas}
          />
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="radar-setup-row">
          <span className="radar-setup-label">Suggestions</span>
          <div className="radar-chips">
            {suggestions.map((s) => (
              <button className="radar-suggest-chip" key={s.label} onClick={() => add(s)} disabled={savingAreas}>
                + {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="radar-setup-row">
        <span className="radar-setup-label">Open a paper</span>
        <div className="radar-paper-open">
          <input
            className="radar-area-input wide"
            placeholder="paste an arXiv link or id — e.g. 2401.01234"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && openPaper()}
            disabled={opening}
          />
          <button className="btn-primary" onClick={openPaper} disabled={opening || !link.trim()}>
            {opening ? "Opening…" : "Open"}
          </button>
        </div>
      </div>

      {savingAreas && (
        <div className="radar-setup-note"><span className="spin" /> Updating your radar…</div>
      )}
      {err && <div className="modal-error">⚠️ {err}</div>}
    </div>
  );
}

function RadarDetail({ item, theme }: { item: RadarItem; theme: "light" | "dark" }) {
  // Reuse the SAME chat stack Neura uses (thinking animation, live-trace box, typewriter).
  const chat = useChat({ network: "research_radar", mode: "assist", busyLabel: "Reading the paper…" });
  const [q, setQ] = useState("");
  const [expanded, setExpanded] = useState(false); // paper/dock fills the full left side
  const [sessions, setSessions] = useState<Conversation[]>([]); // past chats for THIS paper
  const [sessionsOpen, setSessionsOpen] = useState(false);

  // Sessions are research_radar conversations titled "<arxivId> · <title>" — that ties
  // each saved chat to its paper without any schema change.
  const sessionTitle = `${item.id} · ${item.title}`;
  const prefix = `${item.id} · `;
  async function refreshSessions() {
    const all = await listConversations("research_radar").catch(() => [] as Conversation[]);
    setSessions(all.filter((c) => c.title.startsWith(prefix)));
  }

  // On paper change: reset, load this paper's saved sessions, and resume the most recent.
  useEffect(() => {
    setExpanded(false);
    setSessionsOpen(false);
    chat.reset();
    setRadarItemStatus(item.id, "read").catch(() => {});
    let cancelled = false;
    (async () => {
      const all = await listConversations("research_radar").catch(() => [] as Conversation[]);
      if (cancelled) return;
      const mine = all.filter((c) => c.title.startsWith(prefix));
      setSessions(mine);
      if (mine.length) void chat.load(mine[0].id); // resume the newest (list is updated-desc)
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id]);

  // The user's bubble shows the clean question; the agent also gets the paper context.
  const withCtx = (question: string) =>
    `(Paper context — title: "${item.title}"; arXiv: ${item.url}; ` +
    `abstract: ${item.abstract.slice(0, 1200)})\n\n${question}`;

  function ask(text?: string) {
    const question = (text ?? q).trim();
    if (!question || chat.busy) return;
    setQ("");
    void chat.send(question, { transmit: withCtx(question), title: sessionTitle }).then(refreshSessions);
  }

  const fmtDate = (t: number) =>
    new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="radar-detail">
      {/* Left: paper header + live agent network (like Neura) */}
      <div className={"radar-detail-main" + (expanded ? " expanded" : "")}>
        <div className="radar-detail-head" style={{ background: banner(item.id, theme) }}>
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
          {item.skill && item.skill.toLowerCase() !== item.area.toLowerCase() && (
            <div className="radar-detail-skill">Strengthens: {item.skill}</div>
          )}
          <p className="radar-detail-summary">{item.summary}</p>
          <details className="radar-abstract">
            <summary>Full abstract</summary>
            <p>{item.abstract}</p>
          </details>
        </div>

        <div className="radar-detail-graph">
          <NetworkView
            key={item.id}
            open
            floating={false}
            focus
            conversationId={chat.conversationId}
            theme={theme}
            network="research_radar"
            activeNodes={chat.activeNodes}
            activeEdges={chat.activeEdges}
            logs={chat.logs}
            busy={chat.busy}
            onToggle={() => setExpanded((v) => !v)}
            expanded={expanded}
            paperUrl={`https://arxiv.org/pdf/${item.id}`}
          />
        </div>
      </div>

      {/* Right: the reused Neura chat panel (thinking animation + live-trace + typewriter) */}
      <div className="radar-detail-chat">
        <div className="radar-chat">
          <div className="radar-chat-title">
            <span>Ask about this paper</span>
            <div className="radar-sessions">
              <button
                className="radar-sessions-btn"
                onClick={() => setSessionsOpen((v) => !v)}
                title="Chat sessions for this paper"
              >
                ☰
              </button>
              {sessionsOpen && (
                <>
                  <div className="radar-sessions-scrim" onClick={() => setSessionsOpen(false)} />
                  <div className="radar-sessions-menu">
                    <div className="radar-sessions-hd">This paper's chats</div>
                    {sessions.length === 0 && <div className="radar-sessions-empty">No saved chats yet</div>}
                    {sessions.map((s) => (
                      <button
                        key={s.id}
                        className={"radar-session" + (s.id === chat.conversationId ? " on" : "")}
                        onClick={() => {
                          void chat.load(s.id);
                          setSessionsOpen(false);
                        }}
                      >
                        <span>{fmtDate(s.updated)}</span>
                        <span className="radar-session-count">{s.count} msg{s.count === 1 ? "" : "s"}</span>
                      </button>
                    ))}
                    <div className="radar-sessions-sep" />
                    <button
                      className="radar-session new"
                      onClick={() => {
                        chat.reset();
                        setSessionsOpen(false);
                      }}
                    >
                      + New chat
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="radar-chat-thread">
            {chat.messages.length === 0 && !chat.busy ? (
              <div className="muted-empty">
                e.g. "Explain the method simply", "What builds on this?", "Is there code?",
                "Explain the math with an example"
              </div>
            ) : (
              <Thread
                messages={chat.messages}
                activity={chat.activity}
                liveTrace={chat.liveTrace}
                liveCommands={chat.liveCommands}
                liveEvents={chat.liveEvents}
                busy={chat.busy}
                animatingId={chat.animatingId}
                onQuick={(t) => ask(t)}
                onBuild={() => {}}
              />
            )}
          </div>
          <div className="radar-chat-input">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="Ask a question about this paper…"
              disabled={chat.busy}
            />
            {chat.busy ? (
              <button className="btn-primary radar-stop" onClick={() => chat.stop()} title="Stop">■ Stop</button>
            ) : (
              <button className="btn-primary" onClick={() => ask()} disabled={!q.trim()}>Ask</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
