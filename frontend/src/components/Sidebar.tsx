import { useEffect, useState } from "react";
import { Plus, Doc, Shield, Sun, Trash, Wand, Bot, Home, ChevronRight } from "../icons";
import type { Conversation, NetworkInfo } from "../api";

interface Props {
  open: boolean;
  networks: NetworkInfo[];
  currentNetwork: string;
  conversations: Conversation[];
  currentId: string | null;
  kbChunks: number | null;
  onSelectNetwork(name: string): void;
  onBuildAgent(): void;
  onOpenKnowledge(): void;
  onClearKnowledge(): void;
  onDeleteNetwork(name: string): void;
  onNewChat(): void;
  onSelect(id: string): void;
  onDelete(id: string): void;
  onToggleTheme(): void;
  profileName?: string;
  profileSub?: string;
  onOpenProfile(): void;
}

function netIcon(n: NetworkInfo) {
  if (n.name === "neura") return <Home />;
  if (n.name === "agent_network_designer") return <Wand />;
  return <Bot />;
}

function initials(name?: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "🙂";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function Sidebar(p: Props) {
  const neura = p.networks.find((n) => n.name === "neura");
  const others = p.networks.filter((n) => n.name !== "neura");
  const [expanded, setExpanded] = useState(false);

  // Auto-expand the folder if the active network is one of the "others".
  useEffect(() => {
    if (p.currentNetwork !== "neura") setExpanded(true);
  }, [p.currentNetwork]);

  const NetRow = (n: NetworkInfo) => (
    <a
      key={n.name}
      className={n.name === p.currentNetwork ? "active" : ""}
      onClick={() => p.onSelectNetwork(n.name)}
      title={n.description || n.title}
    >
      <span className="net-ic">{netIcon(n)}</span>
      <span className="conv-title">{n.title}</span>
      {n.spawned && (
        <button
          className="conv-del"
          title="Delete this agent network"
          onClick={(e) => {
            e.stopPropagation();
            p.onDeleteNetwork(n.name);
          }}
        >
          <Trash />
        </button>
      )}
    </a>
  );

  return (
    <aside className={"side" + (p.open ? " open" : "")}>
      <div className="brand">
        <div className="orb" />
        <div>
          <h1>Neura</h1>
          <span>Your Personal AI</span>
        </div>
      </div>

      <button className="newchat" onClick={p.onNewChat}>
        <Plus />
        New conversation
      </button>

      {/* Neura is the default assistant */}
      <nav className="conv nets">{neura && NetRow(neura)}</nav>

      {/* Everything else lives in a collapsible folder */}
      <button className={"folder-toggle" + (expanded ? " open" : "")} onClick={() => setExpanded((v) => !v)}>
        <ChevronRight className="chev" />
        <span>Agent networks</span>
        <span className="count">{others.length}</span>
        <span
          className="folder-add"
          title="Build a new agent network"
          onClick={(e) => {
            e.stopPropagation();
            p.onBuildAgent();
          }}
        >
          <Wand />
        </span>
      </button>
      {expanded && (
        <nav className="conv nets sub">
          {others.length === 0 && (
            <span className="muted-empty" style={{ padding: "4px 10px" }}>No agents yet — build one</span>
          )}
          {others.map((n) => NetRow(n))}
        </nav>
      )}

      <div className="sect">Recent</div>
      <nav className="conv scroll">
        {p.conversations.length === 0 && (
          <span className="muted-empty" style={{ padding: "4px 10px" }}>No conversations yet</span>
        )}
        {p.conversations.map((c) => (
          <a
            key={c.id}
            className={c.id === p.currentId ? "active" : ""}
            onClick={() => p.onSelect(c.id)}
            title={c.title}
          >
            <span className="dot" />
            <span className="conv-title">{c.title}</span>
            <button
              className="conv-del"
              title="Delete conversation"
              onClick={(e) => {
                e.stopPropagation();
                p.onDelete(c.id);
              }}
            >
              <Trash />
            </button>
          </a>
        ))}
      </nav>

      <div className="sect sect-row">
        <span>Knowledge</span>
        <button className="sect-add" title="Add folders or documents" onClick={p.onOpenKnowledge}>
          <Plus />
        </button>
      </div>
      <div className="kb">
        <div className="row clickable" onClick={p.onOpenKnowledge} title="Add folders or documents">
          <div className="ic"><Doc /></div>
          <div>
            <div className="t">Documents</div>
            <div className="c">Click to add more</div>
          </div>
          <div className="meta">
            <div className="t">{p.kbChunks == null ? "—" : p.kbChunks.toLocaleString()}</div>
            <div className="c">chunks</div>
          </div>
          {!!p.kbChunks && (
            <button
              className="kb-clear"
              title="Clear all global knowledge"
              onClick={(e) => {
                e.stopPropagation();
                p.onClearKnowledge();
              }}
            >
              <Trash />
            </button>
          )}
        </div>
        <div className="row">
          <div className="ic"><Shield /></div>
          <div>
            <div className="t">Privacy</div>
            <div className="c">On-device embeddings</div>
          </div>
          <div className="meta">
            <div className="t" style={{ color: "var(--accent-2)" }}>●</div>
            <div className="c">local</div>
          </div>
        </div>
      </div>

      <div className="spacer" />
      <div className="profile">
        <button className="profile-open" onClick={p.onOpenProfile} title="Edit your profile">
          <div className="avatar">{initials(p.profileName)}</div>
          <div className="profile-txt">
            <div className="t">{p.profileName || "Set up your profile"}</div>
            <div className="s">{p.profileSub || "Tell Neura about you"}</div>
          </div>
        </button>
        <button className="gear" title="Toggle theme" onClick={p.onToggleTheme}>
          <Sun />
        </button>
      </div>
    </aside>
  );
}
