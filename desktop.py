"""Neura desktop launcher.

Runs Neura in a native macOS window (WKWebView via pywebview) — no browser. Uses its
OWN port range (82xx) so it never collides with a dev instance, and stops all services
(freeing their ports) when the window closes.

FIRST RUN: if no LLM API key is configured, it shows a key-entry screen, writes the
key to the app's own .env + points llm_config at that provider, then boots. So a
teammate who just double-clicks it never sees "Server offline".
"""
from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent

# --- Isolated app ports (distinct from dev defaults) ---
os.environ["NEURA_UI_PORT"] = os.environ.get("NEURA_UI_PORT", "8210")
os.environ["NEURA_HTTP_PORT"] = os.environ.get("NEURA_HTTP_PORT", "8211")
os.environ["TTS_PORT"] = os.environ.get("TTS_PORT", "8212")
os.environ["STT_PORT"] = os.environ.get("STT_PORT", "8213")
os.environ.setdefault("NEURA_SERVER_URL", f"http://127.0.0.1:{os.environ['NEURA_HTTP_PORT']}")
os.environ.setdefault("TTS_URL", f"http://127.0.0.1:{os.environ['TTS_PORT']}")
os.environ.setdefault("STT_URL", f"http://127.0.0.1:{os.environ['STT_PORT']}")

URL = f"http://127.0.0.1:{os.environ['NEURA_UI_PORT']}"
SERVICES = ["run_server.sh", "run_ui.sh", "run_tts.sh", "run_stt.sh"]
ENV_VAR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "mistral": "MISTRAL_API_KEY"}
LLM_BLOCK = {
    "anthropic": '    "llm_config": { "class": "anthropic", "model_name": "claude-opus-4-5", "temperature": 0.2 }',
    "openai": '    "llm_config": { "class": "openai", "model_name": "gpt-5.4", "temperature": 0.2 }',
    "mistral": '    "llm_config": { "class": "langchain_mistralai.chat_models.ChatMistralAI", "model": "mistral-large-latest", "temperature": 0.2 }',
}

_procs: list[subprocess.Popen] = []
_window = None

_SPLASH = """<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{height:100%;margin:0;background:#0b0e15;color:#c7ccd8;font:15px -apple-system,system-ui,sans-serif;display:grid;place-items:center}
 .b{width:52px;height:52px;border-radius:50%;border:3px solid #2a3350;border-top-color:#7c7cf6;animation:s 1s linear infinite;margin:0 auto 18px}@keyframes s{to{transform:rotate(360deg)}}
 .t{text-align:center}.m{color:#7b8194;font-size:13px;margin-top:6px}
</style></head><body><div class="t"><div class="b"></div><div>Starting Neura…</div>
 <div class="m">bringing up the agents &amp; voice — first launch can take a minute</div></div></body></html>"""

_KEY_FORM = """<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{height:100%;margin:0;background:#0b0e15;color:#e6e9f0;font:15px -apple-system,system-ui,sans-serif;display:grid;place-items:center}
 .card{width:420px;max-width:86vw;text-align:center}
 h1{font-size:22px;font-weight:640;margin:0 0 6px}.sub{color:#7b8194;font-size:13.5px;margin:0 0 22px;line-height:1.5}
 label{display:block;text-align:left;font-size:12px;color:#8b91a7;margin:14px 4px 6px}
 select,input{width:100%;box-sizing:border-box;background:#141a26;border:1px solid #2a3350;border-radius:11px;color:#e6e9f0;font:inherit;font-size:14px;padding:12px 14px;outline:none}
 select:focus,input:focus{border-color:#7c7cf6}
 button{margin-top:20px;width:100%;padding:13px;border:none;border-radius:11px;background:linear-gradient(135deg,#7c7cf6,#4f46e5);color:#fff;font:inherit;font-size:15px;font-weight:600;cursor:pointer}
 button:disabled{opacity:.6;cursor:default}
 .msg{min-height:18px;margin-top:12px;font-size:12.5px;color:#f2647a}.msg.ok{color:#7b8194}
 .orb{width:48px;height:48px;margin:0 auto 16px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#a5a5ff,#4f46e5)}
</style></head><body>
 <div class="card">
  <div class="orb"></div>
  <h1>Welcome to Neura</h1>
  <p class="sub">Add an LLM API key to get started. It's saved only on this Mac and never leaves your device.</p>
  <label for="prov">Provider</label>
  <select id="prov"><option value="anthropic">Anthropic (Claude)</option><option value="openai">OpenAI (GPT)</option><option value="mistral">Mistral</option></select>
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="paste your key" autofocus />
  <button id="go" onclick="save()">Save &amp; Start</button>
  <div class="msg" id="msg"></div>
 </div>
 <script>
  async function save(){
    const go=document.getElementById('go'), msg=document.getElementById('msg');
    const p=document.getElementById('prov').value, k=document.getElementById('key').value.trim();
    if(!k){ msg.className='msg'; msg.textContent='Please paste a key.'; return; }
    go.disabled=true; msg.className='msg ok'; msg.textContent='Saving…';
    try{
      const r=await window.pywebview.api.save_key(p,k);
      if(r&&r.ok){ msg.textContent='Starting Neura…'; }
      else { go.disabled=false; msg.className='msg'; msg.textContent=(r&&r.error)||'Could not save the key.'; }
    }catch(e){ go.disabled=false; msg.className='msg'; msg.textContent=String(e); }
  }
  document.getElementById('key').addEventListener('keydown',e=>{ if(e.key==='Enter') save(); });
 </script>
</body></html>"""


def _up(url: str, timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def _have_key() -> bool:
    """True if a realistic provider key is already configured (in .env or env)."""
    envp = ROOT / ".env"
    text = envp.read_text(encoding="utf-8") if envp.exists() else ""
    for m in re.finditer(r"^(ANTHROPIC|OPENAI|MISTRAL)_API_KEY\s*=\s*(.*)$", text, re.M):
        if len(m.group(2).strip().strip("\"'")) >= 15:  # 15+ = a real key, not "..."
            return True
    return any(len((os.environ.get(v) or "").strip()) >= 15 for v in ENV_VAR.values())


def _write_key(provider: str, key: str) -> None:
    var = ENV_VAR.get(provider, "ANTHROPIC_API_KEY")
    envp = ROOT / ".env"
    lines = envp.read_text(encoding="utf-8").splitlines() if envp.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith(var + "=")]
    lines.append(f"{var}={key}")
    envp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[var] = key
    (ROOT / "config" / "llm_config.hocon").write_text(
        "{\n" + LLM_BLOCK.get(provider, LLM_BLOCK["anthropic"]) + "\n}\n", encoding="utf-8"
    )


def _start_services() -> None:
    env = dict(os.environ)
    for script in SERVICES:
        p = ROOT / "scripts" / script
        if p.exists():
            _procs.append(subprocess.Popen(
                ["bash", str(p)], cwd=str(ROOT), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))


def _stop_services() -> None:
    for p in _procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
    deadline = time.time() + 5
    for p in _procs:
        try:
            p.wait(timeout=max(0.1, deadline - time.time()))
        except Exception:
            pass
    for p in _procs:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
    _procs.clear()


atexit.register(_stop_services)
for _sig in (signal.SIGTERM, signal.SIGINT):
    try:
        signal.signal(_sig, lambda *_a: (_stop_services(), os._exit(0)))
    except Exception:
        pass


def _boot_and_load() -> None:
    if not _up(f"{URL}/"):
        _start_services()
    for _ in range(180):
        if _up(f"{URL}/"):
            break
        time.sleep(1)
    if _window is not None:
        try:
            _window.load_url(URL)
        except Exception:
            pass


def _post_key_boot() -> None:
    # Let save_key's return value reach its JS callback before we navigate away —
    # loading a new page synchronously inside save_key destroys that callback and
    # raises a (harmless but noisy) JavascriptException.
    time.sleep(0.35)
    if _window is not None:
        try:
            _window.load_html(_SPLASH)
        except Exception:
            pass
    _boot_and_load()


class _Api:
    """Exposed to the key-entry page as window.pywebview.api."""

    def save_key(self, provider: str, key: str):
        provider = (provider or "anthropic").strip().lower()
        key = (key or "").strip()
        if len(key) < 12:
            return {"ok": False, "error": "That key looks too short."}
        try:
            _write_key(provider, key)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        threading.Thread(target=_post_key_boot, daemon=True).start()
        return {"ok": True}


def main() -> None:
    global _window
    if _have_key():
        _window = webview.create_window("Neura", html=_SPLASH, width=1280, height=860, min_size=(920, 640))
        webview.start(lambda w: _boot_and_load(), _window)
    else:
        _window = webview.create_window("Neura", html=_KEY_FORM, js_api=_Api(), width=1280, height=860, min_size=(920, 640))
        webview.start()
    _stop_services()


if __name__ == "__main__":
    main()
