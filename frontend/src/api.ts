import type { AgentMsg, Health, Source } from "./types";

// Base URL for the Neura backend. Empty (default) → same-origin relative "/api/…"
// (the web app + desktop shell). A host like the VS Code extension injects an
// absolute base (window.__NEURA_API_BASE__ = "http://127.0.0.1:8010") so the
// webview's fetches/SSE reach the backend across origins.
export const API_BASE: string =
  (typeof window !== "undefined" && (window as any).__NEURA_API_BASE__) || "";
/** Prefix a same-origin API/asset path with the configured base. */
export const apiUrl = (path: string): string =>
  path.startsWith("http") ? path : API_BASE + path;

export interface Conversation {
  id: string;
  title: string;
  updated: number;
  count: number;
}

export interface ChecklistItem {
  item: string;
  status: "pending" | "in_progress" | "done" | "skipped";
  notes?: string;
  agent?: string;
}

export interface ChatCallbacks {
  onConversation?(info: { id: string; title: string; new: boolean }): void;
  onActivity?(label: string): void;
  onTrace?(node: string, path: string[]): void;
  onLog?(entry: { kind: string; text: string }): void;
  onSources?(items: Source[]): void;
  onAnswer?(text: string): void;
  onSuggestBuild?(description: string): void;
  onAgentMessage?(m: { agent: string; text: string; kind?: string; path?: string[] }): void;
  onCommand?(c: { command: string; exit: number; output: string }): void;
  onFileChange?(fc: { path: string; diff: string; kind?: string }): void;
  onChecklist?(items: ChecklistItem[]): void;
  onProgress?(value: number): void;
  onImagePending?(): void;
  onSummary?(text: string): void;
  onDone?(): void;
  onError?(msg: string): void;
}

export interface GraphData {
  front: string;
  detail: {
    name: string;
    display_as: string;
    tools: string[];
    description?: string | null;
    params?: { name: string; type: string; required: boolean }[] | null;
    class?: string | null;
    toolbox?: string | null;
    model?: string | null;
    modelInherited?: boolean | null;
  }[];
  nodes: { id: string; type: string }[];
  edges: { source: string; target: string }[];
}

export async function getGraph(name: string): Promise<GraphData> {
  return (await fetch(`${API_BASE}/api/networks/${name}/graph`)).json();
}

export interface ChatOptions {
  conversationId?: string | null;
  mode?: "strict" | "assist";
  network?: string;
  slyData?: Record<string, unknown>;
  title?: string; // caller-supplied conversation title (e.g. the paper for a Radar session)
}

/** Stream a chat turn from the backend SSE endpoint, dispatching typed events. */
export async function streamChat(
  message: string,
  opts: ChatOptions,
  cb: ChatCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(API_BASE + "/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: opts.conversationId ?? null,
      mode: opts.mode ?? "strict",
      network: opts.network ?? "neura",
      sly_data: opts.slyData ?? {},
      title: opts.title,
      // A host (VS Code extension) injects the open folder so `dev` edits it directly.
      workspace_path:
        (typeof window !== "undefined" && (window as any).__NEURA_WORKSPACE__) || undefined,
    }),
    signal,
  });
  if (!resp.body) throw new Error("No response stream");

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (!chunk.startsWith("data:")) continue;
      let ev: any;
      try {
        ev = JSON.parse(chunk.slice(5).trim());
      } catch {
        continue;
      }
      switch (ev.type) {
        case "conversation": cb.onConversation?.(ev); break;
        case "activity":
          cb.onActivity?.(ev.text);
          cb.onLog?.({ kind: "activity", text: ev.text });
          break;
        case "trace":
          cb.onTrace?.(ev.node, ev.path || []);
          break;
        case "sources":
          cb.onSources?.(ev.items);
          cb.onLog?.({ kind: "sources", text: "sources: " + ev.items.map((i: Source) => i.name).join(", ") });
          break;
        case "answer": cb.onAnswer?.(ev.text); break;
        case "suggest_build": cb.onSuggestBuild?.(ev.description); break;
        case "agent_message":
          cb.onAgentMessage?.(ev);
          cb.onLog?.({ kind: ev.agent || "agent", text: ev.text });
          break;
        case "command":
          cb.onCommand?.(ev);
          cb.onLog?.({ kind: "command", text: `$ ${ev.command} (exit ${ev.exit})` });
          break;
        case "file_change":
          cb.onFileChange?.(ev);
          cb.onLog?.({ kind: "edit", text: `${ev.kind || "changed"} ${ev.path}` });
          break;
        case "checklist": cb.onChecklist?.(ev.items || []); break;
        case "progress": cb.onProgress?.(ev.value); break;
        case "image_pending": cb.onImagePending?.(); break;
        case "summary": cb.onSummary?.(ev.text); break;
        case "done": cb.onDone?.(); break;
        case "error": cb.onError?.(ev.text); break;
      }
    }
  }
}

export async function fetchHealth(): Promise<Health> {
  return (await fetch(API_BASE + "/api/health")).json();
}

export async function listConversations(network = "neura"): Promise<Conversation[]> {
  const r = await fetch(`${API_BASE}/api/conversations?network=${encodeURIComponent(network)}`);
  return (await r.json()).conversations ?? [];
}

export async function getConversation(id: string): Promise<{
  id: string;
  title: string;
  summary: string;
  workspace_path?: string;
  local_kb_chunks?: number;
  checklist?: ChecklistItem[];
  messages: { id: string; role: "user" | "ai"; text: string; sources: Source[]; build?: string; trace?: AgentMsg[]; commands?: { command: string; exit: number; output: string }[]; file_changes?: { path: string; diff: string; kind?: string }[] }[];
}> {
  return (await fetch(`${API_BASE}/api/conversations/${id}`)).json();
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" });
}

/** Clear a chat's multi-turn context (keeps messages) — fresh start for a drifted long chat. */
export async function resetContext(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/conversations/${id}/reset`, { method: "POST" });
}

export async function createConversation(network = "neura"): Promise<{ id: string; title: string; network: string }> {
  const r = await fetch(API_BASE + "/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ network }),
  });
  return r.json();
}

export interface NetworkInfo {
  name: string;
  title: string;
  description: string;
  builtin: boolean;
  spawned: boolean;
}

export async function listNetworks(): Promise<NetworkInfo[]> {
  const r = await fetch(API_BASE + "/api/networks");
  return (await r.json()).networks ?? [];
}

export async function spawnNetwork(
  description: string
): Promise<{ status: string; networks?: { name: string; title: string }[]; message?: string; error?: string }> {
  const r = await fetch(API_BASE + "/api/spawn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
  return r.json();
}

export async function deleteNetwork(name: string): Promise<void> {
  await fetch(`${API_BASE}/api/networks/${name}`, { method: "DELETE" });
}

export interface NetworkConfig {
  name: string;
  suggested: { key: string; label: string }[];
  config: Record<string, string>;
}

export async function getNetworkConfig(name: string): Promise<NetworkConfig> {
  return (await fetch(`${API_BASE}/api/networks/${name}/config`)).json();
}

export async function saveNetworkConfig(
  name: string,
  config: Record<string, string>
): Promise<{ ok: boolean; restarting?: boolean }> {
  return (
    await fetch(`${API_BASE}/api/networks/${name}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    })
  ).json();
}

export interface IngestReport {
  files: number;
  chunks: number;
  total: number;
  missing?: string[];
  saved?: string[];
  error?: string;
}

export interface FsListing {
  path: string;
  parent: string | null;
  dirs: string[];
  files: number;
  home: string;
}

export async function fsList(path = ""): Promise<FsListing> {
  const r = await fetch(`${API_BASE}/api/fs?path=${encodeURIComponent(path)}`);
  return r.json();
}

export interface IngestProgress {
  onScan?(info: { total: number; missing: string[] }): void;
  onFile?(info: {
    index: number;
    total: number;
    name: string;
    chunks: number;
    added_files: number;
    added_chunks: number;
  }): void;
  onDone?(report: IngestReport): void;
  onError?(msg: string): void;
}

/** Stream ingestion of the given paths, reporting scan/per-file/done progress.
 *  opts.collection targets a specific collection (e.g. a chat's "chat_<id>");
 *  opts.conversationId records the folder as that chat's workspace. */
export async function streamIngest(
  paths: string[],
  cb: IngestProgress,
  opts: { collection?: string; conversationId?: string } = {}
): Promise<void> {
  const resp = await fetch(API_BASE + "/api/ingest/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, collection: opts.collection, conversation_id: opts.conversationId }),
  });
  if (!resp.body) throw new Error("No stream");
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (!chunk.startsWith("data:")) continue;
      let ev: any;
      try {
        ev = JSON.parse(chunk.slice(5).trim());
      } catch {
        continue;
      }
      if (ev.phase === "scanning") cb.onScan?.({ total: ev.total, missing: ev.missing || [] });
      else if (ev.phase === "file") cb.onFile?.(ev);
      else if (ev.phase === "done") cb.onDone?.(ev as IngestReport);
      else if (ev.phase === "error") cb.onError?.(ev.message);
    }
  }
}

// ---- Code editor (Monaco) over the chat's indexed workspace ----
export async function getTree(cid: string): Promise<{ root: string; files: string[] }> {
  return (await fetch(`${API_BASE}/api/tree?cid=${encodeURIComponent(cid)}`)).json();
}
export async function getFile(cid: string, path: string, ref = ""): Promise<{ content: string; exists?: boolean }> {
  const q = `cid=${encodeURIComponent(cid)}&path=${encodeURIComponent(path)}${ref ? `&ref=${ref}` : ""}`;
  return (await fetch(`${API_BASE}/api/file?${q}`)).json();
}
export async function saveFile(cid: string, path: string, content: string): Promise<{ ok: boolean }> {
  return (
    await fetch(API_BASE + "/api/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: cid, path, content }),
    })
  ).json();
}
export async function getGitStatus(
  cid: string
): Promise<{
  git: boolean;
  branch?: string;
  status: Record<string, string>;
  staged?: Record<string, string>;
  unstaged?: Record<string, string>;
}> {
  return (await fetch(`${API_BASE}/api/git/status?cid=${encodeURIComponent(cid)}`)).json();
}
export async function gitStage(cid: string, path: string, unstage = false): Promise<{ ok?: boolean }> {
  return (
    await fetch(API_BASE + "/api/git/stage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: cid, path, unstage }),
    })
  ).json();
}
export async function gitCommit(cid: string, message: string): Promise<{ ok?: boolean; output?: string; error?: string }> {
  return (
    await fetch(API_BASE + "/api/git/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: cid, message }),
    })
  ).json();
}

/** Clear the global "about me" knowledge base (drops all indexed chunks). */
export async function clearKnowledge(): Promise<{ ok: boolean; chunks: number }> {
  return (await fetch(API_BASE + "/api/knowledge", { method: "DELETE" })).json();
}

export async function uploadFiles(
  files: FileList | File[]
): Promise<{ saved: string[]; skipped: number }> {
  const fd = new FormData();
  Array.from(files).forEach((f) => fd.append("files", f, (f as any).webkitRelativePath || f.name));
  const r = await fetch(API_BASE + "/api/upload", { method: "POST", body: fd });
  return r.json();
}

export interface WatchStatus {
  watching: boolean;
  path?: string;
  reindexing?: boolean;
  last_event?: { name: string; ts: number } | null;
  reindex_count?: number;
  error?: string | null;
}

export async function startWatch(cid: string): Promise<WatchStatus> {
  const r = await fetch(API_BASE + "/api/watch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: cid }),
  });
  return r.json();
}

export async function stopWatch(cid: string): Promise<void> {
  await fetch(`${API_BASE}/api/watch/${cid}`, { method: "DELETE" });
}

export async function getWatch(cid: string): Promise<WatchStatus> {
  return (await fetch(`${API_BASE}/api/watch/${cid}`)).json();
}

export interface ProfileField {
  key: string;
  label: string;
}

export async function getProfile(): Promise<{ profile: Record<string, string>; fields: ProfileField[] }> {
  return (await fetch(API_BASE + "/api/profile")).json();
}

export async function saveProfile(
  profile: Record<string, string>
): Promise<{ ok: boolean; profile: Record<string, string> }> {
  return (
    await fetch(API_BASE + "/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    })
  ).json();
}

export interface LlmProvider {
  id: string;
  label: string;
  env_key: string;
  models: string[];
  key_set: boolean;
}
export interface LlmSettings {
  active: { provider: string; model: string | null };
  providers: LlmProvider[];
}

export async function getLlm(): Promise<LlmSettings> {
  return (await fetch(API_BASE + "/api/llm")).json();
}
export async function saveLlm(
  provider: string,
  model: string,
  apiKey?: string
): Promise<{ ok?: boolean; restarting?: boolean; error?: string }> {
  return (
    await fetch(API_BASE + "/api/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model, api_key: apiKey || "" }),
    })
  ).json();
}

// Set (or clear, with empty provider+model) one agent's LLM inside a network.
export async function setAgentLlm(
  network: string,
  agent: string,
  provider: string,
  model: string,
  temperature?: number | null
): Promise<{ ok?: boolean; restarting?: boolean; error?: string }> {
  return (
    await fetch(`${API_BASE}/api/networks/${encodeURIComponent(network)}/agent-llm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent, provider, model, temperature: temperature ?? null }),
    })
  ).json();
}

export interface RadarArea {
  label: string;
  query: string;
}
export interface RadarItem {
  id: string;
  title: string;
  authors: string[];
  published: string;
  url: string;
  abstract: string;
  area: string;
  summary?: string;
  skill?: string;
  action?: string; // "read" | "try"
  status?: string; // "new" | "read" | "dismissed"
}
export interface RadarDoc {
  generated: string | null;
  day: string | null;
  areas: RadarArea[];
  items: RadarItem[];
}
export async function getRadar(refresh = false): Promise<RadarDoc> {
  return (await fetch(`${API_BASE}/api/radar${refresh ? "?refresh=true" : ""}`)).json();
}
export async function refreshRadar(): Promise<RadarDoc> {
  return (await fetch(API_BASE + "/api/radar/refresh", { method: "POST" })).json();
}
export async function getRadarPaper(id: string): Promise<{ item: RadarItem | null; error?: string }> {
  return (await fetch(`${API_BASE}/api/radar/paper?id=${encodeURIComponent(id)}`)).json();
}
export async function setRadarAreas(areas: RadarArea[]): Promise<RadarDoc> {
  return (
    await fetch(API_BASE + "/api/radar/areas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ areas }),
    })
  ).json();
}
export async function setRadarItemStatus(id: string, status: string): Promise<{ ok: boolean }> {
  return (
    await fetch(`${API_BASE}/api/radar/item/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    })
  ).json();
}

export interface WorkflowMemoryEntry {
  id: string;
  key: string;
  value: string;
  source: string; // "auto" | "model" | "user"
  ts: string;
}
export interface WorkflowMemoryDoc {
  conversation_id: string;
  title: string;
  created: string | null;
  updated: string | null;
  entries: WorkflowMemoryEntry[];
}
export async function getWorkflowMemory(cid: string): Promise<WorkflowMemoryDoc> {
  return (await fetch(`${API_BASE}/api/workflow-memory/${cid}`)).json();
}
export async function addWorkflowMemory(
  cid: string,
  value: string,
  key = "note"
): Promise<{ ok: boolean; entry: WorkflowMemoryEntry | null }> {
  return (
    await fetch(`${API_BASE}/api/workflow-memory/${cid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, key }),
    })
  ).json();
}
export async function deleteWorkflowMemoryEntry(cid: string, id: string): Promise<{ ok: boolean }> {
  return (await fetch(`${API_BASE}/api/workflow-memory/${cid}/${id}`, { method: "DELETE" })).json();
}
export async function clearWorkflowMemory(cid: string): Promise<{ ok: boolean }> {
  return (await fetch(`${API_BASE}/api/workflow-memory/${cid}`, { method: "DELETE" })).json();
}

export interface MemoryItem {
  topic: string;
  content: string;
}
export interface MemorySuggested {
  key: string;
  label: string;
  placeholder?: string;
}

export async function getMemory(): Promise<{ items: MemoryItem[]; suggested: MemorySuggested[] }> {
  return (await fetch(API_BASE + "/api/memory")).json();
}
export async function setMemory(topic: string, content: string): Promise<{ ok: boolean; topic: string }> {
  return (
    await fetch(API_BASE + "/api/memory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, content }),
    })
  ).json();
}
export async function deleteMemory(topic: string): Promise<void> {
  await fetch(`${API_BASE}/api/memory/${encodeURIComponent(topic)}`, { method: "DELETE" });
}

/** Rewrite an answer into a short, natural spoken version (for TTS). */
export async function speechify(text: string): Promise<string> {
  try {
    const r = await fetch(API_BASE + "/api/speechify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const d = await r.json();
    return d.text || text;
  } catch {
    return text;
  }
}

export async function synthesize(text: string, voice = "af_heart"): Promise<Blob> {
  const r = await fetch(API_BASE + "/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.slice(0, 1500), voice, speed: 1.0 }),
  });
  if (!r.ok) throw new Error("TTS unavailable");
  return r.blob();
}
