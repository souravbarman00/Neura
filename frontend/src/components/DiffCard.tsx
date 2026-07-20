import { useState } from "react";
import type { FileChange } from "../types";
import { ChevronDown } from "../icons";

// A GitHub-style diff card for a file the codebase agent edited/created — filename header,
// added/removed line counts, and colored +/- lines. Collapsible; long diffs scroll.
const KIND_LABEL: Record<string, string> = { edit: "edited", create: "created", overwrite: "overwrote" };

export default function DiffCard({ fc }: { fc: FileChange }) {
  const [open, setOpen] = useState(true);
  const lines = (fc.diff || "").split("\n");
  const added = lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
  const removed = lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
  const name = fc.path.split(/[/\\]/).pop() || fc.path;

  function lineClass(l: string): string {
    if (l.startsWith("@@")) return "diff-hunk";
    if (l.startsWith("+")) return "diff-add";
    if (l.startsWith("-")) return "diff-del";
    return "diff-ctx";
  }

  return (
    <div className="diff-card">
      <button className="diff-head" onClick={() => setOpen((v) => !v)}>
        <ChevronDown className={"diff-chev" + (open ? " open" : "")} />
        <span className="diff-kind">{KIND_LABEL[fc.kind || ""] || "changed"}</span>
        <span className="diff-file" title={fc.path}>{name}</span>
        <span className="diff-path">{fc.path}</span>
        <span className="diff-stat">
          {added > 0 && <span className="diff-plus">+{added}</span>}
          {removed > 0 && <span className="diff-minus">−{removed}</span>}
        </span>
      </button>
      {open && (
        <pre className="diff-body">
          {lines.map((l, i) => (
            <div key={i} className={"diff-line " + lineClass(l)}>
              {l || " "}
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}
