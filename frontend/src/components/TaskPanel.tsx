import type { ChecklistItem } from "../api";

const AGENT_LABEL: Record<string, string> = {
  jira: "Jira",
  github: "GitHub",
  codebase: "Codebase",
  slack: "Slack",
  outlook: "Outlook",
  teams: "Teams",
  figma: "Figma",
  knowledge_search: "Knowledge",
};

const SYMBOL: Record<ChecklistItem["status"], string> = {
  pending: "○",
  in_progress: "◐",
  done: "✓",
  skipped: "–",
};

/** Live "Task Plan" panel — appears for multi-step / complex jobs (driven by the
 *  checklist middleware). Each step is listed, crossed off as it completes, and
 *  badged with the sub-agent responsible for it. */
export default function TaskPanel({
  items,
  progress,
}: {
  items: ChecklistItem[];
  progress: number | null;
}) {
  if (!items.length) return null;
  const done = items.filter((i) => i.status === "done" || i.status === "skipped").length;
  const pct = progress != null ? Math.round(progress * 100) : Math.round((done / items.length) * 100);
  const running = items.some((i) => i.status === "in_progress");

  return (
    <div className="taskpanel">
      <div className="rhead tp-head">
        <h3>Task Plan</h3>
        <span className={"tp-count" + (running ? " live" : "")}>
          {done}/{items.length}
        </span>
      </div>
      <div className="tp-bar">
        <div className="tp-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="card tp-list">
        {items.map((it, i) => (
          <div key={i} className={"tp-item s-" + it.status}>
            <span className="tp-sym">{SYMBOL[it.status]}</span>
            <div className="tp-body">
              <div className="tp-text">{it.item}</div>
              {it.notes && <div className="tp-notes">{it.notes}</div>}
            </div>
            {it.agent && AGENT_LABEL[it.agent] && (
              <span className={"tp-agent a-" + it.agent}>{AGENT_LABEL[it.agent]}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
