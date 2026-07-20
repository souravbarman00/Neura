# Neura for VS Code

Neura — your personal AI assistant — inside VS Code. It reuses the full Neura chat UI
in a webview: chat, streaming **live agent trace**, the **agent-network graph**, and the
**task checklist**. It points Neura's `dev` agent at the folder you have open, so it can
read and edit those files directly.

The extension is **lightweight**: it's just the UI. It talks to a running **Neura backend**
(the FastAPI server) over HTTP — it does not bundle Python, models, or the runtime.

## Requirements

A running Neura backend. From the Neura repo:

```bash
bash scripts/run_server.sh   # neuro-san runtime  (:8099)
bash scripts/run_ui.sh       # UI backend/API     (:8010)
# optional: run_tts.sh / run_stt.sh for voice
```

…or launch the Neura desktop app. Then set **`neura.backendUrl`** if it isn't the default
`http://127.0.0.1:8010`.

## Use

- Click the **Neura** icon in the Activity Bar for the chat in the side panel, or run
  **“Neura: Open Chat in Editor Tab”** for a roomy view (better for the graph).
- The folder you have open is passed to Neura automatically (`neura.autoWorkspace`), so
  `dev` edits it directly — no manual "Add to knowledge base".
- Run **“Neura: Index the Open Folder”** to build the semantic index (so Neura can locate
  files by *what they do*, not just by name).

## Settings

| Setting | Default | What |
|---|---|---|
| `neura.backendUrl` | `http://127.0.0.1:8010` | URL of the running Neura backend. |
| `neura.autoWorkspace` | `true` | Point `dev` at the open folder. |

## Develop

This extension lives in the Neura repo at `vscode-extension/`. From there:

```bash
# 1. build the lean UI (from the repo root)
(cd ../frontend && npm run build:ext)
# 2. build + package the extension
cd ../vscode-extension
npm install
npm run sync-ui     # copy frontend/dist-ext → media/  (override with NEURA_DIST=…)
npm run build       # bundle the extension
# press F5 in VS Code to launch an Extension Development Host
npm run package     # produce neura-vscode-<v>.vsix to share
```

## How it works

The webview loads the prebuilt Neura React app from `media/`. The extension injects the
backend base URL (`window.__NEURA_API_BASE__`) and the open folder
(`window.__NEURA_WORKSPACE__`), and sets a CSP that allows the UI to fetch/stream from the
backend and render screenshots. The backend enables CORS for the webview origin.
