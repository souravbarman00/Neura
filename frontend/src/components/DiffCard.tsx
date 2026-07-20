import { useState } from "react";
import type { FileChange } from "../types";
import { ChevronDown } from "../icons";

// A GitHub-style diff card for a file the codebase agent edited/created — filename header,
// added/removed counts, old/new line-number gutters, and colored +/- lines. Collapsible.
const KIND_LABEL: Record<string, string> = { edit: "edited", create: "created", overwrite: "overwrote" };

interface Row {
  cls: string;
  oldNo: string;
  newNo: string;
  text: string;
}

function toRows(diff: string): Row[] {
  const rows: Row[] = [];
  let oldNo = 0;
  let newNo = 0;
  for (const l of (diff || "").split("\n")) {
    const hunk = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunk) {
      oldNo = parseInt(hunk[1], 10);
      newNo = parseInt(hunk[2], 10);
      rows.push({ cls: "diff-hunk", oldNo: "", newNo: "", text: l });
    } else if (l.startsWith("+")) {
      rows.push({ cls: "diff-add", oldNo: "", newNo: String(newNo++), text: l });
    } else if (l.startsWith("-")) {
      rows.push({ cls: "diff-del", oldNo: String(oldNo++), newNo: "", text: l });
    } else {
      rows.push({ cls: "diff-ctx", oldNo: String(oldNo++), newNo: String(newNo++), text: l || " " });
    }
  }
  return rows;
}

export default function DiffCard({ fc }: { fc: FileChange }) {
  const [open, setOpen] = useState(true);
  const rows = toRows(fc.diff);
  const added = rows.filter((r) => r.cls === "diff-add").length;
  const removed = rows.filter((r) => r.cls === "diff-del").length;
  const name = fc.path.split(/[/\\]/).pop() || fc.path;

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
        <div className="diff-body">
          {rows.map((r, i) => (
            <div key={i} className={"diff-line " + r.cls}>
              <span className="diff-ln">{r.oldNo}</span>
              <span className="diff-ln">{r.newNo}</span>
              <span className="diff-code">{r.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
