import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentMsg } from "../types";
import { ExternalLink } from "../icons";

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

export default function TraceList({ items }: { items: AgentMsg[] }) {
  return (
    <div className="trace-list">
      {items.map((t, i) => (
        <div className={"trace-line k-" + (t.kind || "say")} key={i}>
          <span className="trace-agent">{t.agent}</span>
          <div className="trace-text">
            {isCode(t) ? (
              <pre className="trace-code">{prettify(t.text)}</pre>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
                {t.text}
              </ReactMarkdown>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
