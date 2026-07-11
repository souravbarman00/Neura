import { useEffect, useRef } from "react";

// Blob orb animation ported from neuro-san-app (VoiceWidget/OrbAnimation).
// A harmonic-deformed blob whose colour/amplitude/speed shift with the voice state
// and pulse with live audio (mic while listening, TTS while speaking).
export type OrbState = "idle" | "listening" | "thinking" | "speaking";

interface Props {
  state: OrbState;
  analyser: AnalyserNode | null;
  size?: number;
}

interface OrbConfig {
  inner: string; mid: string; outer: string;
  amplitude: number; speed: number; glow: number;
}

const CFG: Record<OrbState, OrbConfig> = {
  idle:      { inner: "#312e81", mid: "#4338ca", outer: "#818cf8", amplitude: 6,  speed: 0.35, glow: 14 },
  listening: { inner: "#064e3b", mid: "#059669", outer: "#34d399", amplitude: 20, speed: 1.1,  glow: 30 },
  thinking:  { inner: "#1e3a8a", mid: "#4f46e5", outer: "#a5b4fc", amplitude: 10, speed: 0.65, glow: 20 },
  speaking:  { inner: "#4c1d95", mid: "#7c3aed", outer: "#ec4899", amplitude: 26, speed: 1.9,  glow: 40 },
};

const HARMONICS = [
  { n: 2, ph: 0.0, a: 1.0 },
  { n: 3, ph: 1.4, a: 0.7 },
  { n: 4, ph: 2.7, a: 0.45 },
  { n: 5, ph: 0.9, a: 0.28 },
];

function hex(c: string): [number, number, number] {
  const h = c.slice(1);
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function lerpRgb(a: string, b: string, t: number) {
  const [ar, ag, ab] = hex(a), [br, bg, bb] = hex(b);
  return `rgb(${Math.round(ar + (br - ar) * t)},${Math.round(ag + (bg - ag) * t)},${Math.round(ab + (bb - ab) * t)})`;
}
function midPt(a: [number, number], b: [number, number]): [number, number] {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}
function blendedCfg(from: OrbConfig, to: OrbConfig, t: number): OrbConfig {
  const l = (a: number, b: number) => a + (b - a) * t;
  return {
    inner: lerpRgb(from.inner, to.inner, t),
    mid: lerpRgb(from.mid, to.mid, t),
    outer: lerpRgb(from.outer, to.outer, t),
    amplitude: l(from.amplitude, to.amplitude),
    speed: l(from.speed, to.speed),
    glow: l(from.glow, to.glow),
  };
}

export default function VoiceOrb({ state, analyser, size = 240 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const tRef = useRef(0);
  const blendRef = useRef(1);
  const fromCfgRef = useRef<OrbConfig>(CFG[state]);
  const prevState = useRef<OrbState>(state);
  const analyserRef = useRef<AnalyserNode | null>(analyser);
  analyserRef.current = analyser;

  useEffect(() => {
    if (prevState.current !== state) {
      fromCfgRef.current = blendedCfg(fromCfgRef.current, CFG[prevState.current], blendRef.current);
      blendRef.current = 0;
      prevState.current = state;
    }
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const cx = size / 2, cy = size / 2;
    const baseR = size * 0.3;
    const N = 120;
    const freq = new Uint8Array(64);

    const frame = () => {
      tRef.current += 0.016;
      blendRef.current = Math.min(1, blendRef.current + 0.03);
      const t = tRef.current;
      const cfg = blendedCfg(fromCfgRef.current, CFG[prevState.current], blendRef.current);

      // Live audio level → extra amplitude, so the blob reacts to the voice.
      let level = 0;
      const an = analyserRef.current;
      if (an) {
        an.getByteFrequencyData(freq);
        let sum = 0;
        for (let i = 0; i < freq.length; i++) sum += freq[i];
        level = sum / freq.length / 255;
      }
      const amp = cfg.amplitude * (1 + level * 1.6);

      ctx.clearRect(0, 0, size, size);
      const pts: [number, number][] = [];
      for (let i = 0; i < N; i++) {
        const th = (i / N) * Math.PI * 2;
        let r = baseR;
        for (const { n, ph, a } of HARMONICS) {
          r += amp * a * Math.sin(n * th + ph + t * cfg.speed * (0.8 + n * 0.1));
        }
        pts.push([cx + r * Math.cos(th), cy + r * Math.sin(th)]);
      }
      ctx.beginPath();
      let mid = midPt(pts[N - 1], pts[0]);
      ctx.moveTo(mid[0], mid[1]);
      for (let i = 0; i < N; i++) {
        const p = pts[i];
        const pn = pts[(i + 1) % N];
        mid = midPt(p, pn);
        ctx.quadraticCurveTo(p[0], p[1], mid[0], mid[1]);
      }
      ctx.closePath();
      const grad = ctx.createRadialGradient(cx, cy - baseR * 0.15, 0, cx, cy, baseR + amp);
      grad.addColorStop(0, cfg.inner + "ee");
      grad.addColorStop(0.55, cfg.mid);
      grad.addColorStop(1, cfg.outer + "55");
      ctx.shadowBlur = cfg.glow;
      ctx.shadowColor = cfg.mid;
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.shadowBlur = 0;
      rafRef.current = requestAnimationFrame(frame);
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(rafRef.current);
  }, [size]);

  return <canvas ref={canvasRef} style={{ display: "block" }} />;
}
