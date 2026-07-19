import { useEffect, useRef, useState } from "react";
import { createConversation, fsList, streamIngest, uploadFiles, type FsListing, type IngestReport } from "../api";
import { Doc, Close, Clip, Folder, ArrowUp, ChevronRight, Home } from "../icons";

interface Props {
  open: boolean;
  kbChunks: number | null;
  initialScope?: "chat" | "global";
  currentConversationId: string | null;
  currentNetwork: string;
  onClose(): void;
  onConversationCreated(id: string): void;
  onComplete(info: { scope: "chat" | "global"; total?: number; conversationId?: string; path?: string }): void;
}

const ALLOWED = new Set([
  ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml",
  ".yml", ".toml", ".hocon", ".cfg", ".ini", ".csv", ".html", ".css", ".sh",
  ".sql", ".java", ".go", ".rb", ".pdf",
]);
const MAX_BYTES = 2 * 1024 * 1024;
const ext = (name: string) => {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
};

type Phase = "idle" | "browse" | "uploading" | "indexing" | "done" | "error";
type Scope = "chat" | "global";

export default function KnowledgeModal(p: Props) {
  const { open, kbChunks, initialScope, currentConversationId, currentNetwork, onClose, onConversationCreated, onComplete } = p;
  const [scope, setScope] = useState<Scope>(initialScope || "chat");
  const [phase, setPhase] = useState<Phase>("idle");
  const [paths, setPaths] = useState("");
  const [fs, setFs] = useState<FsListing | null>(null);
  const [fsLoading, setFsLoading] = useState(false);
  const [uploadCount, setUploadCount] = useState(0);
  const [prog, setProg] = useState({ index: 0, total: 0, name: "", files: 0, chunks: 0 });
  const [log, setLog] = useState<string[]>([]);
  const [report, setReport] = useState<IngestReport | null>(null);
  const [error, setError] = useState("");
  const filesRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setScope(initialScope || "chat");
      setPhase("idle");
      setPaths("");
      setFs(null);
      setUploadCount(0);
      setProg({ index: 0, total: 0, name: "", files: 0, chunks: 0 });
      setLog([]);
      setReport(null);
      setError("");
    }
  }, [open]);

  const busy = phase === "uploading" || phase === "indexing";

  // Resolve the target collection + conversation for the chosen scope.
  async function resolveTarget(): Promise<{ collection?: string; conversationId?: string }> {
    if (scope === "global") return {};
    let cid = currentConversationId;
    if (!cid) {
      const c = await createConversation(currentNetwork);
      cid = c.id;
      onConversationCreated(cid);
    }
    return { collection: `chat_${cid}`, conversationId: cid };
  }

  async function loadFs(path: string) {
    setFsLoading(true);
    try {
      setFs(await fsList(path));
    } catch (e: any) {
      setError(String(e?.message || e));
    }
    setFsLoading(false);
  }

  async function runStream(list: string[]) {
    setPhase("indexing");
    setLog([]);
    setProg({ index: 0, total: 0, name: "", files: 0, chunks: 0 });
    try {
      const target = await resolveTarget();
      await streamIngest(
        list,
        {
          onScan: ({ total }) => setProg((s) => ({ ...s, total, index: 0 })),
          onFile: (f) => {
            setProg({ index: f.index, total: f.total, name: f.name, files: f.added_files, chunks: f.added_chunks });
            if (f.chunks > 0) setLog((l) => [`${f.name} → ${f.chunks} chunks`, ...l].slice(0, 6));
          },
          onDone: (r) => {
            setReport(r);
            setPhase("done");
            onComplete({ scope, total: r.total, conversationId: target.conversationId, path: list[0] });
          },
          onError: (msg) => {
            setError(msg);
            setPhase("error");
          },
        },
        target
      );
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase("error");
    }
  }

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || !fileList.length || busy) return;
    const all = Array.from(fileList);
    const picked = all.filter((f) => ALLOWED.has(ext(f.name)) && f.size <= MAX_BYTES);
    if (!picked.length) {
      setError(`No supported files (checked ${all.length}). Supported: text, code, PDF under 2 MB.`);
      setPhase("error");
      return;
    }
    setError("");
    setPhase("uploading");
    setUploadCount(picked.length);
    try {
      const res = await uploadFiles(picked);
      if (!res.saved?.length) {
        setError("Upload produced no indexable files.");
        setPhase("error");
        return;
      }
      await runStream(res.saved);
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase("error");
    }
  }

  function addPaths() {
    const list = paths.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    if (list.length) runStream(list);
  }

  if (!open) return null;
  const pct = prog.total ? Math.round((prog.index / prog.total) * 100) : 0;

  return (
    <div className="modal-scrim" onClick={busy ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">
            <Doc className="wand" />
            Add to knowledge base
          </div>
          {!busy && <button className="modal-x" onClick={onClose}><Close /></button>}
        </div>

        {(phase === "idle" || phase === "error") && (
          <>
            {/* Scope selector */}
            <div className="scope-row">
              <button className={"scope-btn" + (scope === "chat" ? " on" : "")} onClick={() => setScope("chat")}>
                <Home /> This chat
                <span className="scope-sub">workspace for this conversation</span>
              </button>
              <button className={"scope-btn" + (scope === "global" ? " on" : "")} onClick={() => setScope("global")}>
                <Doc /> Global
                <span className="scope-sub">about-me, all chats</span>
              </button>
            </div>
            <p className="modal-sub">
              {scope === "chat" ? (
                <>Index a folder as <strong>this chat's</strong> workspace — Neura will ground answers here
                first (great for the codebase you're editing). Falls back to global when needed.</>
              ) : (
                <>Index into your <strong>global</strong> knowledge base (available in every chat).
                {kbChunks != null && <> Currently <strong>{kbChunks.toLocaleString()}</strong> global chunks.</>}</>
              )}
              {" "}Everything is chunked & embedded locally.
            </p>

            <input ref={filesRef} type="file" multiple style={{ display: "none" }}
              onChange={(e) => handleFiles(e.target.files)} />

            <div className="pick-row">
              <button className="pick-btn" onClick={() => { setError(""); setPhase("browse"); loadFs(""); }}>
                <Folder /> Browse for a folder
              </button>
              <button className="pick-btn" onClick={() => filesRef.current?.click()}>
                <Clip /> Select files
              </button>
            </div>
            <div className="pick-hint">Folders are scanned in place (no upload) and indexed recursively; build/dependency folders are skipped.</div>

            <div className="or-row"><span>or type absolute paths</span></div>
            <textarea className="modal-input" rows={2}
              placeholder={"/Users/you/my-repo"} value={paths} onChange={(e) => setPaths(e.target.value)} />
            {error && <div className="modal-error">⚠️ {error}</div>}
            <div className="modal-actions">
              <button className="btn-ghost" onClick={onClose}>Cancel</button>
              <button className="btn-primary" onClick={addPaths} disabled={!paths.trim()}>
                <Doc /> Add paths
              </button>
            </div>
          </>
        )}

        {phase === "browse" && (
          <>
            <div className="fs-path" title={fs?.path}>{fs?.path || "…"}</div>
            <div className="fs-list">
              {fs?.parent && (
                <button className="fs-row up" onClick={() => loadFs(fs.parent!)}>
                  <ArrowUp /> <span>Up one level</span>
                </button>
              )}
              {fsLoading && <div className="muted-empty" style={{ padding: "10px" }}>Loading…</div>}
              {!fsLoading && fs?.dirs.length === 0 && (
                <div className="muted-empty" style={{ padding: "10px" }}>No sub-folders here.</div>
              )}
              {!fsLoading && fs?.dirs.map((d) => (
                <button key={d} className="fs-row" onClick={() => loadFs(`${fs.path}/${d}`)}>
                  <Folder /> <span className="conv-title">{d}</span> <ChevronRight />
                </button>
              ))}
            </div>
            <div className="pick-hint">Indexing into: <strong>{scope === "chat" ? "this chat" : "global"}</strong></div>
            <div className="modal-actions">
              <button className="btn-ghost" onClick={() => setPhase("idle")}>Back</button>
              <button className="btn-primary" onClick={() => fs && runStream([fs.path])} disabled={!fs}>
                <Folder /> Index this folder
              </button>
            </div>
          </>
        )}

        {(phase === "uploading" || phase === "indexing") && (
          <div className="ingest-live">
            <div className="loader-orb" />
            <div className="ingest-phase">
              {phase === "uploading"
                ? `Uploading ${uploadCount} file${uploadCount > 1 ? "s" : ""}…`
                : `Indexing ${prog.total ? `${prog.index} / ${prog.total}` : "…"}`}
            </div>
            <div className="progress-track"><i style={{ width: `${phase === "uploading" ? 8 : pct}%` }} /></div>
            {phase === "indexing" && (
              <>
                <div className="ingest-current" title={prog.name}>
                  {prog.name ? <>Chunking <strong>{prog.name}</strong></> : "Scanning files…"}
                </div>
                <div className="ingest-counts">
                  {prog.files} file{prog.files === 1 ? "" : "s"} · {prog.chunks} chunks · into {scope === "chat" ? "this chat" : "global"}
                </div>
                {log.length > 0 && (
                  <div className="ingest-log">
                    {log.map((l, i) => (
                      <div key={i} className="ingest-log-row"><span className="tick">✓</span> {l}</div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {phase === "done" && report && (
          <div className="modal-done">
            <div className="done-badge">✓</div>
            <h3>{scope === "chat" ? "This chat's workspace is ready" : "Global knowledge updated"}</h3>
            <p className="modal-sub">
              Indexed <strong>{report.files}</strong> file(s) → <strong>{report.chunks}</strong> new chunks
              ({scope === "chat" ? "this chat" : "global"} now holds <strong>{report.total?.toLocaleString()}</strong>).
              {report.missing?.length ? <div className="miss">Not found: {report.missing.join(", ")}</div> : null}
            </p>
            <div className="modal-actions center">
              <button className="btn-primary" onClick={onClose}>Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
