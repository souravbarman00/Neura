# Neura for VS Code

Neura — your personal AI assistant — inside VS Code. A **lean webview UI** (chat + a
streaming **live agent trace**, a toggleable **agent-network graph**, and a **task
checklist**) that talks to the Neura backend and points Neura's `dev` agent at the folder
you have open, so it reads and edits those files directly.

Lightweight by design: the extension ships only the UI (~250 KB) — it does **not** bundle
Python, models, or the runtime. It connects to a Neura backend over HTTP (and can start one
for you).

This extension lives inside the Neura repo at [`vscode-extension/`](.).

## Install

Build a `.vsix` (see **Develop** below) or use one you were given, then in VS Code:
**Extensions ⁝ → Install from VSIX…** → pick `neura-vscode-<v>.vsix` → **Developer: Reload
Window**. A **Neura** icon appears in the Activity Bar (drag it to the right Secondary Side
Bar if you prefer it there).

## Use

- Open the **Neura** panel from the Activity Bar, or run **“Neura: Open Chat in Editor Tab”**
  for a roomy view.
- If the backend isn't running, the panel shows a **Start screen** — click **Start Neura** and
  it launches everything in a terminal (see below). A **Help** button explains the one-time
  project-folder pick.
- In the chat header: a **☰ history** drawer of past conversations, and **Graph** / **Checklist**
  toggles (both off by default).
- The folder you have open is passed to Neura automatically (`neura.autoWorkspace`), so `dev`
  edits it directly. Run **“Neura: Index the Open Folder”** to add the semantic index (so it
  can find files by *what they do*, not just by name).

## Start Neura (one click)

**Start Neura** (button on the Start screen, or the command palette) runs the cross-platform
launcher `scripts/neura_serve.py` in a terminal — creating the venv, installing packages
(first run only), and starting all servers. It works on **Windows, macOS, and Linux**. The
first time it asks for your Neura **project folder** (the repo with `scripts/neura_serve.py`);
it also auto-detects the open workspace if that's the repo. Keep the terminal open; **Ctrl-C**
stops Neura. Add an LLM key to the project's `.env` if prompted.

## Settings

| Setting | Default | What |
|---|---|---|
| `neura.backendUrl` | `http://127.0.0.1:8010` | URL of the running Neura backend. |
| `neura.autoWorkspace` | `true` | Point `dev` at the folder you have open. |
| `neura.projectPath` | `""` | Neura repo path for **Start Neura** (asked once if empty). |

## Commands

- **Neura: Open Chat in Editor Tab**
- **Neura: Start Neura (install + run servers)**
- **Neura: Index the Open Folder**
- **Neura: Reload**

## Develop

```bash
# from the repo root: build the lean UI
(cd frontend && npm run build:ext)          # → frontend/dist-ext
# build + package the extension
cd vscode-extension
npm install
npm run sync-ui     # copy frontend/dist-ext → media/   (override with NEURA_DIST=…)
npm run build       # bundle src/extension.ts → out/
# press F5 in VS Code to launch an Extension Development Host
npm run package     # produce neura-vscode-<v>.vsix to share
```

The lean UI is a separate Vite entry (`frontend/ext.html` → `frontend/src/ext/`, built with
`vite.ext.config.ts`), so it stays small and independent of the full web app.

## How it works

The webview loads the prebuilt lean UI from `media/`. The extension rewrites the asset paths
to webview URIs, sets a CSP that allows the UI to fetch/stream from the backend and render
screenshots/fonts, and injects three globals before the bundle loads:

- `window.__NEURA_API_BASE__` — the backend URL (from `neura.backendUrl`),
- `window.__NEURA_WORKSPACE__` — the open folder (when `neura.autoWorkspace`),
- `window.__NEURA_IN_VSCODE__` — so the UI shows the Start screen and messages the extension.

The backend enables CORS for the webview origin. **Start Neura** is handled by the extension
host (spawns the launcher in a VS Code terminal).
