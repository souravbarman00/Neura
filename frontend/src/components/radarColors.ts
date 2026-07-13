// Per-paper hue derived from the id — used subtly (a small accent dot, a faint
// header wash, a soft hover glow), never as a saturated fill.
export function hue(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

export function dot(id: string): string {
  return `hsl(${hue(id)} 45% 55%)`;
}

// Tasteful low-saturation header tint — soft pastel in light, charcoal in dark.
export function banner(id: string, theme: "light" | "dark"): string {
  const h = hue(id);
  const h2 = (h + 40) % 360;
  return theme === "light"
    ? `linear-gradient(135deg, hsl(${h} 52% 95%), hsl(${h2} 48% 92%))`
    : `linear-gradient(135deg, hsl(${h} 22% 17%), hsl(${h2} 18% 12%))`;
}
