import CommandCard from "./CommandCard";
import DiffCard from "./DiffCard";
import { TraceLine } from "./TraceList";
import type { TurnEvent } from "../types";

// Renders a chronological turn timeline — thinking lines, command cards, and diff cards
// in the exact order they occurred. Used live (during a turn) and on the finished message.
// `animate` type-streams the newest line while it's still arriving (live view only).
export default function Timeline({ events, animate }: { events: TurnEvent[]; animate?: boolean }) {
  const lastIdx = events.length - 1;
  return (
    <div className="timeline">
      {events.map((e, i) => {
        if (e.t === "cmd") {
          return (
            <CommandCard
              key={i}
              cmd={{ command: e.command || "", exit: e.exit ?? 0, output: e.output || "" }}
            />
          );
        }
        if (e.t === "diff") {
          return <DiffCard key={i} fc={{ path: e.path || "", diff: e.diff || "", kind: e.changeKind }} />;
        }
        return (
          <TraceLine
            key={i}
            t={{ agent: e.agent || "agent", text: e.text || "", kind: e.kind }}
            animate={!!animate && i === lastIdx}
          />
        );
      })}
    </div>
  );
}
