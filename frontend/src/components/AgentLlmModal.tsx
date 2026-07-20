import { useEffect, useMemo, useState } from "react";
import { getLlm, setAgentLlm, type LlmSettings } from "../api";
import type { NodeDetails } from "../studio/graph/layout";

const CUSTOM = "__custom__";

type Status = "" | "saving" | "restarting" | "error";

export default function AgentLlmModal({
  network,
  agent,
  details,
  onClose,
  onSaved,
}: {
  network: string;
  agent: string;
  details?: NodeDetails;
  onClose(): void;
  onSaved(): void;
}) {
  const [data, setData] = useState<LlmSettings | null>(null);
  const inherited = details?.modelInherited !== false; // undefined/true => inheriting
  // "" = inherit network default; a provider id; or CUSTOM (free-type class)
  const [provider, setProvider] = useState<string>(inherited ? "" : details?.provider || "");
  const [model, setModel] = useState<string>(inherited ? "" : details?.model || "");
  const [temp, setTemp] = useState<string>(
    details?.temperature != null ? String(details.temperature) : ""
  );
  // A per-agent class not in the provider list (e.g. azure-openai) is kept here.
  const [customClass, setCustomClass] = useState<string>("");
  const [status, setStatus] = useState<Status>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    getLlm()
      .then((r) => {
        setData(r);
        // If the agent's saved provider is a custom class (not a known provider), reflect it.
        if (!inherited && details?.provider && !r.providers.some((p) => p.id === details.provider)) {
          setProvider(CUSTOM);
          setCustomClass(details.provider);
        }
      })
      .catch(() => setError("Couldn't load the model catalog."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const known = useMemo(
    () => data?.providers?.find((p) => p.id === provider),
    [data, provider]
  );
  const isCustom = provider === CUSTOM;
  const isInherit = provider === "";
  const models = known?.models ?? [];
  const netModel = data?.active?.model || "the network default";
  const busy = status === "saving" || status === "restarting";

  function pickProvider(v: string) {
    setError("");
    if (v === "") {
      setProvider("");
      setModel("");
      return;
    }
    if (v === CUSTOM) {
      setProvider(CUSTOM);
      return;
    }
    setProvider(v);
    const p = data?.providers?.find((x) => x.id === v);
    // snap to that provider's first model unless the current one already belongs to it
    if (!p?.models?.includes(model)) setModel(p?.models?.[0] || "");
  }

  async function save() {
    setError("");
    // provider "" => clear override (inherit). Otherwise model is required.
    const sendProvider = isInherit ? "" : isCustom ? (customClass || "") : provider;
    const sendModel = isInherit ? "" : model.trim();
    if (sendProvider && !sendModel) {
      setError("Choose a model (or pick “Inherit network default”).");
      return;
    }
    setStatus("saving");
    try {
      const t = temp.trim() === "" ? null : Number(temp);
      const r = await setAgentLlm(network, agent, sendProvider, sendModel, t);
      if (r.error) {
        setError(r.error);
        setStatus("error");
        return;
      }
      // runtime restarts — give it a moment, then let the graph reload pick it up
      setStatus("restarting");
      setTimeout(() => {
        onSaved();
        onClose();
      }, 1200);
    } catch {
      setError("Save failed.");
      setStatus("error");
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal agent-llm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">
            Model — <span className="all-agent">{agent}</span>
          </div>
          <button className="modal-x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="modal-sub">
          Pick the LLM that runs this agent. Leave it on <em>Inherit network default</em> to follow
          the network model ({netModel}). Saving reloads the runtime.
        </p>

        {!data && !error && <div className="muted-empty">Loading…</div>}

        {data && (
          <div className="all-form">
            {/* Provider */}
            <label className="all-field">
              <span className="all-label">Provider</span>
              <select
                className="modal-input"
                value={isCustom ? CUSTOM : provider}
                onChange={(e) => pickProvider(e.target.value)}
                disabled={busy}
              >
                <option value="">Inherit network default</option>
                {data.providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                    {p.key_set ? "" : " — no key"}
                  </option>
                ))}
                <option value={CUSTOM}>Other / custom…</option>
              </select>
            </label>

            {/* Custom class */}
            {isCustom && (
              <label className="all-field">
                <span className="all-label">Custom class</span>
                <input
                  className="modal-input mono"
                  value={customClass}
                  onChange={(e) => setCustomClass(e.target.value)}
                  placeholder="azure-openai, ollama, bedrock, or a full python path"
                  disabled={busy}
                />
              </label>
            )}

            {/* Model (hidden when inheriting) */}
            {!isInherit && (
              <label className="all-field">
                <span className="all-label">Model</span>
                <input
                  className="modal-input mono"
                  list="all-model-list"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={`e.g. ${models[0] || netModel}`}
                  disabled={busy}
                />
                <datalist id="all-model-list">
                  {models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </label>
            )}

            {/* Temperature (optional) */}
            {!isInherit && (
              <label className="all-field">
                <span className="all-label">Temperature</span>
                <input
                  className="modal-input mono"
                  type="number"
                  step="0.1"
                  min={0}
                  max={2}
                  value={temp}
                  onChange={(e) => setTemp(e.target.value)}
                  placeholder="inherit (0.2)"
                  disabled={busy}
                />
              </label>
            )}

            {known && !known.key_set && (
              <div className="all-warn">
                No API key saved for {known.label}. Add it in Settings → Model, or this agent will
                fail to run.
              </div>
            )}
            {error && <div className="modal-error">{error}</div>}

            <div className="modal-actions">
              <button className="btn-ghost" onClick={onClose} disabled={busy}>
                Cancel
              </button>
              <button className="btn-primary" onClick={save} disabled={busy}>
                {status === "saving" && <><span className="spin" /> Saving…</>}
                {status === "restarting" && <><span className="spin" /> Reloading…</>}
                {(status === "" || status === "error") &&
                  (isInherit ? "Inherit network default" : "Save & apply")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
