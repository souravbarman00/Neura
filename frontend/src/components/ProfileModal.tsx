import { useEffect, useState } from "react";
import { getProfile, saveProfile, type ProfileField } from "../api";
import { Close, Shield } from "../icons";
import NetworkConfigPanel from "./NetworkConfigPanel";
import MemoryPanel from "./MemoryPanel";
import ModelPanel from "./ModelPanel";

interface Props {
  open: boolean;
  network: string;
  onClose(): void;
  onSaved(profile: Record<string, string>): void;
}

// Fields that read better as a multi-line textarea.
const LONG = new Set(["focus", "communication_style", "about"]);
// Neutral example hints only — the real values are whatever the user types (saved
// per-user in their own database). Nothing here is anyone's actual profile.
const PLACEHOLDER: Record<string, string> = {
  name: "e.g. Jane Doe",
  role: "e.g. Software Engineer",
  company: "e.g. Acme Inc.",
  team: "e.g. Platform",
  location: "e.g. San Francisco, CA",
  timezone: "e.g. PST (UTC-8)",
  working_hours: "e.g. 09:00–17:00",
  focus: "What you're currently working on.",
  communication_style: "e.g. Direct and concise. Show code and links. Skip preamble.",
  about: "Anything Neura should always keep in mind about you, your projects, or how you work.",
};

export default function ProfileModal({ open, network, onClose, onSaved }: Props) {
  const [tab, setTab] = useState<"profile" | "model" | "memory" | "connections">("profile");
  const [fields, setFields] = useState<ProfileField[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const t = new URLSearchParams(location.search).get("tab");
    setTab(
      t === "memory" || t === "connections" || t === "model" ? t : "profile"
    );
    getProfile()
      .then((r) => {
        setFields(r.fields || []);
        setValues(r.profile || {});
      })
      .catch(() => {});
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      const r = await saveProfile(values);
      onSaved(r.profile || values);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal profile-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">Settings</div>
          <button className="modal-x" onClick={onClose}>
            <Close />
          </button>
        </div>

        <div className="settings-tabs">
          <button className={tab === "profile" ? "on" : ""} onClick={() => setTab("profile")}>
            Profile
          </button>
          <button className={tab === "model" ? "on" : ""} onClick={() => setTab("model")}>
            Model
          </button>
          <button className={tab === "memory" ? "on" : ""} onClick={() => setTab("memory")}>
            Memory
          </button>
          <button className={tab === "connections" ? "on" : ""} onClick={() => setTab("connections")}>
            Connections
          </button>
        </div>

        {tab === "profile" ? (
          <>
            <p className="modal-sub">
              Neura keeps these details and remembers them in every conversation, so you never have to
              reintroduce yourself. Stored locally in your own database — never uploaded.
            </p>
            <div className="profile-form">
              {fields.map((f) => (
                <label className={"pf-field" + (LONG.has(f.key) ? " wide" : "")} key={f.key}>
                  <span className="pf-label">{f.label}</span>
                  {LONG.has(f.key) ? (
                    <textarea
                      className="modal-input"
                      rows={f.key === "about" ? 3 : 2}
                      placeholder={PLACEHOLDER[f.key] || ""}
                      value={values[f.key] || ""}
                      onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                    />
                  ) : (
                    <input
                      className="modal-input"
                      placeholder={PLACEHOLDER[f.key] || ""}
                      value={values[f.key] || ""}
                      onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                    />
                  )}
                </label>
              ))}
            </div>
            <div className="pf-privacy">
              <Shield /> Saved on-device · used to personalize Neura, not shared
            </div>
            <div className="modal-actions">
              <button className="btn-ghost" onClick={onClose} disabled={saving}>
                Cancel
              </button>
              <button className="btn-primary" onClick={save} disabled={saving}>
                {saving ? <><span className="spin" /> Saving…</> : "Save profile"}
              </button>
            </div>
          </>
        ) : tab === "model" ? (
          <div className="settings-connections">
            <ModelPanel />
          </div>
        ) : tab === "memory" ? (
          <div className="settings-connections">
            <MemoryPanel />
          </div>
        ) : (
          <div className="settings-connections">
            <NetworkConfigPanel network={network} />
          </div>
        )}
      </div>
    </div>
  );
}
