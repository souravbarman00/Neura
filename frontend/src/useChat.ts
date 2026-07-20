import { useRef, useState } from "react";
import { getConversation, streamChat, type ChecklistItem } from "./api";
import type { AgentMsg, CommandRun, Message } from "./types";

// Radar user turns are transmitted with a hidden paper-context preamble; strip it so
// the reloaded user bubbles show just the question.
const stripCtx = (t: string): string => t.replace(/^\(Paper context —[\s\S]*?\)\s*\n\n/, "");

// Shared chat-stream state, extracted so both the main Neura panel and the Research
// Radar can drive the SAME <Thread> UI (thinking animation, live-trace box, typewriter).
// It maps the SSE callbacks onto the exact state shape <Thread> consumes.

let _seq = 0;
const nextId = (): string => `m${Date.now().toString(36)}${(_seq++).toString(36)}`;

export interface UseChat {
  messages: Message[];
  activity: string | null;
  liveTrace: AgentMsg[];
  checklist: ChecklistItem[];
  progress: number | null;
  imagePending: boolean;
  liveCommands: CommandRun[];
  busy: boolean;
  animatingId: string | null;
  activeNodes: Set<string>;
  activeEdges: Set<string>;
  logs: { kind: string; text: string }[];
  conversationId: string | null;
  /** `text` is what shows in the user bubble; `opts.transmit` (if given) is what's
   *  actually sent to the agent — used to inject hidden context (e.g. paper details).
   *  `opts.title` names the saved conversation (e.g. the paper for a Radar session). */
  send(text: string, opts?: { transmit?: string; title?: string }): Promise<string>;
  /** Abort the in-flight turn (stop the agents). */
  stop(): void;
  reset(): void;
  /** Reload a previously-saved conversation's messages into this chat. */
  load(id: string): Promise<void>;
}

export function useChat(cfg: { network: string; mode?: "strict" | "assist"; busyLabel?: string }): UseChat {
  const [messages, setMessages] = useState<Message[]>([]);
  const [activity, setActivity] = useState<string | null>(null);
  const [liveTrace, setLiveTrace] = useState<AgentMsg[]>([]);
  const [checklist, setChecklist] = useState<ChecklistItem[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [imagePending, setImagePending] = useState(false);
  const [liveCommands, setLiveCommands] = useState<CommandRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [animatingId, setAnimatingId] = useState<string | null>(null);
  const [activeNodes, setActiveNodes] = useState<Set<string>>(new Set());
  const [activeEdges, setActiveEdges] = useState<Set<string>>(new Set());
  const [logs, setLogs] = useState<{ kind: string; text: string }[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const convId = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null); // aborts the in-flight stream

  function reset(): void {
    setMessages([]);
    setActivity(null);
    setLiveTrace([]);
    setLiveCommands([]);
    setChecklist([]);
    setProgress(null);
    setImagePending(false);
    setBusy(false);
    setAnimatingId(null);
    setActiveNodes(new Set());
    setActiveEdges(new Set());
    setLogs([]);
    setConversationId(null);
    convId.current = null;
  }

  async function load(id: string): Promise<void> {
    const conv = await getConversation(id);
    convId.current = id;
    setConversationId(id);
    setAnimatingId(null);
    setActivity(null);
    setLiveTrace([]);
    setLiveCommands([]);
    setMessages(
      (conv.messages || []).map((m) => ({
        id: m.id,
        role: m.role,
        text: m.role === "user" ? stripCtx(m.text) : m.text,
        sources: m.sources || undefined,
        trace: m.trace || undefined,
        commands: m.commands || undefined,
      }))
    );
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function send(text: string, opts?: { transmit?: string; title?: string }): Promise<string> {
    if (busy) return "";
    let finalAnswer = "";
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setLiveTrace([]);
    setLiveCommands([]);
    setActiveNodes(new Set());
    setActiveEdges(new Set());
    setMessages((m) => [...m, { id: nextId(), role: "user", text }]);
    setActivity(cfg.busyLabel || "Working…");

    const aiId = nextId();
    setAnimatingId(aiId);
    let created = false;
    const trace: AgentMsg[] = [];
    const cmds: CommandRun[] = [];

    try {
      await streamChat(
        opts?.transmit ?? text,
        { conversationId: convId.current, mode: cfg.mode || "assist", network: cfg.network, title: opts?.title },
        {
          onConversation: (info) => {
            convId.current = info.id;
            setConversationId(info.id);
          },
          onActivity: () => setActivity("Thinking…"),
          onTrace: (node, path) => {
            setActiveNodes((s) => new Set(s).add(node));
            setTimeout(() => setActiveNodes((s) => {
              const n = new Set(s);
              n.delete(node);
              return n;
            }), 1900);
            const eids: string[] = [];
            for (let i = 0; i + 1 < (path?.length ?? 0); i++) eids.push(`${path[i]}->${path[i + 1]}`);
            if (eids.length) {
              setActiveEdges((s) => {
                const n = new Set(s);
                eids.forEach((e) => n.add(e));
                return n;
              });
              setTimeout(() => setActiveEdges((s) => {
                const n = new Set(s);
                eids.forEach((e) => n.delete(e));
                return n;
              }), 1900);
            }
          },
          onLog: (entry) => setLogs((l) => [...l, entry].slice(-300)),
          onAgentMessage: (m) => {
            trace.push(m);
            setLiveTrace([...trace]);
            if (created) setMessages((ms) => ms.map((x) => (x.id === aiId ? { ...x, trace: [...trace] } : x)));
          },
          onCommand: (c) => {
            cmds.push(c);
            // Once the answer bubble exists, commands live inside it — clear the live
            // block so the same terminal cards don't show twice.
            if (created) {
              setLiveCommands([]);
              setMessages((ms) => ms.map((x) => (x.id === aiId ? { ...x, commands: [...cmds] } : x)));
            } else {
              setLiveCommands([...cmds]);
            }
          },
          onAnswer: (t) => {
            setActivity(null);
            setImagePending(false); // the answer carries the image now
            setLiveCommands([]); // commands now live inside the message bubble
            finalAnswer = t;
            setMessages((m) => {
              if (!created) {
                created = true;
                return [...m, { id: aiId, role: "ai", text: t, trace: [...trace], commands: [...cmds] }];
              }
              return m.map((x) => (x.id === aiId ? { ...x, text: t, trace: [...trace], commands: [...cmds] } : x));
            });
          },
          onChecklist: (items) => setChecklist(items || []),
          onProgress: (v) => setProgress(v),
          onImagePending: () => setImagePending(true),
          onError: (msg) => {
            setActivity(null);
            setMessages((m) => [...m, { id: nextId(), role: "ai", text: "⚠️ " + msg }]);
          },
        },
        ac.signal
      );
    } catch (e: any) {
      if (e?.name === "AbortError") {
        if (created) {
          setMessages((m) =>
            m.map((x) => (x.id === aiId ? { ...x, text: (x.text || "") + "\n\n_⏹ Stopped._" } : x))
          );
        } else {
          setMessages((m) => [...m, { id: aiId, role: "ai", text: "_⏹ Stopped._" }]);
        }
      } else {
        setMessages((m) => [...m, { id: nextId(), role: "ai", text: "⚠️ Could not reach the network." }]);
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
      setActivity(null);
      setImagePending(false);
    }
    return finalAnswer;
  }

  return {
    messages, activity, liveTrace, liveCommands, checklist, progress, imagePending, busy, animatingId,
    activeNodes, activeEdges, logs, conversationId, send, stop, reset, load,
  };
}
