# Personal AI Assistant

A private, personal AI assistant built on the **neuro-san** multi-agent framework, with a
professional web UI, local knowledge about you, and optional voice.

## Vision
- **Knows you** — a local knowledge base (your folders, notes, docs) indexed on your machine.
- **Private by design** — sensitive data (credentials, PII) travels via neuro-san `sly_data`
  and is **never placed in an LLM prompt**. Only the knowledge you allow is used to compose answers.
- **Reusable** — others clone this, drop in their own MCP servers, API keys, and DB creds
  (no code changes) and it's their assistant.

## Stack (decided)
| Layer | Choice |
|---|---|
| Orchestration | neuro-san agent network (HOCON) |
| LLM | **Anthropic Claude** (cloud) |
| Embeddings | TBD — OpenAI `text-embedding-3-small` or local sentence-transformers |
| Vector DB | **Chroma** (local folder, no Docker) |
| Private data channel | neuro-san **`sly_data`** (kept out of LLM prompts) |
| Voice | **Kokoro** TTS (24 kHz, local) |
| Backend | FastAPI proxy to neuro-san runtime (pattern borrowed from `alive`) |
| Frontend | **Vite + React + TypeScript**, componentized, fully responsive (desktop/tablet/mobile) |

## Status
- [x] Research: neuro-san capabilities, alive's vector-DB + MCP + backend/UI patterns, Kokoro
- [ ] **Figma design of the UI (in progress — design first)**
- [ ] Stage 1: private brain (network + local KB)
- [ ] Stage 2: Kokoro voice service
- [ ] Stage 3: professional UI
- [ ] Stage 4: privacy dial

## Layout
```
personal-ai-assistant/
├── registries/neura.hocon   # the Neura agent network
├── coded_tools/neura/       # local knowledge base (Chroma) + kb_search tool
├── config/llm_config.hocon  # Claude Sonnet 4.5
├── scripts/                 # ingest.py, run_server.sh, run_ui.sh
├── backend/app.py           # FastAPI: serves UI, proxies chat (SSE) + voice
├── frontend/                # Vite + React + TS app (build → frontend/dist)
├── data/chroma/             # local vector store (gitignored)
└── design/                  # Figma exports / screenshots
```

## Running Neura
```bash
# 1. Runtime (agent network) — :8099
scripts/run_server.sh

# 2. Voice (optional) — :8900
/Users/2504436/tts-tool/run.sh

# 3. UI backend (serves the built React app) — :8010
scripts/run_ui.sh
# → open http://localhost:8010

# Add your own knowledge (stays local):
python scripts/ingest.py ~/Documents ~/notes

# Frontend development (hot reload, proxies /api → :8010):
cd frontend && npm run dev      # :5173
cd frontend && npm run build    # production build → dist/
```
