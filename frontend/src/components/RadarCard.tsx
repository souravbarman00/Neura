import type { CSSProperties } from "react";
import type { RadarItem } from "../api";
import { hue, dot } from "./radarColors";

/** A single research-paper card — modern, subtle: hue-keyed accent dot + soft hover
 *  glow, clear hierarchy, and an "Open" affordance that reveals on hover. */
export default function RadarCard({ item, onOpen }: { item: RadarItem; onOpen(): void }) {
  const isTry = item.action === "try";
  const showSkill = !!item.skill && item.skill.toLowerCase() !== item.area.toLowerCase();
  return (
    <button
      className="radar-card"
      onClick={onOpen}
      style={{ "--rc-hue": hue(item.id) } as CSSProperties}
    >
      <div className="radar-card-top">
        <span className="radar-chip">
          <span className="radar-dot" style={{ background: dot(item.id) }} />
          {item.area}
        </span>
        <span className={"radar-tag " + (isTry ? "try" : "read")}>{isTry ? "Try" : "Read"}</span>
      </div>
      <div className="radar-card-title">{item.title}</div>
      <div className="radar-card-summary">{item.summary || item.abstract.slice(0, 180)}</div>
      <div className="radar-card-foot">
        <span className="radar-skill">{showSkill ? item.skill : item.published}</span>
        <span className="radar-open">
          Open <span className="radar-arrow">→</span>
        </span>
      </div>
    </button>
  );
}
