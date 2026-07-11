import type { CommandRun } from "../types";

// A terminal-style card for a shell command Neura ran (via the codebase agent) —
// the command line + its output + exit status, like Claude Code shows bash.
export default function CommandCard({ cmd, running }: { cmd: CommandRun; running?: boolean }) {
  const failed = !running && cmd.exit !== 0;
  return (
    <div className={"cmd-card" + (failed ? " failed" : "") + (running ? " running" : "")}>
      <div className="cmd-head">
        <span className="cmd-dots"><i /><i /><i /></span>
        <span className="cmd-prompt">$</span>
        <span className="cmd-line">{cmd.command}</span>
        <span className="cmd-status">
          {running ? <span className="cmd-spin" /> : `exit ${cmd.exit}`}
        </span>
      </div>
      {cmd.output && cmd.output !== "(no output)" && (
        <pre className="cmd-output">{cmd.output}</pre>
      )}
    </div>
  );
}
