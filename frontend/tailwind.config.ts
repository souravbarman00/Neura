import type { Config } from "tailwindcss";

// ALIVE Tailwind preset (ported). Colors resolve to CSS vars in src/theme/tokens.css.
// preflight is DISABLED so Tailwind only adds utilities and does not reset our
// existing plain-CSS UI.
const withAlpha = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        canvas: withAlpha("--alive-bg-canvas"),
        panel: withAlpha("--alive-bg-panel"),
        elevated: withAlpha("--alive-bg-elevated"),
        field: withAlpha("--alive-bg-input"),
        hover: withAlpha("--alive-bg-hover"),
        line: {
          subtle: withAlpha("--alive-line-subtle"),
          strong: withAlpha("--alive-line-strong"),
        },
        fg: {
          DEFAULT: withAlpha("--alive-text-primary"),
          soft: withAlpha("--alive-text-secondary"),
          muted: withAlpha("--alive-text-muted"),
          inverse: withAlpha("--alive-text-inverse"),
        },
        accent: {
          DEFAULT: withAlpha("--alive-accent"),
          hover: withAlpha("--alive-accent-hover"),
          contrast: withAlpha("--alive-accent-contrast"),
        },
        node: {
          frontman: withAlpha("--alive-node-frontman"),
          agent: withAlpha("--alive-node-agent"),
          tool: withAlpha("--alive-node-tool"),
          external: withAlpha("--alive-node-external"),
          subnetwork: withAlpha("--alive-node-subnetwork"),
        },
        success: withAlpha("--alive-success"),
        warning: withAlpha("--alive-warning"),
        danger: withAlpha("--alive-danger"),
      },
      borderRadius: {
        sm: "var(--alive-radius-sm)",
        md: "var(--alive-radius-md)",
        lg: "var(--alive-radius-lg)",
        xl: "var(--alive-radius-xl)",
        "2xl": "var(--alive-radius-2xl)",
      },
      fontFamily: { sans: "var(--alive-font-sans)", mono: "var(--alive-font-mono)" },
      boxShadow: {
        "alive-sm": "var(--alive-shadow-sm)",
        "alive-md": "var(--alive-shadow-md)",
        "alive-lg": "var(--alive-shadow-lg)",
      },
    },
  },
  plugins: [],
} satisfies Config;
