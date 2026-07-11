import {
  BaseEdge,
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
  Position,
  useInternalNode,
  useStore,
  type EdgeProps,
  type InternalNode,
} from "@xyflow/react";

function borderPoint(node: InternalNode, toX: number, toY: number) {
  const w = node.measured?.width ?? 260;
  const h = node.measured?.height ?? 90;
  const x = node.internals.positionAbsolute.x;
  const y = node.internals.positionAbsolute.y;
  const cx = x + w / 2;
  const cy = y + h / 2;
  const dx = toX - cx;
  const dy = toY - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy };
  const scale = Math.min(
    dx !== 0 ? w / 2 / Math.abs(dx) : Infinity,
    dy !== 0 ? h / 2 / Math.abs(dy) : Infinity,
  );
  return { x: cx + dx * scale, y: cy + dy * scale };
}

function faceOf(node: InternalNode, toX: number, toY: number): { x: number; y: number; pos: Position } {
  const w = node.measured?.width ?? 260;
  const h = node.measured?.height ?? 90;
  const cx = node.internals.positionAbsolute.x + w / 2;
  const cy = node.internals.positionAbsolute.y + h / 2;
  const dx = toX - cx;
  const dy = toY - cy;
  if (Math.abs(dx) > Math.abs(dy)) {
    return dx > 0
      ? { x: cx + w / 2, y: cy, pos: Position.Right }
      : { x: cx - w / 2, y: cy, pos: Position.Left };
  }
  return dy > 0
    ? { x: cx, y: cy + h / 2, pos: Position.Bottom }
    : { x: cx, y: cy - h / 2, pos: Position.Top };
}

export function GlowEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const floating = data?.curve === "float" || data?.curve === "floatCurve";
  const curvedFloat = data?.curve === "floatCurve";
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  const zoom = useStore((s) => s.transform[2]) || 1;

  const active = !!data?.active;
  const reverse = !!data?.reverse;
  const lit = active || reverse;
  const dimmed = !!data?.dimmed && !lit;
  const color = reverse ? "rgb(52 211 153)" : active ? "rgb(251 191 36)" : "rgb(var(--alive-accent))";
  const flowId = `flow-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;

  let path: string;
  let motionPath: string;
  if (floating && sourceNode && targetNode) {
    const sc = {
      x: sourceNode.internals.positionAbsolute.x + (sourceNode.measured?.width ?? 260) / 2,
      y: sourceNode.internals.positionAbsolute.y + (sourceNode.measured?.height ?? 90) / 2,
    };
    const tc = {
      x: targetNode.internals.positionAbsolute.x + (targetNode.measured?.width ?? 260) / 2,
      y: targetNode.internals.positionAbsolute.y + (targetNode.measured?.height ?? 90) / 2,
    };
    if (curvedFloat) {
      const sf = faceOf(sourceNode, tc.x, tc.y);
      const tf = faceOf(targetNode, sc.x, sc.y);
      const bez = { sourceX: sf.x, sourceY: sf.y, sourcePosition: sf.pos, targetX: tf.x, targetY: tf.y, targetPosition: tf.pos };
      [path] = getBezierPath(bez);
      if (reverse) {
        [motionPath] = getBezierPath({
          sourceX: tf.x, sourceY: tf.y, sourcePosition: tf.pos,
          targetX: sf.x, targetY: sf.y, targetPosition: sf.pos,
        });
      } else {
        motionPath = path;
      }
    } else {
      const sp = borderPoint(sourceNode, tc.x, tc.y);
      const tp = borderPoint(targetNode, sc.x, sc.y);
      [path] = getStraightPath({ sourceX: sp.x, sourceY: sp.y, targetX: tp.x, targetY: tp.y });
      if (reverse) {
        [motionPath] = getStraightPath({ sourceX: tp.x, sourceY: tp.y, targetX: sp.x, targetY: sp.y });
      } else {
        motionPath = path;
      }
    }
  } else {
    const params = { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition };
    const curve = data?.curve === "step" ? getSmoothStepPath : getBezierPath;
    [path] = curve(params);
    if (reverse) {
      [motionPath] = curve({
        sourceX: targetX,
        sourceY: targetY,
        targetX: sourceX,
        targetY: sourceY,
        sourcePosition: targetPosition,
        targetPosition: sourcePosition,
      });
    } else {
      motionPath = path;
    }
  }

  return (
    <>
      <path
        d={path}
        fill="none"
        strokeLinecap="round"
        stroke={color}
        strokeWidth={lit ? 9 : 5}
        strokeOpacity={lit ? 0.6 : dimmed ? 0.04 : 0.2}
        style={{ filter: `blur(${lit ? 4 : 2.5}px)`, pointerEvents: "none" }}
      />
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className={reverse ? "alive-edge-flow-rev" : active ? "alive-edge-flow" : undefined}
        style={{ stroke: color, strokeWidth: lit ? 2.75 : 1.75, opacity: lit ? 1 : dimmed ? 0.06 : 0.85 }}
      />
      {lit &&
        (() => {
          const k = Math.min(Math.max(1 / zoom, 1), 11);
          const tip = 12 * k;
          const back = -7 * k;
          const wing = 8 * k;
          const points = `${tip},0 ${back},${-wing} ${back},${wing}`;
          return (
            <>
              <path id={flowId} d={motionPath} fill="none" stroke="none" style={{ pointerEvents: "none" }} />
              <polygon points={points} fill={color} style={{ pointerEvents: "none" }}>
                <animateMotion dur="1.1s" repeatCount="indefinite" rotate="auto">
                  <mpath href={`#${flowId}`} />
                </animateMotion>
              </polygon>
            </>
          );
        })()}
    </>
  );
}
