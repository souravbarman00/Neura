import { useEffect, useMemo, useState } from "react";
import { getLlm, saveLlm, fetchHealth, type LlmSettings, type LlmProvider } from "../api";
import { Lock } from "../icons";

type Status = "" | "saving" | "restarting" | "done" | "error";

export default function ModelPanel() {
  const [data, setData] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState<string>("anthropic");
  const [model, setModel] = useState<string>("");
  const [apiKey, setApiKey] = useState<string>("");
  const [status, setStatus] = useState<Status>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    getLlm()
      .then((r) => {
        if (!r || !Array.isArray(r.providers) || r.providers.length === 0) {
          setError(
            "Couldn't load model settings. Restart the Neura UI backend so the new /api/llm endpoint is available."
          );
          return;
        }
        setData(r);
        setProvider(r.active?.provider || r.providers[0].id);
        setModel(r.active?.model || "");
      })
      .catch(() =>
        setError(
          "Couldn't load model settings. Restart the Neura UI backend so the new /api/llm endpoint is available."
        )
      );
  }, []);

  const cur: LlmProvider | undefined = useMemo(
    () => data?.providers?.find((p) => p.id === provider),
    [data, provider]
  );

  function pickProvider(id: string) {
    setProvider(id);
    setApiKey("");
    setError("");
    const p = data?.providers?.find((x) => x.id === id);
    // keep the active model if we're returning to the active provider, else default to first
    const activeSame = data?.active?.provider === id && data?.active?.model;
    setModel(activeSame ? (data!.active.model as string) : p?.models?.[0] || "");
  }

  const busy = status === "saving" || status === "restarting";
  const isActive =
    data?.active?.provider === provider && data?.active?.model === model;

  async function save() {
    if (!cur || !model) return;
    setError("");
    setStatus("saving");
    try {
      const r = await saveLlm(provider, model, apiKey || undefined);
      if (r.error) {
        setError(r.error);
        setStatus("error");
        return;
      }
      setStatus("restarting");
      for (let i = 0; i < 15; i++) {
        await new Promise((res) => setTimeout(res, 2000));
        try {
          const h = await fetchHealth();
          if (h.runtime) break;
        } catch {
          /* keep polling */
        }
      }
      // refresh so key_set / active reflect the new state
      try {
        const fresh = await getLlm();
        setData(fresh);
      } catch {
        /* ignore */
      }
      setApiKey("");
      setStatus("done");
      setTimeout(() => setStatus(""), 2500);
    } catch {
      setError("Save failed.");
      setStatus("error");
    }
  }

  return (
    <div>
      <div className="rhead">
        <h3>Model</h3>
        <span className="badge">provider</span>
      </div>
      <div className="card">
        <p className="cfg-intro">
          Choose which LLM powers Neura and enter that provider's API key. The key is stored
          locally in <code>.env</code> (never uploaded); the runtime reloads so the new model
          takes effect.
        </p>

        {!data && !error && <div className="muted-empty">Loading…</div>}
        {error && status !== "error" && <div className="muted-empty">{error}</div>}

        {data?.providers && (
          <>
            {/* Provider selector */}
            <div className="mp-providers">
              {data.providers.map((p) => (
                <button
                  key={p.id}
                  className={"mp-prov" + (p.id === provider ? " on" : "")}
                  onClick={() => pickProvider(p.id)}
                  disabled={busy}
                >
                  <span className="mp-prov-label">{p.label}</span>
                  <span className={"mp-keydot" + (p.key_set ? " set" : "")}>
                    {p.key_set ? "key saved" : "no key"}
                  </span>
                  {data.active?.provider === p.id && <span className="mp-active">● active</span>}
                </button>
              ))}
            </div>

            {/* Model dropdown */}
            <label className="mp-row">
              <span className="mp-row-label">Model</span>
              <select
                className="modal-input"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={busy}
              >
                {(cur?.models || []).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                {model && !(cur?.models || []).includes(model) && (
                  <option value={model}>{model} (custom)</option>
                )}
              </select>
            </label>

            {/* API key */}
            <label className="mp-row">
              <span className="mp-row-label">{cur?.env_key}</span>
              <div className="cfg-valwrap">
                <Lock className="cfg-lock" />
                <input
                  className="cfg-input"
                  type="password"
                  placeholder={cur?.key_set ? "•••••••••• saved — type to replace" : "paste API key…"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={busy}
                />
              </div>
            </label>

            {status === "error" && error && <div className="mp-error">{error}</div>}

            <button
              className="btn-primary cfg-save"
              onClick={save}
              disabled={busy || !model || (!cur?.key_set && !apiKey)}
            >
              {status === "saving" && <><span className="spin" /> Saving…</>}
              {status === "restarting" && <><span className="spin" /> Reloading runtime…</>}
              {status === "done" && <>✓ Applied</>}
              {(status === "" || status === "error") && (
                <>
                  <Lock /> {isActive && cur?.key_set && !apiKey ? "Already active" : "Save & apply"}
                </>
              )}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
