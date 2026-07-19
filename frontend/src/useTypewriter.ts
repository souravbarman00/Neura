import { useEffect, useRef, useState } from "react";

// Cosmetic "typewriter" reveal. neuro-san streams whole MESSAGES (not tokens), so we
// animate the visible slice client-side for a ChatGPT-like type-out.
//
// Time-based (framerate-independent) at BASE_CPS characters/second so the pace is
// visible and consistent; very long messages speed up just enough that they never
// take longer than MAX_SECONDS. It also CHASES a growing `text`, so if a message
// streams in chunks the reveal keeps pace. `done` flips true once fully shown.
//
// Tune the feel here: lower BASE_CPS = slower typing.
const BASE_CPS = 45;
const MAX_SECONDS = 7;

export function useTypewriter(text: string, animate: boolean): { shown: string; done: boolean } {
  const [count, setCount] = useState(() => (animate ? 0 : text.length));
  const countRef = useRef(count);
  countRef.current = count;
  const rafRef = useRef(0);
  const lastRef = useRef(0);

  useEffect(() => {
    if (!animate) {
      setCount(text.length);
      return;
    }
    let cancelled = false;
    lastRef.current = 0;
    const cps = Math.max(BASE_CPS, text.length / MAX_SECONDS);
    const step = (now: number) => {
      if (cancelled) return;
      if (!lastRef.current) lastRef.current = now;
      const dt = now - lastRef.current;
      lastRef.current = now;
      const total = text.length;
      const inc = Math.max(1, Math.round((cps * dt) / 1000));
      const next = Math.min(total, countRef.current + inc);
      if (next !== countRef.current) setCount(next);
      if (next < total) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
    };
  }, [text, animate]);

  return { shown: animate ? text.slice(0, count) : text, done: !animate || count >= text.length };
}
