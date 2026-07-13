import type { CSSProperties } from "react";
import type { RadarItem } from "../api";
import { hue } from "./radarColors";

/* Small monochrome glyphs (use currentColor so we can tint per category). */
const g = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, width: 18, height: 18, viewBox: "0 0 24 24" };
const Nodes = () => (<svg {...g}><circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="7" r="2.2" /><circle cx="12" cy="18" r="2.2" /><path d="M7.6 7.4 10.4 16M16.6 8.6 13.2 16.4M8 6.4h8" /></svg>);
const Layers = () => (<svg {...g}><path d="M12 3 21 8l-9 5-9-5 9-5Z" /><path d="M3 13l9 5 9-5" /></svg>);
const Search = () => (<svg {...g}><circle cx="11" cy="11" r="6" /><path d="m20 20-3.2-3.2" /></svg>);
const Spark = () => (<svg {...g}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" /><circle cx="12" cy="12" r="2.4" /></svg>);
const Doc = () => (<svg {...g}><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4M10 12h5M10 16h5" /></svg>);

function areaGlyph(area: string) {
  const a = area.toLowerCase();
  if (a.includes("multi-agent")) return <Nodes />;
  if (a.includes("orchestration") || a.includes("agentic") || a.includes("framework")) return <Layers />;
  if (a.includes("retrieval") || a.includes("rag")) return <Search />;
  if (a.includes("reasoning") || a.includes("tool")) return <Spark />;
  return <Doc />;
}

/** A single research-paper card — modern: tinted category icon badge, faint hue
 *  wash, soft hover glow, and an "Open →" affordance that reveals on hover. */
export default function RadarCard({ item, onOpen }: { item: RadarItem; onOpen(): void }) {
  const isTry = item.action === "try";
  const showSkill = !!item.skill && item.skill.toLowerCase() !== item.area.toLowerCase();
  return (
    <button className="radar-card" onClick={onOpen} style={{ "--rc-hue": hue(item.id) } as CSSProperties}>
      <div className="radar-head">
        <span className="radar-icon">{areaGlyph(item.area)}</span>
        <span className="radar-headtext">
          <span className="radar-cat">{item.area}</span>
          <span className="radar-hdate">{item.published}</span>
        </span>
        <span className={"radar-tag " + (isTry ? "try" : "read")}>{isTry ? "Try" : "Read"}</span>
      </div>
      <div className="radar-card-title">{item.title}</div>
      <div className="radar-card-summary">{item.summary || item.abstract.slice(0, 200)}</div>
      <div className="radar-card-foot">
        <span className="radar-skill">{showSkill ? item.skill : "arXiv"}</span>
        <span className="radar-open">Open <span className="radar-arrow">→</span></span>
      </div>
    </button>
  );
}
