import { useCallback, useEffect, useState } from "react";
import {
  getWorkflowMemory,
  addWorkflowMemory,
  deleteWorkflowMemoryEntry,
  clearWorkflowMemory,
  type WorkflowMemoryEntry,
} from "../api";
import { Plus, Trash } from "../icons";

interface Props {
  conversationId: string | null;
  refreshKey?: number; // bump to re-fetch (e.g. after a turn auto-captures details)
}

export default function WorkflowMemoryPanel({ conversationId, refreshKey }: Props) {
  const [entries, setEntries] = useState<WorkflowMemoryEntry[]>([]);
  const [val, setVal] = useState("");
  const [key, setKey] = useState("note");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!conversationId) {
      setEntries([]);
      return;
    }
    setLoading(true);
    try {
      const doc = await getWorkflowMemory(conversationId);
      setEntries(doc.entries || []);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  async function add() {
    const v = val.trim();
    if (!v || !conversationId) return;
    setVal("");
    await addWorkflowMemory(conversationId, v, key.trim() || "note");
    load();
  }
  async function del(id: string) {
    if (!conversationId) return;
    await deleteWorkflowMemoryEntry(conversationId, id);
    setEntries((e) => e.filter((x) => x.id !== id));
  }
  async function clearAll() {
    if (!conversationId || entries.length === 0) return;
    if (!window.confirm("Delete all memory for this workflow? This can't be undone.")) return;
    await clearWorkflowMemory(conversationId);
    setEntries([]);
  }

  if (!conversationId) {
    return <div className="wm-empty muted-empty">Start the task — details Neura captures will appear here.</div>;
  }

  return (
    <div className="wm">
      <div className="wm-head">
        <span className="wm-title">This workflow's memory</span>
        {entries.length > 0 && (
          <button className="wm-clear" onClick={clearAll} title="Delete all memory for this workflow">
            Clear all
          </button>
        )}
      </div>

      {loading && entries.length === 0 ? (
        <div className="wm-empty muted-empty">Loading…</div>
      ) : entries.length === 0 ? (
        <div className="wm-empty muted-empty">
          Nothing yet. Neura auto-saves key details (ticket, branch, PR, decisions) as it works — or add your own below.
        </div>
      ) : (
        <ul className="wm-list">
          {entries.map((e) => (
            <li className="wm-item" key={e.id}>
              <span className={"wm-key wm-src-" + e.source}>{e.key}</span>
              <span className="wm-val" title={e.value}>{e.value}</span>
              <button className="wm-del" onClick={() => del(e.id)} title="Delete this entry">
                <Trash />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="wm-add">
        <input
          className="wm-in wm-in-key"
          value={key}
          onChange={(ev) => setKey(ev.target.value)}
          placeholder="key"
          title="Short label, e.g. jira, branch, decision"
        />
        <input
          className="wm-in wm-in-val"
          value={val}
          onChange={(ev) => setVal(ev.target.value)}
          onKeyDown={(ev) => ev.key === "Enter" && add()}
          placeholder="Remember for this task…"
        />
        <button className="wm-addbtn" onClick={add} disabled={!val.trim()} title="Add to workflow memory">
          <Plus />
        </button>
      </div>
    </div>
  );
}
