import { useEffect, useRef, useState } from "react";
import { listNetworks, spawnNetwork } from "../api";
import { Wand, Close } from "../icons";

interface Props {
  open: boolean;
  initialDescription?: string;
  onClose(): void;
  onOpenNetwork(name: string): void;
  onCreated(): void;
}

type Phase = "idle" | "building" | "done" | "error";

export default function BuildAgentModal({ open, initialDescription, onClose, onOpenNetwork, onCreated }: Props) {
  const [desc, setDesc] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [created, setCreated] = useState<{ name: string; title: string } | null>(null);
  const [servable, setServable] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setDesc(initialDescription || "");
      setPhase("idle");
      setCreated(null);
      setServable(false);
      setError("");
      setTimeout(() => ref.current?.focus(), 50);
    }
  }, [open]);

  async function build() {
    const d = desc.trim();
    if (!d || phase === "building") return;
    setPhase("building");
    setError("");
    try {
      const res = await spawnNetwork(d);
      if (res.status === "created" && res.networks?.length) {
        const net = res.networks[0];
        setCreated(net);
        setPhase("done");
        // Poll until the runtime is actually serving it, then enable "Open".
        for (let i = 0; i < 12; i++) {
          const nets = await listNetworks();
          if (nets.some((n) => n.name === net.name)) {
            setServable(true);
            onCreated();
            break;
          }
          await new Promise((r) => setTimeout(r, 3000));
        }
      } else {
        setError(res.message || res.error || "The designer couldn't build that. Try rephrasing.");
        setPhase("error");
      }
    } catch (e: any) {
      setError(String(e?.message || e));
      setPhase("error");
    }
  }

  if (!open) return null;

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">
            <Wand className="wand" />
            Build a new agent network
          </div>
          <button className="modal-x" onClick={onClose}><Close /></button>
        </div>

        {phase !== "done" && (
          <>
            <p className="modal-sub">
              Describe what this agent should do. The network designer will design a multi-agent
              network, save it, and serve it live. Any credentials it needs are read from your
              <code>.env</code>.
            </p>
            <textarea
              ref={ref}
              className="modal-input"
              rows={4}
              placeholder="e.g. A GitHub assistant that lists my open issues and drafts replies. Or: a meeting-notes summarizer that extracts action items with owners."
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              disabled={phase === "building"}
            />
            {phase === "error" && <div className="modal-error">⚠️ {error}</div>}
            <div className="modal-actions">
              <button className="btn-ghost" onClick={onClose} disabled={phase === "building"}>
                Cancel
              </button>
              <button className="btn-primary" onClick={build} disabled={!desc.trim() || phase === "building"}>
                {phase === "building" ? (
                  <>
                    <span className="spin" /> Designing… (~1–2 min)
                  </>
                ) : (
                  <>
                    <Wand /> Build agent
                  </>
                )}
              </button>
            </div>
          </>
        )}

        {phase === "done" && created && (
          <div className="modal-done">
            <div className="done-badge">✓</div>
            <h3>{created.title}</h3>
            <p className="modal-sub">
              {servable
                ? "Your agent network is live and ready to talk to."
                : "Created — waiting for the runtime to serve it…"}
            </p>
            <div className="modal-actions center">
              <button className="btn-ghost" onClick={onClose}>Close</button>
              <button
                className="btn-primary"
                disabled={!servable}
                onClick={() => {
                  onOpenNetwork(created.name);
                  onClose();
                }}
              >
                {servable ? "Open" : <><span className="spin" /> Preparing…</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
