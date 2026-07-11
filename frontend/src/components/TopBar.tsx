import { Menu, Lock, Cloud, Panel, Graph, Eye, Focus, Reset } from "../icons";
import type { WatchStatus } from "../api";

type Mode = "strict" | "assist";

interface Props {
  title: string;
  subtitle: string;
  runtimeOk: boolean;
  model: string;
  mode: Mode;
  showDial: boolean;
  hasWorkspace: boolean;
  watch: WatchStatus | null;
  onToggleWatch(): void;
  onMode(m: Mode): void;
  onShowNetwork(): void;
  onOpenSidebar(): void;
  onOpenRight(): void;
  rightCollapsed?: boolean;
  focus?: boolean;
  onToggleFocus(): void;
  canReset?: boolean;
  onResetContext(): void;
}

export default function TopBar({
  title,
  subtitle,
  runtimeOk,
  model,
  mode,
  showDial,
  hasWorkspace,
  watch,
  onToggleWatch,
  onMode,
  onShowNetwork,
  onOpenSidebar,
  onOpenRight,
  rightCollapsed,
  focus,
  onToggleFocus,
  canReset,
  onResetContext,
}: Props) {
  const watching = !!watch?.watching;
  const reindexing = !!watch?.reindexing;
  const watchLabel = watching ? (reindexing ? "Re-indexing…" : "Watching") : "Watch files";
  const watchTitle = watching
    ? `Watching this chat's workspace — auto re-indexing on change${
        watch?.last_event ? ` (last: ${watch.last_event.name})` : ""
      }. Click to stop.`
    : "Watch this chat's folder and re-index automatically as you edit";
  return (
    <div className="topbar">
      <button
        className={"hamburger" + (focus ? "" : " only-mobile")}
        onClick={onOpenSidebar}
        title="Menu"
      >
        <Menu />
      </button>
      <div className="title">
        {title}
        <small>{runtimeOk ? subtitle : "Server offline — start scripts/run_server.sh"}</small>
      </div>
      <div className="grow" />

      {showDial && (
        <div className="dial hide-sm" title="Strict = answer only from your data. Assist = your data + general knowledge.">
          <button className={mode === "strict" ? "on" : ""} onClick={() => onMode("strict")}>
            <Lock className="lock" />
            Strict
          </button>
          <button className={mode === "assist" ? "on" : ""} onClick={() => onMode("assist")}>
            <Cloud className="cloud" />
            Assist
          </button>
        </div>
      )}

      {hasWorkspace && (
        <button
          className={"watchbtn" + (watching ? " on" : "") + (reindexing ? " busy" : "")}
          onClick={onToggleWatch}
          title={watchTitle}
        >
          <Eye />
          <span className="hide-sm">{watchLabel}</span>
        </button>
      )}

      {canReset && (
        <button className="iconbtn" onClick={onResetContext} title="Reset this chat's context (keeps messages) — fresh start if it has drifted">
          <Reset />
        </button>
      )}

      <button className="iconbtn" onClick={onShowNetwork} title="Show/hide the agent graph">
        <Graph />
      </button>

      <button
        className={"iconbtn" + (focus ? " on" : "")}
        onClick={onToggleFocus}
        title={focus ? "Exit focus mode" : "Focus mode — hide panels, chat + graph side by side"}
      >
        <Focus />
      </button>

      <div className="chip hide-sm">
        <span className={"g" + (runtimeOk ? "" : " off")} />
        {model}
      </div>

      <button
        className={"iconbtn" + (rightCollapsed ? "" : " on")}
        onClick={onOpenRight}
        title={rightCollapsed ? "Show details panel" : "Hide details panel"}
      >
        <Panel />
      </button>
    </div>
  );
}
