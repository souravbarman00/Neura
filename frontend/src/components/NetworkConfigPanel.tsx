import { useEffect, useState } from "react";
import { fetchHealth, getNetworkConfig, saveNetworkConfig } from "../api";
import { Plus, Trash, Lock } from "../icons";

interface Field {
  key: string;
  value: string;
  fixed: boolean; // derived/suggested key (name locked) vs custom
}

export default function NetworkConfigPanel({ network }: { network: string }) {
  const [fields, setFields] = useState<Field[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<"" | "saving" | "restarting" | "done">("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setStatus("");
    getNetworkConfig(network)
      .then((cfg) => {
        if (cancelled) return;
        const saved = cfg.config || {};
        const suggestedKeys = cfg.suggested.map((s) => s.key);
        const rows: Field[] = cfg.suggested.map((s) => ({ key: s.key, value: saved[s.key] || "", fixed: true }));
        // any saved keys that weren't in the suggested set → editable custom rows
        Object.keys(saved).forEach((k) => {
          if (!suggestedKeys.includes(k)) rows.push({ key: k, value: saved[k], fixed: false });
        });
        setFields(rows);
      })
      .catch(() => setFields([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [network]);

  function update(i: number, patch: Partial<Field>) {
    setFields((f) => f.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function addField() {
    setFields((f) => [...f, { key: "", value: "", fixed: false }]);
  }
  function removeField(i: number) {
    setFields((f) => f.filter((_, idx) => idx !== i));
  }

  async function save() {
    const config: Record<string, string> = {};
    fields.forEach((f) => {
      if (f.key.trim() && f.value.trim()) config[f.key.trim()] = f.value.trim();
    });
    setStatus("saving");
    try {
      await saveNetworkConfig(network, config);
      setStatus("restarting");
      // Wait for the runtime to come back after the reload.
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const h = await fetchHealth();
          if (h.runtime) break;
        } catch {
          /* keep polling */
        }
      }
      setStatus("done");
      setTimeout(() => setStatus(""), 2500);
    } catch {
      setStatus("");
    }
  }

  const busy = status === "saving" || status === "restarting";

  return (
    <div>
      <div className="rhead">
        <h3>Configuration</h3>
        <span className="badge">grounding</span>
      </div>
      <div className="card">
        <p className="cfg-intro">
          Add the connection strings & API keys this agent needs. Saved locally to <code>.env</code>;
          the runtime reloads so the network picks them up.
        </p>

        {loading && <div className="muted-empty">Loading…</div>}

        {!loading && fields.length === 0 && (
          <div className="muted-empty" style={{ marginBottom: 10 }}>
            No required keys detected. Add any connection string this agent should use.
          </div>
        )}

        {fields.map((f, i) => (
          <div className="cfg-field" key={i}>
            {f.fixed ? (
              <label className="cfg-key" title={f.key}>{f.key}</label>
            ) : (
              <input
                className="cfg-input key"
                placeholder="KEY_NAME"
                value={f.key}
                onChange={(e) => update(i, { key: e.target.value })}
                disabled={busy}
              />
            )}
            <div className="cfg-valwrap">
              <Lock className="cfg-lock" />
              <input
                className="cfg-input"
                type="password"
                placeholder="paste value…"
                value={f.value}
                onChange={(e) => update(i, { value: e.target.value })}
                disabled={busy}
              />
            </div>
            {!f.fixed && (
              <button className="cfg-del" title="Remove" onClick={() => removeField(i)} disabled={busy}>
                <Trash />
              </button>
            )}
          </div>
        ))}

        <button className="cfg-add" onClick={addField} disabled={busy}>
          <Plus /> Add field
        </button>

        <button className="btn-primary cfg-save" onClick={save} disabled={busy || loading}>
          {status === "saving" && <><span className="spin" /> Saving…</>}
          {status === "restarting" && <><span className="spin" /> Reloading runtime…</>}
          {status === "done" && <>✓ Saved & grounded</>}
          {(status === "" ) && <><Lock /> Save & apply</>}
        </button>
      </div>
    </div>
  );
}
