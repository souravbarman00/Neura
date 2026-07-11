import { useEffect, useMemo, useState } from "react";
import { Editor, DiffEditor } from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getTree, getFile, saveFile, getGitStatus, gitCommit, gitStage } from "../api";
import { Folder, ChevronRight, Files, Branch, Close, ExternalLink } from "../icons";

const MD_COMPONENTS = {
  a: ({ href, children }: any) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="md-link">
      {children}
      <ExternalLink className="md-ext" />
    </a>
  ),
  table: ({ children }: any) => (
    <div className="md-table-wrap">
      <table>{children}</table>
    </div>
  ),
};

interface TreeNode {
  name: string;
  path: string;
  dir: boolean;
  children: TreeNode[];
}
interface FileState {
  content: string;
  saved: string;
  head: string | null;
}

function buildTree(files: string[]): TreeNode {
  const root: TreeNode = { name: "", path: "", dir: true, children: [] };
  for (const f of files) {
    const parts = f.split("/");
    let node = root;
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1;
      const path = parts.slice(0, i + 1).join("/");
      let child = node.children.find((c) => c.name === part && c.dir === !isFile);
      if (!child) {
        child = { name: part, path, dir: !isFile, children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sortRec = (n: TreeNode) => {
    n.children.sort((a, b) => (a.dir === b.dir ? a.name.localeCompare(b.name) : a.dir ? -1 : 1));
    n.children.forEach(sortRec);
  };
  sortRec(root);
  return root;
}

const STATUS_COLOR: Record<string, string> = { M: "#e6b450", A: "#48c78e", U: "#48c78e", D: "#f2647a", R: "#7c7cf6" };
const STATUS_LABEL: Record<string, string> = { M: "Modified", A: "Added", U: "Untracked", D: "Deleted", R: "Renamed" };

function base(path: string) {
  return path.split("/").pop() || path;
}
function langOf(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript", py: "python",
    json: "json", md: "markdown", css: "css", scss: "scss", html: "html", sh: "shell",
    yaml: "yaml", yml: "yaml", hocon: "ini", toml: "ini", sql: "sql", go: "go", rs: "rust",
    java: "java", c: "c", cpp: "cpp", txt: "plaintext",
  };
  return map[ext] || "plaintext";
}

export default function CodeView({ conversationId, theme }: { conversationId: string | null; theme: "light" | "dark" }) {
  const cid = conversationId;
  const [view, setView] = useState<"explorer" | "scm">(
    () => (typeof location !== "undefined" && new URLSearchParams(location.search).get("scm") ? "scm" : "explorer")
  );
  const [files, setFiles] = useState<string[]>([]);
  const [root, setRoot] = useState("");
  const [status, setStatus] = useState<Record<string, string>>({});
  const [staged, setStaged] = useState<Record<string, string>>({});
  const [unstaged, setUnstaged] = useState<Record<string, string>>({});
  const [branch, setBranch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [tabs, setTabs] = useState<string[]>([]);
  const [active, setActive] = useState("");
  const [cache, setCache] = useState<Record<string, FileState>>({});
  const [diff, setDiff] = useState(false);
  const [preview, setPreview] = useState(false);
  const [commitMsg, setCommitMsg] = useState("");
  const [committing, setCommitting] = useState(false);
  const [saving, setSaving] = useState(false);

  function refresh() {
    if (!cid) return;
    getTree(cid).then((t) => {
      setFiles(t.files || []);
      setRoot(t.root || "");
      const dirs = new Set<string>();
      (t.files || []).forEach((f) => f.includes("/") && dirs.add(f.split("/")[0]));
      setExpanded((o) => new Set([...o, ...dirs]));
    });
    getGitStatus(cid).then((g) => {
      setStatus(g.status || {});
      setStaged(g.staged || {});
      setUnstaged(g.unstaged || {});
      setBranch(g.branch || "");
    });
  }
  useEffect(refresh, [cid]);

  async function stage(path: string, unstage = false, e?: React.MouseEvent) {
    e?.stopPropagation();
    if (!cid) return;
    await gitStage(cid, path, unstage);
    getGitStatus(cid).then((g) => {
      setStatus(g.status || {});
      setStaged(g.staged || {});
      setUnstaged(g.unstaged || {});
    });
  }

  // Deep-link: ?file=<relpath> auto-opens that file once the tree has loaded.
  useEffect(() => {
    const f = new URLSearchParams(location.search).get("file");
    if (f && files.includes(f) && active !== f) openFile(f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  const tree = useMemo(() => buildTree(files), [files]);

  const isMdPath = (p: string) => /\.(md|markdown)$/i.test(p);

  async function openFile(path: string, asDiff = false) {
    if (!cid) return;
    setActive(path);
    setDiff(asDiff);
    setPreview(isMdPath(path) && !asDiff); // markdown opens in rendered preview by default
    setTabs((t) => (t.includes(path) ? t : [...t, path]));
    if (!cache[path]) {
      const r = await getFile(cid, path);
      let head: string | null = null;
      if (status[path] && status[path] !== "U") {
        const h = await getFile(cid, path, "HEAD");
        head = h.exists ? h.content : "";
      }
      setCache((c) => ({ ...c, [path]: { content: r.content || "", saved: r.content || "", head } }));
    }
  }
  function closeTab(path: string, e?: React.MouseEvent) {
    e?.stopPropagation();
    setTabs((t) => {
      const nt = t.filter((p) => p !== path);
      if (active === path) setActive(nt[nt.length - 1] || "");
      return nt;
    });
  }
  function edit(val: string) {
    setCache((c) => ({ ...c, [active]: { ...c[active], content: val } }));
  }
  async function save() {
    if (!cid || !active || saving) return;
    setSaving(true);
    try {
      await saveFile(cid, active, cache[active].content);
      setCache((c) => ({ ...c, [active]: { ...c[active], saved: c[active].content } }));
      getGitStatus(cid).then((g) => setStatus(g.status || {}));
    } finally {
      setSaving(false);
    }
  }
  async function commit() {
    if (!cid || !commitMsg.trim() || committing) return;
    setCommitting(true);
    try {
      await gitCommit(cid, commitMsg.trim());
      setCommitMsg("");
      // reflect the new committed state
      setCache({});
      refresh();
    } finally {
      setCommitting(false);
    }
  }

  const cur = cache[active];
  const dirty = (p: string) => cache[p] && cache[p].content !== cache[p].saved;
  const changed = !!(active && status[active] && status[active] !== "U" && cur && cur.head !== null);
  const monacoTheme = theme === "light" ? "light" : "vs-dark";
  const changedFiles = Object.keys(status);
  const stagedFiles = Object.keys(staged);
  const unstagedFiles = Object.keys(unstaged);
  const dirOf = (f: string) => (f.includes("/") ? f.slice(0, f.lastIndexOf("/")) : "");

  function renderNode(node: TreeNode, depth: number): any {
    return node.children.map((c) => {
      if (c.dir) {
        const isOpen = expanded.has(c.path);
        return (
          <div key={c.path}>
            <div
              className="cv-row cv-dir"
              style={{ paddingLeft: 8 + depth * 12 }}
              onClick={() =>
                setExpanded((o) => {
                  const n = new Set(o);
                  n.has(c.path) ? n.delete(c.path) : n.add(c.path);
                  return n;
                })
              }
            >
              <ChevronRight className={"cv-chev" + (isOpen ? " open" : "")} />
              <span className="cv-name">{c.name}</span>
            </div>
            {isOpen && renderNode(c, depth + 1)}
          </div>
        );
      }
      const st = status[c.path];
      return (
        <div
          key={c.path}
          className={"cv-row cv-file" + (active === c.path ? " sel" : "")}
          style={{ paddingLeft: 8 + depth * 12 + 14 }}
          onClick={() => openFile(c.path)}
        >
          <span className="cv-name" style={st ? { color: STATUS_COLOR[st] } : undefined}>{c.name}</span>
          {st && <span className="cv-badge" style={{ color: STATUS_COLOR[st] }}>{st}</span>}
        </div>
      );
    });
  }

  if (!cid) return <div className="cv-empty">Open a chat and index a folder to browse its code here.</div>;
  if (!root)
    return (
      <div className="cv-empty">
        No workspace for this chat yet. Use <b>📁 Index this chat's folder</b> in the composer, and its files appear here.
      </div>
    );

  return (
    <div className="codeview">
      <div className="cv-activity">
        <button className={"cv-act" + (view === "explorer" ? " on" : "")} title="Explorer" onClick={() => setView("explorer")}>
          <Files />
        </button>
        <button className={"cv-act" + (view === "scm" ? " on" : "")} title="Source Control" onClick={() => setView("scm")}>
          <Branch />
          {changedFiles.length > 0 && <span className="cv-act-badge">{changedFiles.length}</span>}
        </button>
      </div>

      {view === "explorer" ? (
        <div className="cv-side">
          <div className="cv-side-head">
            <span className="cv-side-title">Explorer</span>
            {branch && <span className="cv-branch">⎇ {branch}</span>}
            <button className="cv-refresh" title="Refresh" onClick={refresh}>⟳</button>
          </div>
          <div className="cv-tree-body">{renderNode(tree, 0)}</div>
        </div>
      ) : (
        <div className="cv-side">
          <div className="cv-side-head">
            <span className="cv-side-title">Source Control</span>
            {branch && <span className="cv-branch">⎇ {branch}</span>}
            <button className="cv-refresh" title="Refresh" onClick={refresh}>⟳</button>
          </div>
          <div className="cv-commit">
            <textarea
              className="cv-commit-msg"
              placeholder={`Message (commit on ${branch || "branch"})`}
              value={commitMsg}
              rows={2}
              onChange={(e) => setCommitMsg(e.target.value)}
            />
            <button
              className="cv-commit-btn"
              disabled={!commitMsg.trim() || (!stagedFiles.length && !unstagedFiles.length) || committing}
              onClick={commit}
            >
              {committing ? "Committing…" : stagedFiles.length ? `Commit (${stagedFiles.length})` : "Commit all"}
            </button>
          </div>
          <div className="cv-tree-body">
            {stagedFiles.length > 0 && (
              <>
                <div className="cv-scm-label">
                  Staged Changes
                  <button className="cv-scm-bulk" title="Unstage all" onClick={() => stagedFiles.forEach((f) => stage(f, true))}>−</button>
                </div>
                {stagedFiles.map((f) => (
                  <div key={"s" + f} className={"cv-row cv-file cv-scm-row" + (active === f ? " sel" : "")} onClick={() => openFile(f, true)} title={f}>
                    <span className="cv-name">{base(f)}</span>
                    <span className="cv-scm-dir">{dirOf(f)}</span>
                    <button className="cv-scm-act" title="Unstage" onClick={(e) => stage(f, true, e)}>−</button>
                    <span className="cv-badge" style={{ color: STATUS_COLOR[staged[f]] }} title={STATUS_LABEL[staged[f]]}>{staged[f]}</span>
                  </div>
                ))}
              </>
            )}
            <div className="cv-scm-label">
              Changes
              {unstagedFiles.length > 0 && (
                <button className="cv-scm-bulk" title="Stage all" onClick={() => unstagedFiles.forEach((f) => stage(f, false))}>+</button>
              )}
            </div>
            {unstagedFiles.length === 0 ? (
              <div className="cv-scm-empty">No changes</div>
            ) : (
              unstagedFiles.map((f) => (
                <div key={"u" + f} className={"cv-row cv-file cv-scm-row" + (active === f ? " sel" : "")} onClick={() => openFile(f, unstaged[f] !== "U")} title={f}>
                  <span className="cv-name">{base(f)}</span>
                  <span className="cv-scm-dir">{dirOf(f)}</span>
                  <button className="cv-scm-act" title="Stage" onClick={(e) => stage(f, false, e)}>+</button>
                  <span className="cv-badge" style={{ color: STATUS_COLOR[unstaged[f]] }} title={STATUS_LABEL[unstaged[f]]}>{unstaged[f]}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <div className="cv-editor">
        {tabs.length > 0 && (
          <div className="cv-tabs">
            {tabs.map((p) => (
              <div key={p} className={"cv-tab" + (active === p ? " active" : "")} onClick={() => { setActive(p); setDiff(false); }} title={p}>
                <span className="cv-tab-name">{base(p)}</span>
                {dirty(p) ? <span className="cv-tab-dot">●</span> : null}
                <button className="cv-tab-x" onClick={(e) => closeTab(p, e)}><Close /></button>
              </div>
            ))}
          </div>
        )}
        {active && cur ? (
          <>
            <div className="cv-ed-head">
              {isMdPath(active) && (
                <button
                  className={"cv-diff-toggle" + (preview ? " on" : "")}
                  onClick={() => { setPreview((v) => !v); if (!preview) setDiff(false); }}
                >
                  {preview ? "Edit" : "Preview"}
                </button>
              )}
              {changed && !preview && (
                <button className={"cv-diff-toggle" + (diff ? " on" : "")} onClick={() => setDiff((v) => !v)}>
                  {diff ? "Editing" : "Diff vs HEAD"}
                </button>
              )}
              <button className="cv-save" disabled={!dirty(active) || saving} onClick={save}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
            <div className="cv-ed-body">
              {preview && isMdPath(active) ? (
                <div className="cv-md-preview">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                    {cur.content}
                  </ReactMarkdown>
                </div>
              ) : diff && changed ? (
                <DiffEditor
                  original={cur.head || ""}
                  modified={cur.content}
                  language={langOf(active)}
                  theme={monacoTheme}
                  options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, fontSize: 12.5, automaticLayout: true }}
                />
              ) : (
                <Editor
                  path={active}
                  value={cur.content}
                  language={langOf(active)}
                  theme={monacoTheme}
                  onChange={(v) => edit(v ?? "")}
                  options={{ minimap: { enabled: false }, fontSize: 12.5, scrollBeyondLastLine: false, automaticLayout: true }}
                />
              )}
            </div>
          </>
        ) : (
          <div className="cv-empty">Select a file to view or edit it.</div>
        )}
      </div>
    </div>
  );
}
