import CommandCard from "./CommandCard";
import DiffCard from "./DiffCard";
import type { TurnEvent } from "../types";

// Renders a chronological turn timeline — thinking lines, command cards, and diff cards
// in the exact order they occurred. Used live (during a turn) and on the finished message.
export default function Timeline({ events }: { events: TurnEvent[] }) {
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
          <div key={i} className="tl-trace">
            <span className="tl-agent">↳ {e.agent || "agent"}</span> {e.text}
          </div>
        );
      })}
    </div>
  );
}
