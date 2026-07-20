import { useRef, useState } from "react";
import { useChat } from "../useChat";
import { listConversations, deleteConversation, type Conversation } from "../api";
import Thread from "../components/Thread";
import NetworkView from "../components/NetworkView";
import TaskPanel from "../components/TaskPanel";
import "../alive.css"; // Tailwind + node/graph design tokens (needed for the graph nodes)
import "../styles.css";
import "./ext.css";

/**
 * Dedicated, lightweight Neura UI for the VS Code extension webview.
 * Just the chat panel, with the agent graph and the task checklist as
 * toggleable side sections (both OFF by default). Reuses the same chat
 * engine + components as the main app; this shell is extension-only.
 */
export default function ExtApp() {
  const chat = useChat({ network: "neura", mode: "assist" });
  const [showGraph, setShowGraph] = useState(false);
  const [showChecklist, setShowChecklist] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [convos, setConvos] = useState<Conversation[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function refreshHistory() {
    try {
      setConvos(await listConversations("neura"));
    } catch {
      setConvos([]);
    }
  }
  function openHistory() {
    setShowHistory(true);
    void refreshHistory();
  }
  async function pickConversation(id: string) {
    await chat.load(id);
    setShowHistory(false);
  }
  function newChat() {
    chat.reset();
    setShowHistory(false);
  }
  async function removeConversation(id: string) {
    await deleteConversation(id);
    if (id === chat.conversationId) chat.reset();
    void refreshHistory();
  }

  const hasPlan = chat.checklist.length > 0;

  function submit() {
    const el = inputRef.current;
    if (!el) return;
    const v = el.value.trim();
    if (!v || chat.busy) return;
    void chat.send(v);
    el.value = "";
    el.style.height = "auto";
  }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }
  function grow() {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 140) + "px";
  }

  return (
    <div className="ext-root">
      <div className="ext-head">
        <div className="ext-head-left">
          <button className="ext-icon" onClick={openHistory} title="Chat history">☰</button>
          <span className="ext-title">
            <span className="ext-orb" /> Neura
          </span>
        </div>
        <div className="ext-actions">
          <button
            className={"ext-toggle" + (showGraph ? " on" : "")}
            onClick={() => setShowGraph((v) => !v)}
            title="Show the agent network graph"
          >
            Graph
          </button>
          <button
            className={"ext-toggle" + (showChecklist ? " on" : "")}
            onClick={() => setShowChecklist((v) => !v)}
            title="Show the task checklist"
          >
            Checklist{hasPlan ? ` · ${chat.checklist.length}` : ""}
          </button>
          <button className="ext-toggle" onClick={newChat} title="New chat">
            New
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="ext-drawer-scrim" onClick={() => setShowHistory(false)}>
          <div className="ext-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="ext-drawer-head">
              <span>Chats</span>
              <button className="ext-icon" onClick={() => setShowHistory(false)} title="Close">✕</button>
            </div>
            <button className="ext-newchat" onClick={newChat}>＋ New chat</button>
            <div className="ext-convos">
              {convos.length === 0 ? (
                <div className="ext-empty">No chats yet.</div>
              ) : (
                convos.map((c) => (
                  <div key={c.id} className={"ext-conv" + (c.id === chat.conversationId ? " on" : "")}>
                    <button className="ext-conv-main" onClick={() => pickConversation(c.id)} title={c.title}>
                      <span className="ext-conv-title">{c.title || "Untitled"}</span>
                      <span className="ext-conv-meta">{c.count} msg</span>
                    </button>
                    <button className="ext-conv-del" onClick={() => removeConversation(c.id)} title="Delete chat">
                      ✕
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {showGraph && (
        <div className="ext-panel ext-graph">
          <NetworkView
            open
            floating={false}
            network="neura"
            activeNodes={chat.activeNodes}
            activeEdges={chat.activeEdges}
            logs={chat.logs}
            busy={chat.busy}
            conversationId={chat.conversationId}
            theme="dark"
            onToggle={() => setShowGraph(false)}
          />
        </div>
      )}

      {showChecklist && (
        <div className="ext-panel ext-checklist">
          {hasPlan ? (
            <TaskPanel items={chat.checklist} progress={chat.progress} />
          ) : (
            <div className="ext-empty">No task plan yet — it appears when Neura runs a multi-step job.</div>
          )}
        </div>
      )}

      <div className="ext-thread">
        <Thread
          messages={chat.messages}
          activity={chat.activity}
          liveTrace={chat.liveTrace}
          liveCommands={chat.liveCommands}
          busy={chat.busy}
          animatingId={chat.animatingId}
          userInitials="Me"
          imagePending={chat.imagePending}
          onQuick={(q) => chat.send(q)}
          onBuild={() => {}}
          onApprove={(d) =>
            chat.send(d === "always" ? "yes — and proceed without asking again" : d)
          }
        />
      </div>

      <div className="ext-composer">
        <textarea
          ref={inputRef}
          rows={1}
          placeholder="Message Neura…"
          onKeyDown={onKey}
          onInput={grow}
          disabled={false}
        />
        {chat.busy ? (
          <button className="ext-send stop" onClick={() => chat.stop()} title="Stop">■</button>
        ) : (
          <button className="ext-send" onClick={submit} title="Send">↑</button>
        )}
      </div>
    </div>
  );
}
