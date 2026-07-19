import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useRef, useState } from "react";
import { useTypewriter } from "../useTypewriter";
import type { Message as Msg } from "../types";
import { Speaker, Stop, Wand, ExternalLink, ChevronDown } from "../icons";
import { speak, type Speaker as VoiceSpeaker } from "../voice";
import { speechify } from "../api";
import { parseChoices } from "../choices";
import TraceList from "./TraceList";
import CommandCard from "./CommandCard";

// Rich, modern renderers: links open in a new tab (with an external-link icon),
// tables scroll horizontally on overflow.
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

export function isApprovalText(t: string): boolean {
  return /shall i proceed|\(\s*yes\s*\/\s*no\s*\)/i.test(t || "");
}

export default function Message({
  msg,
  onBuild,
  last,
  busy,
  onApprove,
  onQuick,
  animate,
  userInitials,
}: {
  msg: Msg;
  onBuild?(desc: string): void;
  last?: boolean;
  busy?: boolean;
  onApprove?(decision: "yes" | "no" | "always"): void;
  onQuick?(text: string): void;
  animate?: boolean;
  userInitials?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const speakerRef = useRef<VoiceSpeaker | null>(null);
  const wantRef = useRef(false);
  const isAI = msg.role === "ai";
  const trace = msg.trace || [];
  const commands = msg.commands || [];
  // Type-out the in-flight answer (this message only); everything else is instant.
  const { shown, done } = useTypewriter(msg.text, !!animate && isAI);
  const showApproval = isAI && !!last && !busy && done && !!onApprove && isApprovalText(msg.text);
  // A general multiple-choice question → clickable options so the user can answer
  // with a tap instead of typing. Yes/no approvals are handled above, so skip them.
  // Held back until the type-out finishes so buttons don't flash mid-reveal.
  const choices =
    isAI && !!last && !busy && done && !!onQuick && !isApprovalText(msg.text)
      ? parseChoices(msg.text)
      : [];

  async function togglePlay() {
    if (playing) {
      wantRef.current = false;
      speakerRef.current?.stop();
      speakerRef.current = null;
      setPlaying(false);
      return;
    }
    wantRef.current = true;
    setPlaying(true);
    // Rewrite into a short, natural spoken version, then play chunked via Kokoro.
    const spoken = await speechify(msg.text);
    if (!wantRef.current) return; // stopped while preparing
    speakerRef.current = speak(spoken, {
      onDone: () => {
        wantRef.current = false;
        setPlaying(false);
      },
    });
  }

  return (
    <div className={"msg " + (isAI ? "ai" : "user")}>
      <div className="av">{isAI ? "" : userInitials || "Me"}</div>
      <div className="col">
        {isAI && trace.length > 0 && (
          <div className={"trace-disclosure" + (showTrace ? " open" : "")}>
            <button className="trace-toggle" onClick={() => setShowTrace((v) => !v)}>
              <ChevronDown className="trace-chev" />
              {showTrace ? "Hide" : "Show"} agent trace
              <span className="trace-count">{trace.length}</span>
            </button>
            {showTrace && (
              <div className="trace-body">
                <TraceList items={trace} />
              </div>
            )}
          </div>
        )}
        {isAI && commands.length > 0 && (
          <div className="msg-commands">
            {commands.map((c, i) => (
              <CommandCard key={i} cmd={c} />
            ))}
          </div>
        )}
        <div className="bubble">
          {isAI ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
              {shown}
            </ReactMarkdown>
          ) : (
            msg.text
          )}
          {isAI && !done && <span className="type-caret" aria-hidden="true" />}
        </div>
        {showApproval && (
          <div className="approval">
            <button className="ap-btn ap-yes" onClick={() => onApprove!("yes")}>Yes</button>
            <button className="ap-btn ap-no" onClick={() => onApprove!("no")}>No</button>
            <button className="ap-btn ap-always" onClick={() => onApprove!("always")}>
              Always allow (this chat)
            </button>
          </div>
        )}
        {choices.length >= 2 && (
          <div className="choices">
            {choices.map((c) => (
              <button key={c} className="choice-btn" onClick={() => onQuick!(c)}>
                {c}
              </button>
            ))}
          </div>
        )}
        {isAI && done && msg.build && onBuild && (
          <button className="build-cta" onClick={() => onBuild(msg.build!)}>
            <Wand />
            Build an agent for this
          </button>
        )}
        {isAI && done && msg.text && (
          <button className={"speak" + (playing ? " on" : "")} onClick={togglePlay}>
            {playing ? <Stop /> : <Speaker />}
            {playing ? "Stop" : "Play"}
          </button>
        )}
      </div>
    </div>
  );
}
