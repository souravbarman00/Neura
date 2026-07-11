import { useEffect, useState } from "react";

/** Minimal shim of alive's useAliveTheme — reports the current light/dark mode
 *  (driven by the `data-theme` attribute our app sets on <html>). */
export function useAliveTheme(): { mode: "light" | "dark" } {
  const read = (): "light" | "dark" =>
    (document.documentElement.dataset.theme as "light" | "dark") || "dark";
  const [mode, setMode] = useState<"light" | "dark">(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setMode(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return { mode };
}
