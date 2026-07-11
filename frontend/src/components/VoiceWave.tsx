import { useEffect, useRef } from "react";

// Siri-like symmetric bar wave (ported from neuro-san-app VoiceWidget/VoiceWave).
// Reacts to a live AnalyserNode; breathes gently when the mic is quiet.
interface Props {
  analyser: AnalyserNode | null;
  active: boolean;
  color: string;
  glow: string;
  width?: number;
  height?: number;
}

const BARS = 48;

export default function VoiceWave({ analyser, active, color, glow, width = 240, height = 40 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const tRef = useRef(0);
  const heights = useRef(new Float32Array(BARS));
  const propsRef = useRef({ analyser, active, color, glow });
  propsRef.current = { analyser, active, color, glow };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);

    const gap = 2.5;
    const barW = (width - gap * (BARS - 1)) / BARS;
    const cy = height / 2;

    const frame = () => {
      tRef.current += 0.016;
      const t = tRef.current;
      const { analyser: a, active: on, color: c, glow: g } = propsRef.current;
      ctx.clearRect(0, 0, width, height);

      const buf = a ? new Uint8Array(a.frequencyBinCount) : null;
      if (a && buf) a.getByteFrequencyData(buf);

      for (let i = 0; i < BARS; i++) {
        let target: number;
        if (on) {
          if (buf && buf.length > 0) {
            const half = BARS / 2;
            const mi = i >= half ? BARS - 1 - i : i;
            const idx = Math.floor((mi / BARS) * buf.length * 0.85);
            target = buf[idx] / 255;
          } else {
            target = 0.18 + 0.14 * Math.sin(t * 3.2 + i * 0.22);
          }
        } else {
          target = 0;
        }
        const k = target > heights.current[i] ? 0.38 : 0.14;
        heights.current[i] += (target - heights.current[i]) * k;

        const v = heights.current[i];
        const bh = Math.max(1.5, v * (cy - 2));
        const x = i * (barW + gap);
        ctx.beginPath();
        (ctx as any).roundRect(x, cy - bh, barW, bh * 2, barW / 2);
        const alpha = Math.round((0.5 + v * 0.5) * 255).toString(16).padStart(2, "0");
        ctx.fillStyle = c + alpha;
        ctx.shadowBlur = 5 + v * 16;
        ctx.shadowColor = g;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      rafRef.current = requestAnimationFrame(frame);
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(rafRef.current);
  }, [width, height]);

  return <canvas ref={canvasRef} style={{ display: "block" }} />;
}
