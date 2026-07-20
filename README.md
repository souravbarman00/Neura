# Neura — Personal AI Assistant

A private, personal AI assistant built on the **neuro-san** multi-agent framework. Chat with
a live view of the agents at work, ground answers in your own local knowledge, edit code, run
commands, browse the web, generate images and documents — from a **web app**, a **VS Code
extension**, or a **terminal CLI**.

- **Knows you** — a local knowledge base (your folders, notes, docs) indexed on your machine.
- **Private by design** — secrets (credentials, PII) travel via neuro-san `sly_data` and are
  **never placed in an LLM prompt**.
- **Yours to run** — clone it, drop in your own API keys / MCP servers / DB creds (no code
  changes), and it's your assistant. Runs on **Windows, macOS, and Linux**.

## Quick start

Get a backend running (agent runtime + API + voice), then use any interface.

**macOS / Linux**
```bash
bash scripts/start_neura.sh
```
**Windows**
```bat
scripts\start_neura.cmd
```

This one command sets up a virtualenv, installs packages (first run only), and starts every
server. Then add an LLM key to `.env` if prompted (`ANTHROPIC_API_KEY=…`, `OPENAI_API_KEY=…`,
or `MISTRAL_API_KEY=…`) and re-run. Open **http://localhost:8010** for the web app.

> The CLI and VS Code extension can **auto-start** the backend for you — see below.

## Three ways to use it

| Interface | Where | Docs |
|---|---|---|
| **Web app** | `http://localhost:8010` (served by the backend) | — |
| **CLI** | `scripts/neura` (POSIX) / `scripts\neura.cmd` (Windows) | [`cli/README.md`](cli/README.md) |
| **VS Code extension** | `vscode-extension/` → build a `.vsix` and install | [`vscode-extension/README.md`](vscode-extension/README.md) |
| **macOS desktop app** | `bash scripts/build_standalone_app.sh` → `Neura.dmg` | — |

The CLI and extension are thin clients over the same backend, so they share conversations,
memory, tools, and per-chat workspace.

## What it can do

- **Chat** with a streaming **live agent trace**, an interactive **agent-network graph**
  (click a node to change that agent's LLM), and a **task checklist** for multi-step jobs.
- **Knowledge / RAG** — semantic search over folders you index (local) plus an "about me"
  store; cites sources.
- **Dev** — read/search/edit/create files and run commands in a workspace; general shell
  (git, `gh`, `az`, `gcloud`); GitHub via MCP; and a headless **browser** (Playwright) to
  **screenshot / record / inspect** web pages.
- **Create** — **image generation** (OpenAI, inline in chat) and **downloadable PDF / PPTX**.
- **Workplace** — Jira, Confluence, Slack, Outlook/Teams (Microsoft Graph).
- **Design** — Figma files, frames, comments.
- **Voice** — Whisper STT + Kokoro TTS.
- **Memory** — durable facts about you + per-task workflow memory.
- **Multi-provider LLM** — Anthropic / OpenAI / Mistral, switchable per network (Settings →
  Model, or `/model` in the CLI) or **per agent** in the graph.

## Stack

| Layer | Choice |
|---|---|
| Orchestration | neuro-san agent network (HOCON registries) |
| LLM | Anthropic Claude / OpenAI / Mistral (switchable) |
| Vector DB | Chroma (local folder, no Docker) |
| Private data channel | neuro-san `sly_data` (kept out of LLM prompts) |
| Image gen | OpenAI images API (`gpt-image-1` / `dall-e-3`) |
| Docs | `python-pptx` (PPTX) + `fpdf2` (PDF) |
| Browser | Playwright (Chromium) |
| Voice | Kokoro TTS + faster-whisper STT |
| Backend | FastAPI proxy to the neuro-san runtime |
| Frontend | Vite + React + TypeScript |

## Layout

```
personal-ai-assistant/
├── registries/neura.hocon      # the Neura agent network (front-man + domain routers)
├── coded_tools/neura/          # tools: knowledge, codebase, shell, browser, image, document, …
├── middleware/                 # checklist, persistent memory, creator signature
├── config/llm_config.hocon     # active LLM (switch in UI → Settings → Model, or /model)
├── backend/app.py              # FastAPI: serves UI, proxies chat (SSE), voice, artifacts
├── frontend/                   # Vite + React + TS app (build → frontend/dist)
├── services/tts/  services/stt/# Kokoro TTS (:8900) + Whisper STT (:8901)
├── cli/                        # terminal client (see cli/README.md)
├── vscode-extension/           # VS Code extension (see its README)
├── scripts/
│   ├── neura_serve.py          # cross-platform launcher (setup + start all servers)
│   ├── start_neura.sh / .cmd   # one-command start (wrappers)
│   ├── neura / neura.cmd        # CLI launchers
│   ├── run_server/ui/tts/stt.sh# individual servers (POSIX)
│   └── build_standalone_app.sh # build the macOS .dmg
└── data/                       # conversations DB, memory, chroma, artifacts (gitignored)
```

## Running the servers individually (POSIX)

```bash
scripts/run_server.sh   # neuro-san runtime            :8099
scripts/run_ui.sh       # UI + API (serves the web app) :8010
scripts/run_tts.sh      # Kokoro TTS (optional)         :8900
scripts/run_stt.sh      # Whisper STT (optional)        :8901
```
On any OS, `python scripts/neura_serve.py` starts them all (add `--no-voice` to skip TTS/STT).

## Add your own knowledge (stays local)

```bash
python scripts/ingest.py ~/Documents ~/notes
```
…or use **Add to knowledge base** in the UI. The CLI/extension also index the folder you're
working in automatically.

## Frontend development

```bash
cd frontend && npm run dev      # :5173, proxies /api → :8010 (hot reload)
cd frontend && npm run build    # production build → dist/
```

## Privacy

Connection strings and secrets are sent through neuro-san `sly_data` and never inlined into an
LLM prompt. Your knowledge base, conversations, and generated artifacts live under `data/`
(gitignored) on your machine.
