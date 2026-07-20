#!/usr/bin/env python3
"""Cross-platform Neura launcher — set up (venv + packages) and run all servers.

Works on Windows, macOS, and Linux (the .sh scripts are POSIX-only; this is the portable
path used by the CLI and the VS Code extension). Idempotent — safe to re-run. Runs in the
foreground; Ctrl-C stops every server.

  python scripts/neura_serve.py            # start everything
  python scripts/neura_serve.py --no-voice # skip TTS/STT (faster; CLI-only use)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WIN = os.name == "nt"
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
REQS = [
    ROOT / "requirements.txt",
    ROOT / "backend" / "requirements.txt",
    ROOT / "services" / "tts" / "requirements.txt",
    ROOT / "services" / "stt" / "requirements.txt",
]
_procs: list[subprocess.Popen] = []


def log(msg: str) -> None:
    print(msg, flush=True)


def load_env() -> None:
    envf = ROOT / ".env"
    if not envf.exists() and (ROOT / ".env.example").exists():
        shutil.copyfile(ROOT / ".env.example", envf)
    if envf.exists():
        # utf-8-sig strips a BOM (Windows editors often add one, which would corrupt the
        # first key name). Override os.environ so edited .env values take effect on re-run.
        for line in envf.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ[k.strip()] = v


def ensure_venv() -> None:
    if VENV_PY.exists():
        return
    log("▸ Creating virtualenv (.venv)…")
    if shutil.which("uv"):
        subprocess.run(["uv", "venv", str(VENV)], check=True)
    else:
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)


def ensure_deps() -> None:
    present = [r for r in REQS if r.exists()]
    h = hashlib.sha1()
    for r in present:
        h.update(r.read_bytes())
    digest = h.hexdigest()
    stamp = VENV / ".neura-deps"
    if stamp.exists() and stamp.read_text().strip() == digest:
        return
    log("▸ Installing Python packages (first run can take a few minutes)…")
    args: list[str] = []
    for r in present:
        args += ["-r", str(r)]
    if shutil.which("uv"):
        subprocess.run(["uv", "pip", "install", "--python", str(VENV_PY), *args], check=True)
    else:
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"], check=False)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", *args], check=True)
    stamp.write_text(digest)
    # Browser for screenshots (best-effort).
    try:
        subprocess.run([str(VENV_PY), "-c", "import playwright"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([str(VENV_PY), "-m", "playwright", "install", "chromium"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:  # noqa: BLE001
        pass


def maybe_build_ui() -> None:
    if (ROOT / "frontend" / "dist" / "index.html").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        return
    log("▸ Building the web UI (best-effort)…")
    try:
        subprocess.run([npm, "install"], cwd=str(ROOT / "frontend"), shell=IS_WIN, check=True)
        subprocess.run([npm, "run", "build"], cwd=str(ROOT / "frontend"), shell=IS_WIN, check=True)
    except Exception:  # noqa: BLE001
        log("  (UI build skipped — backend still starts)")


def key_present() -> bool:
    return any(len((os.environ.get(k) or "").strip()) >= 15
               for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MISTRAL_API_KEY"))


def base_env() -> dict:
    env = dict(os.environ)
    env.setdefault("NEURA_HTTP_PORT", "8099")
    env.setdefault("NEURA_UI_PORT", "8010")
    env.setdefault("TTS_PORT", "8900")
    env.setdefault("STT_PORT", "8901")
    env.setdefault("NEURA_SERVER_URL", f"http://localhost:{env['NEURA_HTTP_PORT']}")
    env.setdefault("TTS_URL", f"http://localhost:{env['TTS_PORT']}")
    env.setdefault("STT_URL", f"http://localhost:{env['STT_PORT']}")
    return env


def spawn(cmd: list[str], cwd: Path, env: dict) -> None:
    _procs.append(subprocess.Popen(cmd, cwd=str(cwd), env=env))


def start_all(no_voice: bool) -> None:
    env = base_env()
    py = str(VENV_PY)

    # neuro-san runtime. The manifest paths are RELATIVE (resolved against cwd=ROOT):
    # neuro-san splits AGENT_MANIFEST_FILE on spaces, so an absolute path under a folder
    # with spaces (e.g. C:\Users\First Last\…) would shatter and crash. Relative avoids it.
    server_env = dict(env)
    server_env["AGENT_MANIFEST_FILE"] = os.path.join("registries", "manifest.hocon")
    server_env["AGENT_NETWORK_DESIGNER_MANIFEST_FILE"] = os.path.join("registries", "manifest.hocon")
    server_env["AGENT_TOOL_PATH"] = str(ROOT / "coded_tools")
    sep = os.pathsep
    server_env["PYTHONPATH"] = sep.join([str(ROOT), str(ROOT / "coded_tools"),
                                         os.environ.get("PYTHONPATH", "")]).rstrip(sep)
    server_env["AGENT_TOOLBOX_INFO_FILE"] = str(ROOT / "config" / "toolbox_info.hocon")
    server_env["AGENT_NETWORK_DESIGNER_TOOLBOX_INFO_FILE"] = str(ROOT / "config" / "agent_network_designer_toolbox_info.hocon")
    server_env["MCP_SERVERS_INFO_FILE"] = str(ROOT / "config" / "mcp" / "mcp_info.hocon")
    server_env.setdefault("AGENT_MANIFEST_UPDATE_PERIOD_SECONDS", "5")
    spawn([py, "-m", "neuro_san.service.main_loop.server_main_loop",
           "--http_port", env["NEURA_HTTP_PORT"]], ROOT, server_env)

    # UI/API backend
    spawn([py, "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0",
           "--port", env["NEURA_UI_PORT"]], ROOT, env)

    if not no_voice:
        spawn([py, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", env["TTS_PORT"]],
              ROOT / "services" / "tts", env)
        spawn([py, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", env["STT_PORT"]],
              ROOT / "services" / "stt", env)

    log(f"✅ Neura starting → http://localhost:{env['NEURA_UI_PORT']}")
    log("   Keep this window open; press Ctrl-C to stop Neura.")


def stop_all(*_a) -> None:
    for p in _procs:
        try:
            p.terminate()
        except Exception:  # noqa: BLE001
            pass
    deadline = time.time() + 5
    for p in _procs:
        try:
            p.wait(timeout=max(0.1, deadline - time.time()))
        except Exception:  # noqa: BLE001
            pass
    for p in _procs:
        if p.poll() is None:
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-voice", action="store_true", help="skip TTS/STT servers")
    args = ap.parse_args()

    log(f"▸ Neura setup + start   ({ROOT})")
    load_env()
    ensure_venv()
    ensure_deps()
    maybe_build_ui()
    if not key_present():
        log("⚠  No LLM API key in .env. Add e.g. ANTHROPIC_API_KEY=… or OPENAI_API_KEY=… and re-run.")

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, lambda *_a: (stop_all(), sys.exit(0)))
        except Exception:  # noqa: BLE001
            pass

    try:
        start_all(args.no_voice)
        while any(p.poll() is None for p in _procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    main()
