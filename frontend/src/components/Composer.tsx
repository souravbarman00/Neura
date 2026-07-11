import { useRef } from "react";
import { Folder, Send, Mic, Stop } from "../icons";
import VoiceWave from "./VoiceWave";
import type { OrbState } from "../voice";

interface VoiceState {
  active: boolean;
  state: OrbState;
  analyser: AnalyserNode | null;
  transcript: string;
}

interface Props {
  disabled: boolean;
  placeholder?: string;
  workspace: { path: string; chunks: number } | null;
  voice: VoiceState;
  onSend(text: string): void;
  onAddWorkspace(): void;
  onMic(): void;
  onVoiceAction(): void;
}

const WAVE_COLOR: Record<OrbState, { c: string; g: string }> = {
  idle: { c: "#7c7cf6", g: "#7c7cf6" },
  listening: { c: "#34d399", g: "#059669" },
  thinking: { c: "#a5b4fc", g: "#4f46e5" },
  speaking: { c: "#c084fc", g: "#7c3aed" },
};
const VOICE_LABEL: Record<OrbState, string> = {
  idle: "Tap the mic to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

export default function Composer({
  disabled,
  placeholder = "Message Neura…",
  workspace,
  voice,
  onSend,
  onAddWorkspace,
  onMic,
  onVoiceAction,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function autogrow() {
    const t = ref.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 160) + "px";
  }
  function submit() {
    const t = ref.current;
    if (!t) return;
    const val = t.value.trim();
    if (!val || disabled) return;
    onSend(val);
    t.value = "";
    autogrow();
  }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const wsName = workspace
    ? workspace.path
      ? workspace.path.replace(/\/+$/, "").split("/").pop() || workspace.path
      : "uploaded files"
    : null;

  const busyVoice = voice.state === "listening" || voice.state === "thinking" || voice.state === "speaking";
  const wc = WAVE_COLOR[voice.state];

  return (
    <div className="composer">
      {/* Siri-style voice bar sits ABOVE the composer so the indexed-folder chip
          and text box stay visible while you talk. */}
      {voice.active && (
        <div className="voicebar cbox">
          <div className={"voicebar-wave s-" + voice.state}>
            <VoiceWave analyser={voice.analyser} active={busyVoice} color={wc.c} glow={wc.g} width={260} height={38} />
          </div>
          <div className="voicebar-mid">
            <span className={"voicebar-label s-" + voice.state}>{VOICE_LABEL[voice.state]}</span>
            {voice.transcript && <span className="voicebar-transcript">{voice.transcript}</span>}
          </div>
          <button
            className={"voicebar-act" + (busyVoice ? " stop" : " go")}
            onClick={onVoiceAction}
            title={busyVoice ? "Stop" : "Speak"}
          >
            {busyVoice ? <Stop /> : <Mic />}
          </button>
          <button className="voicebar-close" onClick={onMic} title="Exit voice mode">
            ✕
          </button>
        </div>
      )}
      <div className="cbox">
        <textarea ref={ref} rows={1} placeholder={placeholder} onKeyDown={onKey} onInput={autogrow} />
        <div className="row">
          <button className="ctool" title="Index a folder as this chat's workspace" onClick={onAddWorkspace}>
            <Folder />
          </button>
          {workspace ? (
            <button className="ws-chip" onClick={onAddWorkspace} title={workspace.path || "this chat's workspace"}>
              <Folder />
              <span className="ws-name">{wsName}</span>
              <span className="ws-meta">· {workspace.chunks.toLocaleString()} chunks · this chat</span>
            </button>
          ) : (
            <button className="ws-add" onClick={onAddWorkspace}>+ Index this chat's folder</button>
          )}
          <div className="cgrow" />
          <button className={"ctool mic" + (voice.active ? " on" : "")} title="Talk to Neura" onClick={onMic}>
            <Mic />
          </button>
          <button className="send" disabled={disabled} onClick={submit}>
            <Send />
          </button>
        </div>
      </div>
    </div>
  );
}
