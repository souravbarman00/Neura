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
}

const SUGGESTIONS = ["What is Neuro SAN?", "Summarize my projects", "How are coded tools defined?"];

export default function Thread({ messages, activity, liveTrace, liveCommands, busy, onQuick, onBuild, onApprove }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activity, liveTrace, liveCommands]);

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
              <TraceList items={liveTrace.slice(-6)} />
            </div>
          )}
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
