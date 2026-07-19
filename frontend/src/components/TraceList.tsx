import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentMsg } from "../types";
import { ExternalLink } from "../icons";
import { useTypewriter } from "../useTypewriter";

// Links open in a new tab; tables scroll — same treatment as chat answers.
const MD = {
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

/** Turn a raw tool result (often "HTTP 200 {json}") into readable, pretty-printed text. */
function prettify(text: string): string {
  const s = text.trim();
  const i = s.indexOf("{");
  const j = s.indexOf("[");
  const start = i < 0 ? j : j < 0 ? i : Math.min(i, j);
  if (start >= 0) {
    const head = s.slice(0, start).trim();
    try {
      const obj = JSON.parse(s.slice(start));
      const pretty = JSON.stringify(obj, null, 2);
      const body = pretty.length > 1600 ? pretty.slice(0, 1600) + "\n… (truncated)" : pretty;
      return (head ? head + "\n" : "") + body;
    } catch {
      /* not valid JSON — fall through */
    }
  }
  return s;
}

function isCode(t: AgentMsg): boolean {
  const s = (t.text || "").trim();
  return t.kind === "result" || /^HTTP \d/.test(s) || s.startsWith("{") || s.startsWith("[");
}

function TraceLine({ t, animate }: { t: AgentMsg; animate: boolean }) {
  const code = isCode(t);
  const full = code ? prettify(t.text) : t.text || "";
  const { shown, done } = useTypewriter(full, animate);
  return (
    <div className={"trace-line k-" + (t.kind || "say")}>
      <span className="trace-agent">{t.agent}</span>
      <div className="trace-text">
        {code ? (
          <pre className="trace-code">{shown}</pre>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
            {shown}
          </ReactMarkdown>
        )}
        {animate && !done && <span className="type-caret" aria-hidden="true" />}
      </div>
    </div>
  );
}

/**
 * `animate` (live trace box) types out ONLY the newest line; older ones show in full.
 * `keyBase` is the newest lines' global offset so keys stay stable as the window
 * slides — that keeps completed lines from re-typing when a new one pushes in.
 */
export default function TraceList({
  items,
  animate = false,
  keyBase = 0,
}: {
  items: AgentMsg[];
  animate?: boolean;
  keyBase?: number;
}) {
  const lastIdx = items.length - 1;
  return (
    <div className="trace-list">
      {items.map((t, i) => (
        <TraceLine key={keyBase + i} t={t} animate={animate && i === lastIdx} />
      ))}
    </div>
  );
}
