import { useEffect, useState } from "react";
import { getMemory, setMemory, deleteMemory, type MemorySuggested } from "../api";
import { Plus, Trash } from "../icons";

interface Row {
  topic: string;
  content: string;
  label?: string;
  placeholder?: string;
  fixed: boolean; // suggested identity field (topic locked) vs custom
}

// Manage Neura's long-term memory — the facts it recalls across every conversation
// (GitHub id, Jira/Confluence space, Slack workspace…) plus any custom entries.
export default function MemoryPanel() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<"" | "saving" | "done">("");

  useEffect(() => {
    setLoading(true);
    getMemory()
      .then(({ items, suggested }) => {
        const byTopic = new Map(items.map((i) => [i.topic, i.content]));
        const suggestedKeys = new Set(suggested.map((s: MemorySuggested) => s.key));
        const out: Row[] = suggested.map((s) => ({
          topic: s.key,
          content: byTopic.get(s.key) || "",
          label: s.label,
          placeholder: s.placeholder,
          fixed: true,
        }));
        items.forEach((i) => {
          if (!suggestedKeys.has(i.topic)) out.push({ topic: i.topic, content: i.content, fixed: false });
        });
        setRows(out);
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  function update(i: number, patch: Partial<Row>) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function addRow() {
    setRows((r) => [...r, { topic: "", content: "", fixed: false }]);
  }
  function removeRow(i: number) {
    const row = rows[i];
    if (row.topic && (row.fixed || row.content)) deleteMemory(row.topic).catch(() => {});
    setRows((r) => r.filter((_, idx) => idx !== i));
  }

  async function save() {
    setStatus("saving");
    try {
      for (const row of rows) {
        const topic = row.topic.trim();
        if (!topic) continue;
        // empty value clears the memory server-side
        await setMemory(topic, row.content.trim());
      }
      setStatus("done");
      setTimeout(() => setStatus(""), 2000);
    } catch {
      setStatus("");
    }
  }

  const busy = status === "saving";

  return (
    <div>
      <p className="modal-sub">
        Facts Neura remembers across every conversation — it checks these before acting (e.g. to
        open a PR it uses your GitHub username & repo). Stored locally as markdown; nothing leaves
        your device. Leave a value blank to forget it.
      </p>

      {loading ? (
        <div className="muted-empty">Loading…</div>
      ) : (
        <div className="mem-list">
          {rows.map((r, i) => (
            <div className="mem-row" key={i}>
              {r.fixed ? (
                <label className="mem-key" title={r.topic}>{r.label}</label>
              ) : (
                <input
                  className="modal-input mem-key-input"
                  placeholder="topic_name"
                  value={r.topic}
                  onChange={(e) => update(i, { topic: e.target.value })}
                  disabled={busy}
                />
              )}
              <input
                className="modal-input"
                placeholder={r.placeholder || "value…"}
                value={r.content}
                onChange={(e) => update(i, { content: e.target.value })}
                disabled={busy}
              />
              <button className="cfg-del" title="Forget" onClick={() => removeRow(i)} disabled={busy}>
                <Trash />
              </button>
            </div>
          ))}
        </div>
      )}

      <button className="cfg-add" onClick={addRow} disabled={busy}>
        <Plus /> Add a memory
      </button>
      <div className="modal-actions">
        <button className="btn-primary" onClick={save} disabled={busy || loading}>
          {status === "saving" ? <><span className="spin" /> Saving…</> : status === "done" ? "✓ Saved to memory" : "Save memory"}
        </button>
      </div>
    </div>
  );
}
