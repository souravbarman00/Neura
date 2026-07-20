import { useEffect, useRef } from "react";
import type { AgentMsg, CommandRun, Message as Msg } from "../types";
import Message from "./Message";
import TraceList from "./TraceList";
import CommandCard from "./CommandCard";

interface Props {
  messages: Msg[];
  activity: string | null;
  liveTrace?: AgentMsg[];
  liveCommands?: CommandRun[];
  busy?: boolean;
  onQuick(q: string): void;
  onBuild(desc: string): void;
  onApprove?(decision: "yes" | "no" | "always"): void;
  autoApprove?: boolean;
  onRevertAuto?(): void;
  animatingId?: string | null;
  userInitials?: string;
  imagePending?: boolean;
}

const SUGGESTIONS = ["What is Neuro SAN?", "Summarize my projects", "How are coded tools defined?"];

export default function Thread({ messages, activity, liveTrace, liveCommands, busy, onQuick, onBuild, onApprove, autoApprove, onRevertAuto, animatingId, userInitials, imagePending }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activity, liveTrace, liveCommands]);

  // Keep the live-trace box pinned to its newest line — including WHILE a line types
  // out (content grows without a liveTrace change), via a ResizeObserver on the body.
  const traceBoxRef = useRef<HTMLDivElement>(null);
  const traceContentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = traceBoxRef.current;
    const content = traceContentRef.current;
    if (!box || !content) return;
    const stick = () => {
      box.scrollTop = box.scrollHeight;
    };
    stick();
    const ro = new ResizeObserver(stick);
    ro.observe(content);
    return () => ro.disconnect();
  }, [liveTrace, activity]);

  // Show a deeper window in the (now taller) box; keyBase keeps line keys stable.
  const traceShown = (liveTrace || []).slice(-12);
  const traceKeyBase = Math.max(0, (liveTrace?.length || 0) - traceShown.length);

  if (messages.length === 0) {
    return (
      <div className="thread">
        <div className="empty">
          <div className="bigorb" />
          <h2>Hi, I'm Neura.</h2>
          <p>
            Your private AI. Ask me about your work, notes, and projects — I answer from your own
            locally-indexed knowledge.
          </p>
          <div className="suggest">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => onQuick(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="thread">
      {messages.map((m, i) => (
        <Message
          key={m.id}
          msg={m}
          onBuild={onBuild}
          last={i === messages.length - 1}
          busy={busy}
          onApprove={onApprove}
          onQuick={onQuick}
          animate={!!animatingId && m.id === animatingId}
          userInitials={userInitials}
        />
      ))}
      {liveCommands && liveCommands.length > 0 && (
        <div className="live-commands">
          {liveCommands.map((c, i) => (
            <CommandCard key={i} cmd={c} />
          ))}
        </div>
      )}
      {activity && (
        <div className="thinking">
          <div className="thinking-head">
            <div className="spin" />
            <span>{activity}</span>
          </div>
          {liveTrace && liveTrace.length > 0 && (
            <div className="thinking-box">
              <div className="thinking-box-head">
                <span className="tbh-dot" /> Agents working — live trace
              </div>
              <div className="thinking-box-body" ref={traceBoxRef}>
                <div ref={traceContentRef}>
                  <TraceList items={traceShown} animate keyBase={traceKeyBase} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      {imagePending && (
        <div className="img-gen">
          <div className="img-gen-skel" />
          <div className="img-gen-cap">✨ Generating image…</div>
        </div>
      )}
      {autoApprove && (
        <div className="auto-approve-note">
          <span>⚡ Auto-approving actions for the rest of this chat.</span>
          <button className="auto-approve-undo" onClick={() => onRevertAuto?.()}>
            Turn off · ask me each time
          </button>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
