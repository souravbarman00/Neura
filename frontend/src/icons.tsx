// Small stroke-based icon set (inherits currentColor via the `stroke` CSS on parents).
type P = { className?: string };
const base = { fill: "none", strokeWidth: 2, viewBox: "0 0 24 24" } as const;

export const Plus = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M12 5v14M5 12h14" /></svg>
);
export const Doc = (p: P) => (
  <svg {...base} className={p.className}><path d="M4 4h16v16H4z" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>
);
export const File = (p: P) => (
  <svg {...base} className={p.className}><path d="M4 4h16v16H4z" /></svg>
);
export const Shield = (p: P) => (
  <svg {...base} className={p.className}><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" /></svg>
);
export const Lock = (p: P) => (
  <svg {...base} className={p.className}><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></svg>
);
export const Cloud = (p: P) => (
  <svg {...base} className={p.className}><path d="M6 18a4 4 0 010-8 5 5 0 019.6-1.5A3.5 3.5 0 0118 18z" /></svg>
);
export const Sun = (p: P) => (
  <svg {...base} className={p.className}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" /></svg>
);
export const Menu = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M4 6h16M4 12h16M4 18h16" /></svg>
);
export const Close = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const Send = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const Clip = (p: P) => (
  <svg {...base} className={p.className}><path d="M21 12.5l-8 8a5 5 0 01-7-7l8-8a3 3 0 014 4l-8 8a1 1 0 01-1.5-1.5l7-7" /></svg>
);
export const Speaker = (p: P) => (
  <svg {...base} className={p.className}><path d="M11 5L6 9H2v6h4l5 4V5z" /><path d="M15.5 8.5a5 5 0 010 7" /></svg>
);
export const Panel = (p: P) => (
  <svg {...base} className={p.className}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></svg>
);
export const Clock = (p: P) => (
  <svg {...base} className={p.className}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /></svg>
);
export const Trash = (p: P) => (
  <svg {...base} className={p.className}><path d="M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2M6 7l1 13a1 1 0 001 1h8a1 1 0 001-1l1-13" /></svg>
);
export const Chat = (p: P) => (
  <svg {...base} className={p.className}><path d="M4 5h16v11H8l-4 4z" /></svg>
);
export const Wand = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M5 19l9-9M14 6l1.5-1.5M18 10l1.5-1.5M14.5 5.5L13 4M19.5 10.5L18 9M15 8l1 1" /></svg>
);
export const Bot = (p: P) => (
  <svg {...base} className={p.className}><rect x="4" y="8" width="16" height="11" rx="2" /><path d="M12 8V4M9 13h.01M15 13h.01" /></svg>
);
export const Home = (p: P) => (
  <svg {...base} className={p.className}><path d="M4 11l8-7 8 7M6 10v9h12v-9" /></svg>
);
export const Folder = (p: P) => (
  <svg {...base} className={p.className}><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
);
export const ArrowUp = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M12 19V5M6 11l6-6 6 6" /></svg>
);
export const ChevronRight = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><path d="M9 6l6 6-6 6" /></svg>
);
export const ExternalLink = (p: P) => (
  <svg {...base} strokeLinecap="round" strokeLinejoin="round" className={p.className}><path d="M14 5h5v5M19 5l-8 8M12 5H7a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-5" /></svg>
);
export const Graph = (p: P) => (
  <svg {...base} className={p.className}><circle cx="6" cy="6" r="2.4" /><circle cx="6" cy="18" r="2.4" /><circle cx="18" cy="12" r="2.4" /><path d="M8.1 7.1l7.8 3.8M8.1 16.9l7.8-3.8" /></svg>
);
export const Files = (p: P) => (
  <svg {...base} strokeLinejoin="round" className={p.className}><path d="M13 3H6a1 1 0 00-1 1v16a1 1 0 001 1h12a1 1 0 001-1V9z" /><path d="M13 3v6h6" /></svg>
);
export const Branch = (p: P) => (
  <svg {...base} strokeLinecap="round" className={p.className}><circle cx="6" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="8" r="2.5" /><path d="M6 8.5v7M18 10.5c0 3-3 3.5-6 4" /></svg>
);
export const Reset = (p: P) => (
  <svg {...base} strokeLinecap="round" strokeLinejoin="round" className={p.className}><path d="M3 12a9 9 0 109-9 9 9 0 00-7 3.3M4 3v4h4" /></svg>
);
export const Focus = (p: P) => (
  <svg {...base} strokeLinecap="round" strokeLinejoin="round" className={p.className}><path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3" /></svg>
);
export const Mic = (p: P) => (
  <svg {...base} strokeLinecap="round" strokeLinejoin="round" className={p.className}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></svg>
);
export const Stop = (p: P) => (
  <svg {...base} className={p.className}><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>
);
export const ChevronDown = (p: P) => (
  <svg {...base} strokeLinecap="round" strokeLinejoin="round" className={p.className}><path d="M6 9l6 6 6-6" /></svg>
);
export const Eye = (p: P) => (
  <svg {...base} className={p.className}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="3" /></svg>
);
