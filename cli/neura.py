#!/usr/bin/env python3
"""Neura CLI — a polished terminal interface for your Neura assistant.

Thin client over the running Neura backend's /api/chat SSE stream, so it reuses the same
agents, tools, memory, and per-chat workspace as the web UI and the VS Code extension.
The directory you run it in becomes the chat's workspace, so `dev` reads/edits files here.
If no backend is running it can auto-start one in THIS shell's environment (and stop it on exit).

Usage:
  neura                      # interactive session in the current folder
  neura "refactor utils.py"  # one-shot
  neura --network research_radar  --url http://127.0.0.1:8010  --no-serve  --verbose
Session commands: /new  /help  /exit
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import httpx
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.markdown import Markdown
    from rich.live import Live
    from rich import box
except Exception as exc:  # noqa: BLE001
    sys.stderr.write(f"neura: missing dependency ({exc}); need 'httpx' and 'rich'.\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0"
ACCENT = "#7c7cf6"
console = Console()
_started: subprocess.Popen | None = None  # backend we launched (torn down on exit)


# ----------------------------------------------------------------- backend helpers
def health(url: str) -> bool:
    """True only when the API AND the agent runtime (neuro-san) are up."""
    try:
        r = httpx.get(f"{url}/api/health", timeout=4)
        if r.status_code != 200:
            return False
        try:
            return bool(r.json().get("runtime", True))
        except Exception:  # noqa: BLE001
            return True
    except Exception:  # noqa: BLE001
        return False


def active_model(url: str) -> str:
    try:
        a = httpx.get(f"{url}/api/llm", timeout=4).json().get("active", {})
        m, p = a.get("model"), a.get("provider")
        return f"{m}  ({p})" if m else (p or "—")
    except Exception:  # noqa: BLE001
        return "—"


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in ("127.0.0.1", "localhost", "0.0.0.0", "::1")


def _teardown() -> None:
    global _started
    if _started and _started.poll() is None:
        try:
            os.killpg(os.getpgid(_started.pid), signal.SIGTERM)
        except Exception:  # noqa: BLE001
            try:
                _started.terminate()
            except Exception:  # noqa: BLE001
                pass
    _started = None


def ensure_backend(url: str, serve: bool, timeout: float = 300.0) -> bool:
    """Reachable? Auto-start it (in this shell's env) if not and serve=True. A backend we
    launch is stopped on exit; one already running is left alone."""
    global _started
    if health(url):
        return True
    if not serve:
        return False
    if not _is_local(url):
        console.print(f"[red]neura:[/] nothing at {url} and it's not local — can't auto-start.")
        return False
    script = ROOT / "scripts" / "start_neura.sh"
    if not script.exists():
        console.print(f"[red]neura:[/] {script} not found — can't auto-start.")
        return False

    logf = tempfile.NamedTemporaryFile(prefix="neura-cli-", suffix=".log", delete=False)
    _started = subprocess.Popen(
        ["bash", str(script)], cwd=str(ROOT), env=dict(os.environ),
        stdout=logf, stderr=subprocess.STDOUT, start_new_session=True,
    )
    atexit.register(_teardown)
    for s in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(s, lambda *_a: (_teardown(), sys.exit(0)))
        except Exception:  # noqa: BLE001
            pass

    start = time.monotonic()
    with console.status("[dim]Starting Neura in this shell… (first run installs packages)[/]",
                        spinner="dots"):
        while time.monotonic() - start < timeout:
            if _started.poll() is not None:
                break
            if health(url):
                console.print(f"[green]●[/] backend up [dim]({int(time.monotonic() - start)}s)[/]")
                return True
            time.sleep(0.5)

    console.print("[red]neura: backend failed to start.[/] Last log lines:")
    try:
        tail = Path(logf.name).read_text(errors="replace").splitlines()[-20:]
        console.print("[dim]" + "\n".join("  " + ln for ln in tail) + f"\n  (full log: {logf.name})[/]")
    except Exception:  # noqa: BLE001
        pass
    _teardown()
    return False


# ----------------------------------------------------------------- UI
def welcome(url: str, network: str, workspace: str, up: bool) -> None:
    logo = Text("◇ Neura", style=f"bold {ACCENT}")
    tag = Text("your private personal AI assistant", style="dim italic")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()
    status = Text("● up", style="green") if up else Text("● down", style="red")
    grid.add_row("backend", Text.assemble(status, "  ", Text(url, style="dim")))
    grid.add_row("model", Text(active_model(url) if up else "—"))
    grid.add_row("network", Text(network, style=ACCENT))
    grid.add_row("folder", Text(workspace, style="dim"))

    tips = Text.assemble(
        ("  /help", ACCENT), (" all   ", "dim"),
        ("/model", ACCENT), (" switch LLM   ", "dim"),
        ("/new", ACCENT), (" reset   ", "dim"),
        ("Esc", ACCENT), (" stop   ", "dim"),
        ("/exit", ACCENT), (" quit", "dim"),
    )
    body = Group(logo, tag, Text(""), grid, Text(""), tips)
    console.print(Panel(body, box=box.ROUNDED, border_style=ACCENT, padding=(1, 2),
                        title="[dim]by Sourav Jyoti Barman[/]", title_align="right"))


def artifacts(url: str, answer: str) -> None:
    seen: list[str] = []
    for m in re.findall(r"/artifacts/[A-Za-z0-9._\-]+", answer or ""):
        if m not in seen:
            seen.append(m)
    for path in seen:
        kind = "🖼 image" if path.endswith((".png", ".webp", ".jpg", ".webm", ".mp4")) else "📄 file"
        console.print(f"  [cyan]{kind}[/] [dim]{url}{path}[/]")


class EscWatcher:
    """While a turn streams, watch stdin for Esc and abort the response (like Claude Code).
    No-op when stdin isn't a TTY. Ctrl-C still works via KeyboardInterrupt."""

    def __init__(self, resp, event: threading.Event) -> None:
        self.resp = resp
        self.interrupted = event
        self._active = threading.Event()
        self._fd = None
        self._old = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "EscWatcher":
        try:
            import termios
            import tty
            if sys.stdin.isatty():
                self._fd = sys.stdin.fileno()
                self._old = termios.tcgetattr(self._fd)
                tty.setcbreak(self._fd)
                self._active.set()
                self._thread = threading.Thread(target=self._watch, daemon=True)
                self._thread.start()
        except Exception:  # noqa: BLE001 (non-POSIX / no tty)
            pass
        return self

    def _watch(self) -> None:
        import select
        while self._active.is_set():
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0.15)
            except Exception:  # noqa: BLE001
                return
            if ready:
                try:
                    ch = sys.stdin.read(1)
                except Exception:  # noqa: BLE001
                    return
                if ch == "\x1b":  # Esc
                    self.interrupted.set()
                    try:
                        self.resp.close()
                    except Exception:  # noqa: BLE001
                        pass
                    return

    def __exit__(self, *_a) -> None:
        self._active.clear()
        if self._thread:
            self._thread.join(timeout=0.3)
        if self._fd is not None and self._old is not None:
            try:
                import termios
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------------- one turn
def run_turn(url: str, network: str, message: str, conv_id: str | None,
             workspace: str, verbose: bool) -> str | None:
    payload = {"message": message, "conversation_id": conv_id, "mode": "assist",
               "network": network, "workspace_path": workspace}
    show_trace = console.is_terminal or verbose
    new_conv = conv_id
    answer = ""
    live: Live | None = None
    interrupted = threading.Event()
    status = console.status(Text("Thinking…", style="dim"), spinner="dots")
    status.start()
    status_on = True

    def stop_status() -> None:
        nonlocal status_on
        if status_on:
            status.stop()
            status_on = False

    if console.is_terminal:
        status.update(Text("Thinking…  (Esc to interrupt)", style="dim"))
    try:
        with httpx.stream("POST", f"{url}/api/chat", json=payload, timeout=None) as r, EscWatcher(r, interrupted):
            for line in r.iter_lines():
                if interrupted.is_set():
                    break
                if not line or not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                t = ev.get("type")
                if t == "conversation":
                    new_conv = ev.get("id", conv_id)
                elif t == "activity":
                    if status_on:
                        status.update(Text(ev.get("text", "Thinking…"), style="dim"))
                elif t == "trace":
                    node = ev.get("node")
                    if node and status_on:
                        status.update(Text(f"{node} · working…", style="dim"))
                elif t == "agent_message":
                    if show_trace:
                        txt = " ".join((ev.get("text") or "").split())[:150]
                        console.print(Text.assemble(("  ↳ ", ACCENT),
                                                    (f"{ev.get('agent','agent')}  ", ACCENT),
                                                    (txt, "dim")))
                elif t == "command":
                    console.print(f"  [yellow]$ {ev.get('command','')}[/]")
                    out = (ev.get("output") or "").rstrip()
                    if out:
                        console.print("[dim]" + "\n".join("    " + ln for ln in out.splitlines()[:40]) + "[/]")
                elif t == "image_pending":
                    if status_on:
                        status.update(Text("🖼  generating image…", style="magenta"))
                elif t == "answer":
                    answer = ev.get("text", "")
                    if live is None:
                        stop_status()
                        console.print()
                        live = Live(Markdown(answer), console=console, refresh_per_second=12,
                                    vertical_overflow="visible")
                        live.start()
                    else:
                        live.update(Markdown(answer))
                elif t == "error":
                    if live:
                        live.stop(); live = None
                    stop_status()
                    console.print(f"[red]⚠ {ev.get('text','')}[/]")
    except httpx.HTTPError as exc:
        if live:
            live.stop(); live = None
        stop_status()
        if not interrupted.is_set():  # an Esc-close raises here too — that's expected
            console.print(f"[red]⚠ connection error:[/] {exc}")
            return conv_id
    finally:
        if live:
            live.stop()
        stop_status()

    if interrupted.is_set():
        console.print("[yellow]⏹ interrupted[/]")
    elif answer:
        artifacts(url, answer)
    return new_conv


def switch_model(url: str, arg: str) -> None:
    """Change the LLM from the CLI. `/model` interactive; `/model <model>` or
    `/model <provider> <model>` quick. Restarts the runtime."""
    try:
        data = httpx.get(f"{url}/api/llm", timeout=6).json()
    except Exception:  # noqa: BLE001
        console.print("[red]neura:[/] couldn't load the model catalog.")
        return
    providers = data.get("providers", [])
    active = data.get("active", {})
    if not providers:
        console.print("[red]neura:[/] no providers reported by the backend.")
        return

    def find_by_model(m: str):
        for p in providers:
            if m in (p.get("models") or []):
                return p
        return None

    provider = model = None
    parts = arg.split()
    if len(parts) >= 2:  # "/model openai gpt-5.4"
        provider = next((p for p in providers if p["id"] == parts[0] or p["label"].lower().startswith(parts[0].lower())), None)
        model = parts[1]
    elif len(parts) == 1:  # "/model gpt-5.4"
        provider = find_by_model(parts[0])
        model = parts[0]
    if not provider or not model:
        # interactive picker
        console.print("[bold]Providers[/]")
        for i, p in enumerate(providers, 1):
            mark = "  [green](active)[/]" if p["id"] == active.get("provider") else ""
            key = "[green]key ✓[/]" if p.get("key_set") else "[dim]no key[/]"
            console.print(f"  {i}. {p['label']}  {key}{mark}")
        sel = console.input(f"[{ACCENT}]provider[/] # or name (blank to cancel): ").strip()
        if not sel:
            console.print("[dim]cancelled[/]")
            return
        provider = (providers[int(sel) - 1] if sel.isdigit() and 1 <= int(sel) <= len(providers)
                    else next((p for p in providers if p["id"] == sel or p["label"].lower().startswith(sel.lower())), None))
        if not provider:
            console.print("[red]unknown provider[/]")
            return
        models = provider.get("models") or []
        for i, m in enumerate(models, 1):
            console.print(f"  {i}. {m}")
        msel = console.input(f"[{ACCENT}]model[/] # or name (blank to cancel): ").strip()
        if not msel:
            console.print("[dim]cancelled[/]")
            return
        model = (models[int(msel) - 1] if msel.isdigit() and 1 <= int(msel) <= len(models) else msel)
    else:
        provider = provider or find_by_model(model)
    if not provider or not model:
        console.print("[red]neura:[/] pick a provider and model.")
        return

    api_key = ""
    if not provider.get("key_set"):
        api_key = console.input(f"[{ACCENT}]{provider.get('env_key','API key')}[/] (paste, hidden): ",
                                password=True).strip()
        if not api_key:
            console.print("[red]neura:[/] that provider has no saved key.")
            return

    with console.status(f"[dim]Switching to {model}… (restarting runtime)[/]", spinner="dots"):
        try:
            res = httpx.post(f"{url}/api/llm",
                             json={"provider": provider["id"], "model": model, "api_key": api_key},
                             timeout=30).json()
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]neura:[/] {exc}")
            return
        if res.get("error"):
            console.print(f"[red]neura:[/] {res['error']}")
            return
        for _ in range(40):
            if health(url):
                break
            time.sleep(1)
    console.print(f"[green]✓[/] now using [bold]{model}[/] [dim]({provider['id']})[/]")


# ----------------------------------------------------------------- REPL
def repl(url: str, network: str, workspace: str, verbose: bool) -> None:
    welcome(url, network, workspace, up=True)
    conv_id: str | None = None
    while True:
        try:
            msg = console.input(f"\n[bold {ACCENT}]❯[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not msg:
            continue
        if msg in ("/exit", "/quit", ":q"):
            return
        if msg == "/new":
            conv_id = None
            console.rule("[dim]new conversation[/]", style="dim")
            continue
        if msg == "/clear":
            console.clear()
            welcome(url, network, workspace, up=health(url))
            continue
        if msg == "/model" or msg.startswith("/model "):
            switch_model(url, msg[len("/model"):].strip())
            continue
        if msg == "/help":
            console.print(
                "[dim]  /model   switch the LLM        /new    fresh conversation\n"
                "  /clear   clear the screen       /exit   quit\n"
                "  Esc      interrupt a reply       -v      full agent trace[/]"
            )
            continue
        console.print()
        conv_id = run_turn(url, network, msg, conv_id, workspace, verbose)


def main() -> None:
    ap = argparse.ArgumentParser(prog="neura", description="Chat with Neura from the terminal.")
    ap.add_argument("prompt", nargs="*", help="one-shot message (omit for interactive session)")
    ap.add_argument("--url", default=os.environ.get("NEURA_URL", "http://127.0.0.1:8010"),
                    help="Neura backend URL (default http://127.0.0.1:8010)")
    ap.add_argument("--network", default="neura", help="agent network (default: neura)")
    ap.add_argument("--workspace", default=os.getcwd(),
                    help="folder Neura's dev agent works in (default: current directory)")
    ap.add_argument("--verbose", "-v", action="store_true", help="show the full agent trace")
    ap.add_argument("--no-serve", action="store_true",
                    help="don't auto-start a local backend; require one already running")
    args = ap.parse_args()

    url = args.url.rstrip("/")
    if not ensure_backend(url, serve=not args.no_serve):
        if args.no_serve:
            console.print(f"[red]neura:[/] backend not reachable at {url}")
            console.print("[dim]Start it:  bash scripts/start_neura.sh   (or drop --no-serve to auto-start)[/]")
        sys.exit(2)

    if args.prompt:
        run_turn(url, args.network, " ".join(args.prompt), None, args.workspace, args.verbose)
    else:
        repl(url, args.network, args.workspace, args.verbose)


if __name__ == "__main__":
    main()
