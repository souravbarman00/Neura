# Neura CLI

A polished terminal client for Neura — chat with your assistant, watch the live agent
trace, and let it read/edit the folder you're in. It's a thin client over the Neura
backend, so it shares the same agents, tools, memory, and conversations as the web app
and the VS Code extension.

```
╭───────────────────────────────── by Sourav Jyoti Barman ─╮
│  ◇ Neura                                                   │
│  your private personal AI assistant                        │
│                                                            │
│  backend  ● up  http://127.0.0.1:8010                      │
│    model  claude-opus-4-5  (anthropic)                     │
│  network  neura                                            │
│   folder  /Users/you/my-project                            │
│                                                            │
│  /help all  /model switch LLM  /new reset  Esc stop  /exit │
╰────────────────────────────────────────────────────────────╯
❯
```

---

## 1. Prerequisites

- **macOS or Linux**, **Python 3.10+**, **Bash**.
- An **LLM API key** (Anthropic, OpenAI, or Mistral).
- Optional but recommended: [`uv`](https://github.com/astral-tool/uv) (faster installs).
  If `uv` isn't present the scripts fall back to `pip`.
- You already have the **`personal-ai-assistant`** folder.

## 2. Get it running (fastest path)

From inside the project folder:

```bash
cd personal-ai-assistant
./scripts/neura
```

The first time, if no backend is running, the CLI **auto-starts one** — it runs
`scripts/start_neura.sh`, which:

1. creates the `.venv` if missing,
2. installs all Python packages (first run only; cached afterwards),
3. starts the Neura servers,

then drops you into the chat. Startup output goes to a log; the CLI waits until the
agent runtime is ready. When you exit, a backend the CLI started is **stopped
automatically**.

> First run installs packages and can take a few minutes. Later runs are fast.

## 3. Add an API key

The backend needs a key in the project's `.env` (created from `.env.example` on first
run). Add **one** of:

```
ANTHROPIC_API_KEY=sk-ant-…
OPENAI_API_KEY=sk-…
MISTRAL_API_KEY=…
```

`OPENAI_API_KEY` is also what image generation uses. You can switch models later from
inside the CLI with **`/model`**.

## 4. Run `neura` from anywhere (optional)

Put the launcher on your `PATH` so you can type `neura` in any project:

```bash
# pick a dir already on your PATH (e.g. ~/.local/bin)
ln -s "$(pwd)/scripts/neura" ~/.local/bin/neura
# then, in any project:
cd ~/some-project && neura
```

The launcher resolves the symlink back to the project, so it still finds the code and
venv. **The folder you run it in becomes Neura's workspace** — its `dev` agent reads and
edits the files there.

---

## Usage

```bash
neura                         # interactive session in the current folder
neura "add tests for parser"  # one-shot: answer and exit
neura --verbose               # -v: show the full agent trace
neura --network research_radar
neura --url http://127.0.0.1:8010   # point at a specific backend
neura --workspace /path/to/repo     # override the working folder (default: cwd)
neura --no-serve              # require a running backend (don't auto-start one)
```

### In-session commands

| Command | Action |
|---|---|
| `/model` | Switch the LLM (interactive), or `/model gpt-5.4`, or `/model openai gpt-5.4` |
| `/new` | Start a fresh conversation |
| `/clear` | Clear the screen |
| `/help` | Show commands |
| `/exit` | Quit (`Ctrl-D` also works) |
| **Esc** | Interrupt the current reply |

While Neura works you'll see a live **spinner**, the **agent trace** (`↳ agent: …`),
**command cards** (`$ cmd` + output), and the answer rendered as **Markdown**. Generated
images/files are shown as openable links.

---

## How it connects (and the "runs in your shell" bit)

- If a backend is already running (web app, desktop app, or `start_neura.sh`), the CLI
  just uses it and leaves it alone.
- If not, and the URL is local, the CLI **spawns the backend using your current shell's
  environment** — so the commands Neura's `dev` agent runs inherit **your** `PATH`,
  activated venv, `nvm` node, `gh`/`az` logins, etc. It's torn down when you quit.
- Point at a remote backend with `--url`; the CLI won't try to auto-start that.

Default ports: UI/API `:8010`, agent runtime `:8099` (TTS `:8900`, STT `:8901`). Override
via env (`NEURA_UI_PORT`, `NEURA_HTTP_PORT`, …) before launching.

---

## Troubleshooting

- **`zsh: command not found: neura`** — the symlink isn't on your `PATH`. Use
  `./scripts/neura` from the project, or symlink into a `PATH` dir (step 4), then open a
  new terminal or run `hash -r`.
- **"backend not reachable" / `--no-serve`** — start it: `bash scripts/start_neura.sh`,
  or drop `--no-serve` to auto-start.
- **"backend failed to start"** — the CLI prints the last log lines and the full log path.
  Usually a missing API key or a port already in use.
- **No API key** — add one to `.env` (step 3), then run again or use `/model`.
- **Answer says a model is "not valid"** — pick a model from the `/model` list for that
  provider.
- **Colors/animation missing** — that's expected when output is piped/redirected; it's a
  full TUI in an interactive terminal.
