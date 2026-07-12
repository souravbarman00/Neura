"""Neura backend — serves the assistant UI and provides the app's real API:

- Conversation persistence (SQLite) with agent-network memory compression
- Streaming chat proxied to the neuro-san runtime, with multi-turn context
- Local knowledge stats + voice (Kokoro) proxy

The browser only ever talks to this FastAPI app.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import compress, nsclient, spawn, store
from backend.watcher import manager as watch_manager

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend" / "dist"
ENV_FILE = ROOT / ".env"

NEURA_SERVER_URL = os.environ.get("NEURA_SERVER_URL", "http://localhost:8099")
NEURA_NETWORK = os.environ.get("NEURA_NETWORK", "neura")
TTS_URL = os.environ.get("TTS_URL", "http://localhost:8900")

app = FastAPI(title="Neura")
store.init_db()

# Friendly titles for built-in networks; spawned ones come from the DB.
BUILTIN_TITLES = {"neura": "Neura", "agent_network_designer": "Network Designer"}
# Networks that are served but not user-facing.
HIDDEN_NETWORKS = {"memory_compressor", "network_builder"}

# ------------------------------------------------------------------ LLM providers
LLM_CONFIG_FILE = ROOT / "config" / "llm_config.hocon"

# The three providers Neura can run on. Anthropic + OpenAI are native neuro-san
# classes (model picked by "model_name" from its registry); Mistral is wired via
# its LangChain class directly (model picked by "model"). Each maps to an env key.
LLM_PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "label": "Claude (Anthropic)",
        "class": "anthropic",
        "model_field": "model_name",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "label": "OpenAI (GPT)",
        "class": "openai",
        "model_field": "model_name",
        "env_key": "OPENAI_API_KEY",
    },
    "mistral": {
        "label": "Mistral AI",
        "class": "langchain_mistralai.chat_models.ChatMistralAI",
        "model_field": "model",
        "env_key": "MISTRAL_API_KEY",
    },
}
# class value -> provider id (for reading the active provider back out of the hocon)
_CLASS_TO_PROVIDER = {v["class"]: k for k, v in LLM_PROVIDERS.items()}

# Mistral has no neuro-san registry, so we curate its model list (la Plateforme).
MISTRAL_MODELS = [
    "mistral-large-latest",
    "mistral-medium-latest",
    "mistral-small-latest",
    "magistral-medium-latest",
    "magistral-small-latest",
    "ministral-8b-latest",
    "ministral-3b-latest",
    "codestral-latest",
    "pixtral-large-latest",
    "open-mistral-nemo",
]

_LLM_MODELS_CACHE: dict[str, list[str]] = {}


def _registry_models() -> dict[str, list[str]]:
    """Friendly model aliases the installed neuro-san actually supports, by provider.
    Grounds the UI dropdowns so we never offer a model the runtime can't build."""
    if _LLM_MODELS_CACHE:
        return _LLM_MODELS_CACHE
    out: dict[str, list[str]] = {"anthropic": [], "openai": [], "mistral": list(MISTRAL_MODELS)}
    try:
        from neuro_san.internals.run_context.langchain.llms.default_llm_factory import (
            DefaultLlmFactory,
        )

        f = DefaultLlmFactory()
        f.load()
        infos = f.llm_infos
        meta = {"classes", "default_config"}

        def rclass(k: str):
            e = infos.get(k)
            if not isinstance(e, dict):
                return None
            if "class" in e:
                return e["class"]
            t = e.get("use_model_name")
            return infos.get(t, {}).get("class") if isinstance(infos.get(t), dict) else None

        def is_alias(k: str):
            e = infos.get(k)
            return isinstance(e, dict) and set(e.keys()) <= {"use_model_name"}

        for prov in ("anthropic", "openai"):
            out[prov] = sorted(
                k for k in infos if k not in meta and is_alias(k) and rclass(k) == prov
            )
    except Exception:  # noqa: BLE001 — best effort; fall back to curated below
        pass
    # Safety nets if the registry scan came up empty for a native provider.
    if not out["anthropic"]:
        out["anthropic"] = ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"]
    if not out["openai"]:
        out["openai"] = ["gpt-5.4", "gpt-5.4-mini", "gpt-4o", "o3-mini"]
    _LLM_MODELS_CACHE.update(out)
    return out


def _valid_model(provider: str, model: str) -> bool:
    """Mistral accepts any non-empty model (user-class path); native providers must
    name a model the registry knows."""
    if not model:
        return False
    if provider == "mistral":
        return True
    try:
        from neuro_san.internals.run_context.langchain.llms.default_llm_factory import (
            DefaultLlmFactory,
        )

        f = DefaultLlmFactory()
        f.load()
        return model in f.llm_infos
    except Exception:  # noqa: BLE001
        return model in _registry_models().get(provider, [])


def _env_has(key: str) -> bool:
    """Whether an API key is already saved (env or .env) — checked, never returned."""
    if os.environ.get(key):
        return True
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() == key and v.strip():
                return True
    return False


def _read_active_llm() -> dict:
    """Current provider + model from config/llm_config.hocon."""
    provider, model = "anthropic", None
    try:
        from pyhocon import ConfigFactory

        lc = ConfigFactory.parse_file(str(LLM_CONFIG_FILE)).get("llm_config", {})
        cls = lc.get("class", "anthropic")
        provider = _CLASS_TO_PROVIDER.get(cls, "anthropic")
        model = lc.get("model_name", None) or lc.get("model", None)
    except Exception:  # noqa: BLE001
        pass
    return {"provider": provider, "model": model}


def _render_llm_hocon(active: str, model: str, temperature: float = 0.2) -> str:
    """Regenerate config/llm_config.hocon with `active` provider live and the other
    two kept as documented, commented presets."""
    def block(pid: str, mdl: str, commented: bool) -> str:
        p = LLM_PROVIDERS[pid]
        pre = "    # " if commented else "    "
        lines = [
            f'{pre}"llm_config": {{',
            f'{pre}    "class": "{p["class"]}",',
            f'{pre}    "{p["model_field"]}": "{mdl}",',
            f'{pre}    "temperature": {temperature}',
            f"{pre}}}",
        ]
        return "\n".join(lines)

    defaults = {"anthropic": "claude-sonnet-4-5", "openai": "gpt-5.4", "mistral": "mistral-large-latest"}
    order = [active] + [p for p in ("anthropic", "openai", "mistral") if p != active]
    header = (
        "{\n"
        "    # LLM for every agent in the Neura network. Managed by the Settings → Model\n"
        "    # tab in the UI (POST /api/llm). Edit there, or swap the active block below.\n"
        "    #\n"
        "    #   Anthropic / OpenAI: native neuro-san classes (use \"model_name\").\n"
        "    #   Mistral: wired via ChatMistralAI (uses \"model\").\n\n"
    )
    parts = [header]
    for i, pid in enumerate(order):
        mdl = model if pid == active else defaults[pid]
        label = LLM_PROVIDERS[pid]["label"]
        tag = "Active" if i == 0 else "Preset"
        parts.append(f"    # --- {tag}: {label} ---\n")
        parts.append(block(pid, mdl, commented=(i != 0)) + "\n\n")
    return "".join(parts).rstrip() + "\n}\n"


def _write_llm_config(provider: str, model: str) -> None:
    LLM_CONFIG_FILE.write_text(_render_llm_hocon(provider, model), encoding="utf-8")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _title_from(message: str) -> str:
    t = " ".join(message.split())
    return (t[:48] + "…") if len(t) > 48 else (t or "New conversation")


sys.path.insert(0, str(ROOT / "coded_tools"))


def _kb_count(collection: str | None = None) -> int:
    try:
        from neura.knowledge_base import KnowledgeBase

        return KnowledgeBase(collection=collection).count()
    except Exception:  # noqa: BLE001
        return -1


def _ingest(paths: list[str], collection: str | None = None) -> dict:
    from neura.ingest_lib import ingest_paths

    return ingest_paths(paths, collection=collection)


_BUILD_RE = re.compile(r"\[\[BUILD_AGENT:\s*(.+?)\]\]", re.DOTALL)


def _extract_build(text: str) -> tuple[str, str | None]:
    """Strip a [[BUILD_AGENT: ...]] marker from Neura's answer; return (clean, desc)."""
    m = _BUILD_RE.search(text)
    if not m:
        return text, None
    desc = " ".join(m.group(1).split())
    clean = _BUILD_RE.sub("", text).strip()
    return clean, desc


# Map a checklist step to the sub-agent that most likely handles it, so the UI can
# badge each task with the responsible agent. Order matters (first match wins).
_AGENT_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("jira", ("jira", "ticket", "leaf-", "sprint", "backlog", "epic", "story")),
    ("github", ("github", "pull request", " pr ", "pr ", " pr", "open a pr", "branch", "merge", "commit", "review")),
    ("codebase", ("code", "calc.py", ".py", ".ts", ".js", "file", "repo", "local", "edit", "fix",
                  "refactor", "implement", "run", "test", "build", "lint", "function", "workspace")),
    ("slack", ("slack", "message", "channel", "dm", "notify", "ping", "post to")),
    ("outlook", ("email", "mail", "inbox", "calendar", "meeting", "invite")),
    ("teams", ("teams",)),
    ("figma", ("figma", "design", "frame", "mockup")),
    ("knowledge_search", ("knowledge", "notes", "search my", "my docs", "read jira")),
]


def _infer_agent(item: str) -> str:
    """Best-effort mapping from a task description to the sub-agent responsible."""
    low = f" {item.lower()} "
    for agent, keys in _AGENT_HINTS:
        if any(k in low for k in keys):
            return agent
    return ""


# The personal-profile fields shown in the form and folded into Neura's context.
PROFILE_FIELDS: list[tuple[str, str]] = [
    ("name", "Name"),
    ("role", "Role / title"),
    ("company", "Company"),
    ("team", "Team / group"),
    ("location", "Location"),
    ("timezone", "Time zone"),
    ("working_hours", "Working hours"),
    ("focus", "Current focus / projects"),
    ("communication_style", "How I like responses"),
    ("about", "About me"),
]


def _profile_preface(profile: dict) -> str:
    """A compact 'about the user' note prepended to Neura's turns so it remembers them."""
    if not profile:
        return ""
    parts = []
    for key, label in PROFILE_FIELDS:
        val = (profile.get(key) or "").strip() if isinstance(profile.get(key), str) else profile.get(key)
        if val:
            parts.append(f"{label}: {val}")
    if not parts:
        return ""
    return (
        "(About the user you're assisting — remember this and use it to personalize your help; "
        "address them by name when natural: " + " | ".join(parts) + ")"
    )


_PLUMBING_PREFIXES = ("Invoking:", "Invoking `", "Received arguments:", "Got result:", "Received:")


def _is_plumbing(t: str) -> bool:
    """True for framework tool-call plumbing lines that shouldn't show as agent talk."""
    s = (t or "").strip()
    return (not s) or any(s.startswith(p) for p in _PLUMBING_PREFIXES)


def _trim(t: str, n: int = 700) -> str:
    s = " ".join((t or "").split())
    return s if len(s) <= n else s[:n] + "…"


def _parse_command(text: str) -> dict | None:
    """Parse a codebase `run` tool result ('$ <cmd>\\n(exit code N)\\n--- stdout ---\\n…')
    into a structured command card. Returns None if the text isn't a command run."""
    s = (text or "").lstrip()
    if not s.startswith("$ "):
        return None
    lines = s.splitlines()
    command = lines[0][2:].strip()
    exit_code = 0
    m = re.search(r"\(exit code (-?\d+)\)", s)
    if m:
        exit_code = int(m.group(1))
    # Everything after the "(exit code N)" line is the output (stdout/stderr sections).
    out = s
    if m:
        out = s[m.end():].strip()
    out = out.replace("--- stdout ---", "").replace("--- stderr ---", "\n[stderr]").strip()
    if len(out) > 4000:
        out = out[:4000] + "\n… (truncated)"
    return {"command": command, "exit": exit_code, "output": out}


async def _semantic_new_items(existing: list[str], candidates: list[str]) -> list[str]:
    """Return only the candidate steps that are genuinely NEW — not a reworded duplicate
    of an existing step. Uses a cheap Haiku call so "Open a PR" and "Create the pull
    request" don't become two entries; falls back to normalized-text dedup if the model
    isn't available."""
    cands = [str(c).strip() for c in candidates if str(c).strip()]
    if not cands:
        return []
    existing = [str(e).strip() for e in existing if str(e).strip()]
    if not existing:
        return cands

    def _text_fallback() -> list[str]:
        seen = {e.lower() for e in existing}
        out = []
        for c in cands:
            if c.lower() not in seen:
                out.append(c)
                seen.add(c.lower())
        return out

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _text_fallback()
    prompt = (
        "You are de-duplicating a task checklist. EXISTING steps:\n"
        + "\n".join(f"- {s}" for s in existing)
        + "\n\nCANDIDATE new steps:\n"
        + "\n".join(f"- {c}" for c in cands)
        + "\n\nSome candidates may be reworded versions of an existing step (same intent). "
        "Return a JSON array containing ONLY the candidates that are genuinely NEW (no existing "
        "step already covers them), each copied VERBATIM from the candidate list. If none are new, "
        "return []. Output only the JSON array."
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 500,
                      "messages": [{"role": "user", "content": prompt}]},
            )
            data = r.json()
            txt = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            arr = json.loads(txt[txt.find("["): txt.rfind("]") + 1])
            allow = {c: True for c in cands}  # only accept verbatim candidates, preserve order
            picked = [c for c in arr if isinstance(c, str) and c in allow]
            return picked
    except Exception:  # noqa: BLE001
        return _text_fallback()


async def _apply_checklist(checklist: list, name: str, params: dict) -> None:
    """Mutate `checklist` (list of {item,status,notes,agent}) from a checklist tool call."""
    if name == "create_checklist":
        # MERGE, and use AI to decide what's genuinely new: a follow-up turn keeps the
        # existing plan and only appends steps not already covered (even if reworded),
        # preserving the status/notes of steps already tracked.
        existing_items = [c["item"] for c in checklist]
        for s in await _semantic_new_items(existing_items, params.get("items") or []):
            checklist.append({"item": s, "status": "pending", "notes": "", "agent": _infer_agent(s)})
    elif name == "update_checklist_item":
        idx = params.get("item_index")
        if isinstance(idx, int) and 1 <= idx <= len(checklist):
            if params.get("status"):
                checklist[idx - 1]["status"] = params["status"]
            if params.get("notes"):
                checklist[idx - 1]["notes"] = params["notes"]
    elif name == "edit_checklist_item":
        idx = params.get("item_index")
        new_item = params.get("new_item")
        if isinstance(idx, int) and 1 <= idx <= len(checklist) and new_item:
            checklist[idx - 1]["item"] = str(new_item).strip()
            checklist[idx - 1]["agent"] = _infer_agent(str(new_item))


# ---------------------------------------------------------------- health / kb
@app.get("/api/health")
async def health() -> dict:
    runtime_ok = False
    agents: list = []
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{NEURA_SERVER_URL}/api/v1/list")
            agents = r.json().get("agents", [])
            runtime_ok = any(a.get("agent_name") == NEURA_NETWORK for a in agents)
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok", "runtime": runtime_ok, "network": NEURA_NETWORK, "kb_chunks": _kb_count()}


# ---------------------------------------------------------------- profile
@app.get("/api/profile")
async def get_profile():
    return {"profile": store.get_profile(), "fields": [{"key": k, "label": l} for k, l in PROFILE_FIELDS]}


@app.post("/api/profile")
async def save_profile(request: Request):
    payload = await request.json()
    profile = payload.get("profile") or {}
    # Keep only known string fields, trimmed.
    clean = {}
    known = {k for k, _ in PROFILE_FIELDS}
    for k, v in profile.items():
        if k in known and isinstance(v, str) and v.strip():
            clean[k] = v.strip()
    store.set_profile(clean)
    return {"ok": True, "profile": clean}


# ---------------------------------------------------------------- persistent memory
# Same markdown store + namespace the persistent_memory middleware uses, so facts
# added here are exactly the memory the neura agent reads/writes during chats.
MEMORY_NS = "neura.neura"
MEMORY_SUGGESTED: list[dict] = [
    {"key": "github_username", "label": "GitHub username", "placeholder": "octocat"},
    {"key": "github_default_repo", "label": "Default GitHub repo", "placeholder": "owner/repo"},
    {"key": "jira_project", "label": "Jira project key", "placeholder": "LEAF"},
    {"key": "confluence_space", "label": "Confluence space key", "placeholder": "ENG"},
    {"key": "slack_workspace", "label": "Slack workspace", "placeholder": "cognizant-ai-lab"},
    {"key": "slack_default_channel", "label": "Slack channel", "placeholder": "#neura"},
    {"key": "teams_default", "label": "Teams team / channel", "placeholder": "AI Lab / General"},
]


def _memory_store():
    from middleware.persistent_memory.topic_store_factory import TopicStoreFactory

    return TopicStoreFactory.create({"backend": "markdown_file", "folder_name": "data/memory"}, sly_data={})


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (topic or "").strip().lower()).strip("_")


@app.get("/api/memory")
async def memory_list():
    try:
        s = _memory_store()
        topics = await s.list_topics(MEMORY_NS)
        items = []
        for t in topics:
            c = await s.get_topic(MEMORY_NS, t)
            items.append({"topic": t, "content": (c or "").strip()})
        return {"items": items, "suggested": MEMORY_SUGGESTED}
    except Exception as e:  # noqa: BLE001
        return {"items": [], "suggested": MEMORY_SUGGESTED, "error": str(e)}


@app.post("/api/memory")
async def memory_set(request: Request):
    payload = await request.json()
    topic = _slug(payload.get("topic", ""))
    content = (payload.get("content") or "").strip()
    if not topic:
        return JSONResponse({"error": "topic required"}, status_code=400)
    s = _memory_store()
    if content:
        await s.set_topic(MEMORY_NS, topic, content)
    else:
        await s.delete_topic(MEMORY_NS, topic)  # empty value clears the memory
    return {"ok": True, "topic": topic}


@app.delete("/api/memory/{topic}")
async def memory_delete(topic: str):
    s = _memory_store()
    await s.delete_topic(MEMORY_NS, _slug(topic))
    return {"ok": True}


# --------------------------------------------------- workflow memory (per chat)
@app.get("/api/workflow-memory/{cid}")
async def workflow_memory_get(cid: str) -> dict:
    from neura import workflow_memory_lib as wm

    return wm.load(cid)


@app.post("/api/workflow-memory/{cid}")
async def workflow_memory_add(request: Request, cid: str):
    """User adds a detail to this workflow's memory from the chat/UI."""
    from neura import workflow_memory_lib as wm

    payload = await request.json()
    value = (payload.get("value") or "").strip()
    key = (payload.get("key") or "note").strip() or "note"
    if not value:
        return JSONResponse({"error": "value required"}, status_code=400)
    entry = wm.add(cid, value, key=key, source="user")
    return {"ok": True, "entry": entry}


@app.delete("/api/workflow-memory/{cid}/{entry_id}")
async def workflow_memory_del_entry(cid: str, entry_id: str) -> dict:
    from neura import workflow_memory_lib as wm

    return {"ok": wm.delete_entry(cid, entry_id)}


@app.delete("/api/workflow-memory/{cid}")
async def workflow_memory_clear(cid: str) -> dict:
    """Delete this workflow's entire memory JSON — user control once the task is done."""
    from neura import workflow_memory_lib as wm

    return {"ok": wm.delete_all(cid)}


async def _memory_preface() -> str:
    """All of Neura's long-term memory, folded into every turn so it's ALWAYS
    grounded in the user's specific info without depending on it calling a tool."""
    try:
        s = _memory_store()
        topics = await s.list_topics(MEMORY_NS)
        if not topics:
            return ""
        parts = []
        for t in topics:
            c = " ".join(((await s.get_topic(MEMORY_NS, t)) or "").split())
            if c:
                parts.append(f"{t}: {c}")
        if not parts:
            return ""
        blob = " | ".join(parts)
        if len(blob) > 3000:
            blob = blob[:3000] + " …"
        return (
            "(WHAT YOU KNOW ABOUT THE USER — from your long-term memory; treat this as ground "
            "truth and use it directly without re-asking. If a fact here is relevant to the "
            "request, apply it: " + blob + ")"
        )
    except Exception:  # noqa: BLE001
        return ""


# Once a chat passes this many messages, stop replaying neuro-san's full multi-turn state
# and instead send a compact "summary + last few turns" — keeps the model focused and calling
# tools instead of pattern-matching on a long, stale history (Claude-style context compaction).
COMPACT_AFTER_MESSAGES = 20
COMPACT_KEEP_TURNS = 8


def _compacted_history(conv_id: str) -> str:
    """Summary of earlier turns + the last few verbatim turns, for compacted mode."""
    summary, upto = store.get_summary_state(conv_id)
    tail = store.messages_after(conv_id, upto)
    tail = tail[:-1] if tail else []  # drop the just-added current user message
    parts = []
    if summary:
        parts.append("Summary of earlier conversation:\n" + summary)
    if tail:
        convo = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Neura'}: {' '.join((m['text'] or '').split())[:600]}"
            for m in tail[-COMPACT_KEEP_TURNS:]
        )
        parts.append("Recent turns:\n" + convo)
    if not parts:
        return ""
    return "(Conversation context — " + "\n\n".join(parts) + ")"


# ---------------------------------------------------------------- knowledge
@app.get("/api/fs")
async def fs_list(path: str = "") -> dict:
    """List sub-folders of a directory, for the in-app folder browser."""
    from neura.ingest_lib import SKIP_DIRS

    try:
        base = (Path(path).expanduser() if path else Path.home()).resolve()
    except Exception:  # noqa: BLE001
        base = Path.home()
    if not base.exists() or not base.is_dir():
        base = Path.home()

    dirs: list[str] = []
    file_count = 0
    try:
        for entry in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    if entry.name not in SKIP_DIRS:
                        dirs.append(entry.name)
                else:
                    file_count += 1
            except OSError:
                continue
    except PermissionError:
        pass

    parent = str(base.parent) if base.parent != base else None
    return {"path": str(base), "parent": parent, "dirs": dirs, "files": file_count, "home": str(Path.home())}


# ---------------------------------------------------------------- code editor (Monaco)
def _ws_root(cid: str) -> Path | None:
    p = store.get_workspace(cid) if cid else ""
    if not p:
        return None
    base = Path(p).expanduser()
    try:
        base = base.resolve()
    except Exception:  # noqa: BLE001
        return None
    return base if base.is_dir() else None


def _ws_target(base: Path, rel: str) -> Path | None:
    """Resolve a workspace-relative path, refusing anything outside the workspace."""
    cand = (base / rel).resolve()
    if cand == base or base in cand.parents:
        return cand
    return None


@app.get("/api/tree")
async def file_tree(cid: str):
    """Flat list of files in the chat's indexed workspace (for the Monaco file tree)."""
    base = _ws_root(cid)
    if not base:
        return {"root": "", "files": []}
    from neura.ingest_lib import SKIP_DIRS

    files: list[str] = []
    for p in base.rglob("*"):
        rel = p.relative_to(base)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if p.is_file():
            try:
                if p.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            files.append(str(rel))
        if len(files) >= 4000:
            break
    files.sort()
    return {"root": str(base), "files": files}


@app.get("/api/file")
async def read_file(cid: str, path: str, ref: str = ""):
    base = _ws_root(cid)
    if not base:
        return JSONResponse({"error": "no workspace"}, status_code=400)
    if ref == "HEAD":
        # The committed version, for the working-tree-vs-HEAD diff.
        try:
            r = subprocess.run(
                ["git", "show", f"HEAD:{path}"], cwd=str(base),
                capture_output=True, text=True, timeout=15,
            )
            return {"content": r.stdout if r.returncode == 0 else "", "exists": r.returncode == 0}
        except Exception:  # noqa: BLE001
            return {"content": "", "exists": False}
    target = _ws_target(base, path)
    if not target or not target.is_file():
        return JSONResponse({"error": "not a file"}, status_code=404)
    try:
        content = target.read_bytes()[:2_000_000].decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"content": content, "path": path}


@app.post("/api/file")
async def write_file(request: Request):
    payload = await request.json()
    cid = payload.get("conversation_id") or payload.get("cid")
    path = payload.get("path") or ""
    content = payload.get("content")
    base = _ws_root(cid)
    if not base:
        return JSONResponse({"error": "no workspace"}, status_code=400)
    target = _ws_target(base, path)
    if not target or content is None:
        return JSONResponse({"error": "bad path"}, status_code=400)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")
    return {"ok": True, "path": path}


@app.get("/api/git/status")
async def git_status(cid: str):
    """Per-file git status (M/A/D/U) + branch, for VS-Code-style change decorations."""
    base = _ws_root(cid)
    if not base:
        return {"git": False, "status": {}}
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(base),
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return {"git": False, "status": {}, "staged": {}, "unstaged": {}}
        status: dict[str, str] = {}      # combined (for the Explorer badge)
        staged: dict[str, str] = {}      # index (X) column
        unstaged: dict[str, str] = {}    # working-tree (Y) column
        for line in r.stdout.splitlines():
            if len(line) < 4:
                continue
            x, y = line[0], line[1]
            f = line[3:].strip().strip('"')
            if " -> " in f:  # renamed
                f = f.split(" -> ")[-1]
            if x == "?" and y == "?":
                unstaged[f] = "U"
                status[f] = "U"
                continue
            if x not in (" ", "?"):
                staged[f] = x
            if y not in (" ", "?"):
                unstaged[f] = y
            status[f] = y if y not in (" ", "?") else x
        b = subprocess.run(
            ["git", "branch", "--show-current"], cwd=str(base),
            capture_output=True, text=True, timeout=10,
        )
        return {"git": True, "branch": b.stdout.strip(), "status": status, "staged": staged, "unstaged": unstaged}
    except Exception:  # noqa: BLE001
        return {"git": False, "status": {}, "staged": {}, "unstaged": {}}


@app.post("/api/git/stage")
async def git_stage(request: Request):
    payload = await request.json()
    base = _ws_root(payload.get("conversation_id") or payload.get("cid"))
    path = payload.get("path") or ""
    unstage = bool(payload.get("unstage"))
    if not base or not path:
        return JSONResponse({"error": "bad request"}, status_code=400)
    try:
        if unstage:
            r = subprocess.run(["git", "restore", "--staged", "--", path], cwd=str(base),
                               capture_output=True, text=True, timeout=20)
            if r.returncode != 0:  # older git without `restore`
                r = subprocess.run(["git", "reset", "-q", "HEAD", "--", path], cwd=str(base),
                                   capture_output=True, text=True, timeout=20)
        else:
            r = subprocess.run(["git", "add", "--", path], cwd=str(base),
                               capture_output=True, text=True, timeout=20)
        return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/git/commit")
async def git_commit(request: Request):
    """Stage everything and commit (from the Source Control panel)."""
    payload = await request.json()
    cid = payload.get("conversation_id") or payload.get("cid")
    message = (payload.get("message") or "").strip()
    base = _ws_root(cid)
    if not base:
        return JSONResponse({"error": "no workspace"}, status_code=400)
    if not message:
        return JSONResponse({"error": "commit message required"}, status_code=400)
    try:
        # Commit staged changes; if nothing is staged, stage everything first (VS Code behavior).
        has_staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=str(base), capture_output=True, text=True, timeout=20
        ).returncode != 0
        if not has_staged:
            subprocess.run(["git", "add", "-A"], cwd=str(base), capture_output=True, text=True, timeout=30)
        r = subprocess.run(
            ["git", "commit", "-m", message], cwd=str(base),
            capture_output=True, text=True, timeout=30,
        )
        return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/knowledge")
async def clear_knowledge():
    """Clear the GLOBAL 'about me' knowledge base (drops every indexed chunk).
    Per-chat workspaces and long-term memory are untouched."""
    try:
        from neura.knowledge_base import KnowledgeBase, DEFAULT_COLLECTION

        KnowledgeBase.drop(DEFAULT_COLLECTION)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True, "chunks": _kb_count()}


@app.post("/api/ingest")
async def ingest(request: Request):
    """Index local folders/files into a collection (global by default, or a chat's)."""
    payload = await request.json()
    paths = payload.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    paths = [p for p in paths if p and str(p).strip()]
    if not paths:
        return JSONResponse({"error": "provide one or more folder/file paths"}, status_code=400)
    collection = payload.get("collection") or None
    cid = payload.get("conversation_id")
    if cid and paths:
        store.set_workspace(cid, paths[0])
    report = await asyncio.to_thread(_ingest, paths, collection)
    return report


@app.post("/api/ingest/stream")
async def ingest_stream(request: Request):
    """Stream ingestion progress (scan → per-file chunking → done) as SSE events."""
    payload = await request.json()
    paths = payload.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    paths = [p for p in paths if p and str(p).strip()]
    if not paths:
        return JSONResponse({"error": "provide one or more folder/file paths"}, status_code=400)
    collection = payload.get("collection") or None
    cid = payload.get("conversation_id")
    if cid and paths:
        store.set_workspace(cid, paths[0])

    def gen():
        from neura.ingest_lib import iter_ingest

        try:
            for ev in iter_ingest(paths, collection=collection):
                yield _sse(ev)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"phase": "error", "message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream")


_ALLOWED_UPLOAD_EXT = {
    ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".hocon", ".cfg", ".ini", ".csv", ".html",
    ".css", ".sh", ".sql", ".java", ".go", ".rb", ".pdf",
}


def _safe_rel(name: str) -> str:
    """Sanitize a (possibly folder-relative) upload filename into a safe subpath."""
    parts = [p for p in Path(name.replace("\\", "/")).parts if p not in ("", ".", "..")]
    return "/".join(parts) or "upload"


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    """Upload individual files OR a whole folder (preserving structure), then index them.

    Folder uploads (webkitdirectory) send each file's relative path as its name; we keep
    that structure under data/uploads/ and skip unsupported/binary types.
    """
    updir = ROOT / "data" / "uploads"
    saved: list[str] = []
    skipped = 0
    for f in files:
        rel = _safe_rel(f.filename or "upload")
        if Path(rel).suffix.lower() not in _ALLOWED_UPLOAD_EXT:
            skipped += 1
            continue
        dest = updir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await f.read())
        saved.append(str(dest))
    # Return saved paths; the client then calls /api/ingest/stream to index with progress.
    return {"saved": saved, "skipped": skipped}


# ---------------------------------------------------------------- watcher
@app.post("/api/watch")
async def watch_start(request: Request):
    """Start watching a chat's workspace folder → auto re-index on change."""
    payload = await request.json()
    cid = payload.get("conversation_id")
    path = store.get_workspace(cid) if cid else ""
    if not path:
        return JSONResponse({"error": "this chat has no workspace folder yet"}, status_code=400)
    return watch_manager.start(cid, path, f"chat_{cid}")


@app.delete("/api/watch/{cid}")
async def watch_stop(cid: str) -> dict:
    watch_manager.stop(cid)
    return {"watching": False}


@app.get("/api/watch/{cid}")
async def watch_status(cid: str) -> dict:
    return watch_manager.status(cid)


# ---------------------------------------------------------------- networks
@app.get("/api/networks")
async def networks() -> dict:
    """List user-facing networks the runtime is serving, with friendly titles."""
    served: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{NEURA_SERVER_URL}/api/v1/list")
            served = [a.get("agent_name") for a in r.json().get("agents", [])]
    except Exception:  # noqa: BLE001
        pass
    db = {n["name"]: n for n in store.list_networks()}
    out = []
    for name in served:
        if name in HIDDEN_NETWORKS:
            continue
        rec = db.get(name)
        if BUILTIN_TITLES.get(name):
            title = BUILTIN_TITLES[name]
        elif rec:
            title = rec["title"]
        else:
            # e.g. "generated/meeting_notes" -> "Meeting Notes"
            title = name.split("/")[-1].replace("_", " ").title()
        out.append(
            {
                "name": name,
                "title": title,
                "description": rec["description"] if rec else "",
                "builtin": name in BUILTIN_TITLES,
                "spawned": name.startswith("generated/"),
            }
        )
    return {"networks": out}


def _network_details_map(name: str) -> dict:
    """Parse a network's HOCON for per-node detail (description, params, class,
    toolbox, model) so the graph nodes can show what each agent/tool does — the
    rich hover card alive shows. Best-effort: returns {} on any parse failure."""
    stem = name.split("/")[-1]
    hocon = spawn.GENERATED_DIR / f"{stem}.hocon"
    if not hocon.exists():
        hocon = spawn.ROOT / "registries" / f"{stem}.hocon"
    if not hocon.exists():
        return {}
    try:
        from pyhocon import ConfigFactory

        cwd = os.getcwd()
        os.chdir(str(spawn.ROOT))  # so relative `include` paths resolve
        try:
            conf = ConfigFactory.parse_file(str(hocon))
        finally:
            os.chdir(cwd)
    except Exception:  # noqa: BLE001
        return {}

    try:
        _lc = conf.get("llm_config", {})
        model = _lc.get("model_name", None) or _lc.get("model", None)
    except Exception:  # noqa: BLE001
        model = None
    if not model:
        # The network `include`s config/llm_config.hocon; read the model from there directly.
        try:
            from pyhocon import ConfigFactory as _CF

            llm = _CF.parse_file(str(spawn.ROOT / "config" / "llm_config.hocon")).get("llm_config", {})
            model = llm.get("model_name", None) or llm.get("model", None)
        except Exception:  # noqa: BLE001
            model = None

    out: dict = {}
    try:
        tools = conf.get("tools", []) or []
    except Exception:  # noqa: BLE001
        tools = []
    for t in tools:
        try:
            nm = t.get("name", None)
            if not nm:
                continue
            fn = t.get("function", {}) or {}
            desc = fn.get("description", None) or t.get("description", None) or ""
            params_props = (fn.get("parameters", {}) or {}).get("properties", {}) or {}
            required = set((fn.get("parameters", {}) or {}).get("required", []) or [])
            params = [
                {"name": p, "type": (params_props[p] or {}).get("type", "string"), "required": p in required}
                for p in params_props
            ]
            cls = t.get("class", None)
            toolbox = t.get("toolbox", None)
            is_agent = bool(t.get("instructions", None)) or (not cls and not toolbox)
            out[nm] = {
                "description": desc or None,
                "params": params or None,
                "class": cls,
                "toolbox": toolbox,
                "model": model if is_agent else None,
                "modelInherited": True if (is_agent and model) else None,
            }
        except Exception:  # noqa: BLE001
            continue
    return out


@app.get("/api/networks/{name:path}/graph")
async def network_graph(name: str) -> dict:
    """Return the agent-network graph (nodes + edges) from the runtime's connectivity."""
    info: list = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{NEURA_SERVER_URL}/api/v1/{name}/connectivity")
            info = r.json().get("connectivity_info", [])
    except Exception:  # noqa: BLE001
        pass
    nodes: list = []
    edges: list = []
    seen: set = set()
    for entry in info:
        origin = entry.get("origin")
        if not origin:
            continue
        if origin not in seen:
            nodes.append({"id": origin, "type": entry.get("display_as", "llm_agent")})
            seen.add(origin)
        for t in entry.get("tools", []):
            edges.append({"source": origin, "target": t})
    for e in edges:
        if e["target"] not in seen:
            nodes.append({"id": e["target"], "type": "external_agent"})
            seen.add(e["target"])
    front = info[0]["origin"] if info else name
    # `detail` feeds alive's detailToFlow (name/display_as/tools). Mark the front-man
    # as front_man and map external MCP servers to coded_tool (a leaf tool node).
    detail = []
    for entry in info:
        origin = entry.get("origin")
        if not origin:
            continue
        disp = entry.get("display_as", "llm_agent")
        if origin == front:
            disp = "front_man"
        elif disp == "external_agent":
            disp = "coded_tool"
        detail.append({"name": origin, "display_as": disp, "tools": entry.get("tools", [])})
    # Enrich with per-node detail parsed from the HOCON (description, params, class, model…).
    dmap = _network_details_map(name)
    for d in detail:
        extra = dmap.get(d["name"])
        if extra:
            for k, v in extra.items():
                if v is not None:
                    d[k] = v
    return {"front": front, "detail": detail, "nodes": nodes, "edges": edges}


@app.get("/api/networks/{name:path}/config")
async def get_network_config(name: str) -> dict:
    """Config the network needs (derived) + any values already saved."""
    rec = store.get_network(name)
    return {
        "name": name,
        "suggested": spawn.required_config(name),
        "config": (rec or {}).get("config", {}) or {},
    }


@app.post("/api/networks/{name:path}/config")
async def set_network_config(request: Request, name: str) -> dict:
    """Save connection strings for a spawned network to .env + DB, then reload runtime."""
    payload = await request.json()
    config = payload.get("config") or {}
    config = {k: v for k, v in config.items() if str(k).strip()}
    _write_env(config)
    rec = store.get_network(name)
    merged = {**((rec or {}).get("config", {}) or {}), **config}
    store.set_network_config(name, merged)
    _restart_runtime()
    return {"ok": True, "restarting": True}


@app.delete("/api/networks/{name:path}")
async def remove_network(name: str) -> dict:
    if name in BUILTIN_TITLES or name in HIDDEN_NETWORKS:
        return JSONResponse({"error": "cannot delete a built-in network"}, status_code=400)
    spawn.remove_network(name)
    return {"ok": True}


def _write_env(config: dict) -> None:
    if not config:
        return
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v
    for k, v in config.items():
        if v is not None and str(v) != "":
            existing[k] = str(v)
    lines = ["# Neura environment (managed; contains secrets — gitignored)"]
    lines += [f"{k}={v}" for k, v in existing.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV_FILE.chmod(0o600)


def _restart_runtime() -> None:
    subprocess.run(["pkill", "-f", "neuro_san.service.main_loop.server_main_loop"], check=False)
    subprocess.Popen(
        ["bash", str(ROOT / "scripts" / "run_server.sh")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(ROOT),
    )


# ------------------------------------------------------------------ LLM provider API
@app.get("/api/llm")
async def get_llm() -> dict:
    """Active provider/model + the model catalog and which API keys are already set.
    API key values are never returned — only whether each is configured."""
    models = _registry_models()
    active = _read_active_llm()
    providers = []
    for pid, p in LLM_PROVIDERS.items():
        providers.append(
            {
                "id": pid,
                "label": p["label"],
                "env_key": p["env_key"],
                "models": models.get(pid, []),
                "key_set": _env_has(p["env_key"]),
            }
        )
    # Fill in a sensible default model for the active provider if none is set.
    if not active.get("model"):
        opts = models.get(active["provider"], [])
        active["model"] = opts[0] if opts else None
    return {"active": active, "providers": providers}


@app.post("/api/llm")
async def set_llm(request: Request):
    """Switch the network's LLM: write config/llm_config.hocon, save the API key to
    .env (if provided), then reload the runtime so the new model takes effect."""
    payload = await request.json()
    provider = (payload.get("provider") or "").strip()
    model = (payload.get("model") or "").strip()
    api_key = (payload.get("api_key") or "").strip()

    if provider not in LLM_PROVIDERS:
        return JSONResponse({"error": f"unknown provider '{provider}'"}, status_code=400)
    if not _valid_model(provider, model):
        return JSONResponse(
            {"error": f"model '{model}' is not valid for {provider}"}, status_code=400
        )

    p = LLM_PROVIDERS[provider]
    # Require a key to be present (either newly supplied or already saved).
    if api_key:
        _write_env({p["env_key"]: api_key})
    elif not _env_has(p["env_key"]):
        return JSONResponse(
            {"error": f"{p['env_key']} is required for {p['label']}"}, status_code=400
        )

    _write_llm_config(provider, model)
    store.set_setting("llm", {"provider": provider, "model": model})
    _restart_runtime()
    return {"ok": True, "restarting": True, "provider": provider, "model": model}


# --------------------------------------------------------------------- spawn
@app.post("/api/spawn")
async def spawn_network(request: Request):
    """Drive the real agent_network_designer to build & serve a new network."""
    payload = await request.json()
    description = (payload.get("description") or "").strip()
    if not description:
        return JSONResponse({"error": "describe the capability"}, status_code=400)
    try:
        result = await spawn.spawn_via_designer(description)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)
    if result.get("status") != "created":
        return JSONResponse(result, status_code=502)
    return result


# ---------------------------------------------------------------- conversations
@app.get("/api/conversations")
async def list_conversations(network: str = "neura") -> dict:
    return {"conversations": store.list_conversations(network)}


@app.post("/api/conversations")
async def new_conversation(request: Request) -> dict:
    payload = {}
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        pass
    network = (payload or {}).get("network", "neura")
    cid = store.create_conversation(network=network)
    return {"id": cid, "title": "New conversation", "network": network}


@app.get("/api/conversations/{cid}")
async def get_conversation(cid: str):
    conv = store.get_conversation(cid)
    if not conv:
        return JSONResponse({"error": "not found"}, status_code=404)
    from neura import workflow_memory_lib as _wm

    return {
        "id": conv["id"],
        "title": conv["title"],
        "summary": conv["summary"],
        "workspace_path": conv.get("workspace_path", ""),
        "local_kb_chunks": _kb_count(f"chat_{cid}"),
        # Checklist now lives in the workflow JSON (alongside workflow memory), with the
        # SQLite column kept as a fallback for chats created before this change.
        "checklist": _wm.get_checklist(cid) or conv.get("checklist", []),
        "messages": conv["messages"],
    }


@app.post("/api/conversations/{cid}/reset")
async def reset_context(cid: str) -> dict:
    """Clear a chat's neuro-san multi-turn state (keeps the messages). Use when a long
    chat has drifted — the next turn starts fresh from the compacted summary."""
    store.set_context(cid, None)
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
async def delete_conversation(cid: str) -> dict:
    store.delete_conversation(cid)
    try:
        from neura.knowledge_base import KnowledgeBase

        KnowledgeBase.drop(f"chat_{cid}")  # remove this chat's local workspace index
    except Exception:  # noqa: BLE001
        pass
    try:
        from neura import workflow_memory_lib as _wm

        _wm.delete_all(cid)  # remove this workflow's memory + checklist JSON
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


# ---------------------------------------------------------------- chat
@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    payload = await request.json()
    message = (payload.get("message") or "").strip()
    conv_id = payload.get("conversation_id")
    sly_data = payload.get("sly_data") or {}
    mode = payload.get("mode", "strict")
    network = payload.get("network") or "neura"

    # Ensure a conversation exists.
    is_new = False
    if not conv_id or not store.get_conversation(conv_id):
        conv_id = store.create_conversation(_title_from(message), network=network)
        is_new = True
    store.add_message(conv_id, "user", message)
    if store.message_count(conv_id) == 1:
        store.rename_conversation(conv_id, _title_from(message))

    # Knowledge scoping: this chat's own index (local) + the global "about me" index.
    # knowledge_search reads these from sly_data and searches local-first.
    sly_data = {
        **sly_data,
        "knowledge_base": {"local_collection": f"chat_{conv_id}", "global_collection": "about_me"},
        # The chat's workspace folder (if any) — where the codebase sub-agent may read/edit/run.
        "workspace_path": store.get_workspace(conv_id) or "",
        # Scopes workflow_memory to THIS conversation (one JSON per workflow).
        "conversation_id": conv_id,
    }

    ctx = store.get_context(conv_id)

    # CONTEXT COMPACTION: once a chat gets long, stop replaying neuro-san's full multi-turn
    # state (which biases the model toward its own past tool-free turns). Instead drop it and
    # inject a compact "summary + last few turns" so the model stays focused and keeps using tools.
    compact_note = ""
    if network == "neura" and store.message_count(conv_id) > COMPACT_AFTER_MESSAGES:
        compact_note = _compacted_history(conv_id)
        if compact_note:
            ctx = None  # start the runtime fresh from the compact context

    # The Strict/Assist dial only shapes grounding for the built-in Neura network.
    send_message = message
    if network == "neura":
        if compact_note:
            send_message = f"{compact_note}\n\n{send_message}"
        # Fold the user's saved personal profile into every Neura turn so it always
        # remembers who it's assisting (stored in the DB, not stuffed into the vector DB).
        preface = _profile_preface(store.get_profile())
        if preface:
            send_message = f"{preface}\n\n{send_message}"
        # Fold ALL of Neura's long-term memory into every turn — guarantees grounding
        # in the user's specific facts without relying on the model to call the tool.
        mem_preface = await _memory_preface()
        if mem_preface:
            send_message = f"{mem_preface}\n\n{send_message}"
        # Fold in THIS workflow's captured details (ticket, branch, PR, decisions) so a
        # long multi-step task keeps them even after context compaction.
        try:
            from neura import workflow_memory_lib as _wm

            wf_preface = _wm.preface(conv_id)
            if wf_preface:
                send_message = f"{wf_preface}\n\n{send_message}"
        except Exception:  # noqa: BLE001
            pass
        if mode == "strict":
            send_message = send_message + (
                "\n\n(Strict mode: use my own data and connected tools — knowledge_search AND "
                "connected integrations like github — but do NOT use web search or general world "
                "knowledge. If something isn't in my data or reachable via my tools, say so.)"
            )
        else:
            send_message = send_message + (
                "\n\n(Assist mode: use my data, connected tools (github, etc.), web search, and "
                "general knowledge. Make clear which parts come from my data/tools vs the web.)"
            )
        # Per-turn grounding reminder — kept LAST so it stays influential even in long chats
        # where the model might otherwise pattern-match on earlier tool-free turns.
        send_message = send_message + (
            "\n\n(Reminder: to actually DO anything — run a command or code, read/edit/create a "
            "file, use git, or reach GitHub/Jira/Confluence/Slack/Teams/Outlook/Figma, or compute "
            "a result — you MUST call the matching tool THIS turn and use its real returned output. "
            "Never answer such requests from conversation history, and never fabricate command "
            "output, file writes, byte counts, diffs, or 'done' confirmations you didn't get from a "
            "tool this turn.)"
        )

    title = store.get_conversation(conv_id)["title"]

    async def event_stream():
        yield _sse({"type": "conversation", "id": conv_id, "title": title, "new": is_new})
        answer = ""
        sources: list = []
        new_ctx = None
        suggested = None
        # Seed the task-plan from what this conversation already had, so a follow-up
        # message continues the SAME checklist instead of restarting it. New steps get
        # appended (see _apply_checklist create_checklist merge); statuses are preserved.
        from neura import workflow_memory_lib as _wm

        checklist: list = _wm.get_checklist(conv_id)
        if checklist:
            yield _sse({"type": "checklist", "items": checklist})
        trace_log: list = []  # agent-to-agent talk for this answer (the "thinking")
        cmd_log: list = []    # shell commands the codebase agent ran (terminal cards)
        front = None          # front-man name (root of the origin path)
        try:
            async for frame in nsclient.stream_frames(network, send_message, ctx, sly_data or None):
                r = frame.get("response", {}) or {}
                rtype = r.get("type")
                text = r.get("text") or ""
                # Origin path: [front-man, …, deepest active agent/tool].
                origin = r.get("origin")
                path = []
                if isinstance(origin, list) and origin:
                    path = [o.get("tool") for o in origin if isinstance(o, dict) and o.get("tool")]
                if path:
                    if front is None:
                        front = path[0]
                    yield _sse({"type": "trace", "node": path[-1], "path": path})
                agent = path[-1] if path else (front or network)

                # Task-plan (checklist middleware) + progress, carried on the frame's structure.
                struct = r.get("structure")
                if isinstance(struct, dict):
                    if isinstance(struct.get("progress"), (int, float)):
                        yield _sse({"type": "progress", "value": float(struct["progress"])})
                    name = struct.get("invoked_agent_name")
                    params = struct.get("params") or {}
                    if name in ("create_checklist", "update_checklist_item", "edit_checklist_item"):
                        await _apply_checklist(checklist, name, params)
                        yield _sse({"type": "checklist", "items": checklist})

                if rtype == "AGENT_TOOL_RESULT":
                    s = nsclient.parse_sources(text)
                    if s:
                        sources = s
                        yield _sse({"type": "sources", "items": s})
                    # A sub-agent/tool returned something. A shell command run → terminal
                    # card; anything else → agent-to-agent trace.
                    if text.strip():
                        cmd = _parse_command(text)
                        if cmd:
                            cmd_log.append(cmd)
                            yield _sse({"type": "command", **cmd})
                        else:
                            msg = {"agent": agent, "path": path, "kind": "result", "text": _trim(text)}
                            trace_log.append(msg)
                            yield _sse({"type": "agent_message", **msg})
                elif rtype == "AGENT" and text:
                    # An agent narrating its work — the agent-to-agent talk (skip framework plumbing).
                    if not _is_plumbing(text):
                        msg = {"agent": agent, "path": path, "kind": "say", "text": _trim(text, 1400)}
                        trace_log.append(msg)
                        yield _sse({"type": "agent_message", **msg})
                        yield _sse({"type": "activity", "agent": agent, "text": _trim(text, 90)})
                elif rtype in ("AI", "AGENT_FRAMEWORK") and text:
                    # The chat bubble only shows the FRONT-MAN's final reply. Sub-agent
                    # replies (deeper origin) become agent-to-agent trace, not the answer.
                    is_front = (not path) or (len(path) <= 1) or (path[-1] == front)
                    if is_front:
                        clean, desc = _extract_build(text)
                        answer = clean
                        yield _sse({"type": "answer", "text": clean})
                        if desc and not suggested:
                            suggested = desc
                            yield _sse({"type": "suggest_build", "description": desc})
                    else:
                        msg = {"agent": agent, "path": path, "kind": "say", "text": _trim(text, 1400)}
                        trace_log.append(msg)
                        yield _sse({"type": "agent_message", **msg})
                if isinstance(r, dict) and r.get("chat_context"):
                    new_ctx = r["chat_context"]

            if answer or suggested:
                store.add_message(conv_id, "ai", answer, sources, build=suggested or "",
                                  trace=trace_log[-60:], commands=cmd_log[-30:])
            if new_ctx is not None:
                store.set_context(conv_id, new_ctx)
            if checklist:
                _wm.set_checklist(conv_id, checklist)

            # Auto-capture salient identifiers (Jira keys, PR/commit/resource URLs, branch
            # names) from the answer + the commands that ran, into this workflow's memory.
            # Cheap regex, no LLM cost; complements what the model saved via the tool.
            try:
                from neura import workflow_memory_lib as _wm

                blob = answer + "\n" + "\n".join(
                    f"{c.get('command','')} {c.get('output','')}" for c in cmd_log
                )
                added = _wm.auto_capture(conv_id, blob, title=title)
                if added:
                    yield _sse({"type": "workflow_memory", "added": added})
            except Exception:  # noqa: BLE001
                pass

            summary = await compress.maybe_compress(conv_id)
            if summary:
                yield _sse({"type": "summary", "text": summary})

            yield _sse({"type": "done", "conversation_id": conv_id})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "text": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------- voice
@app.post("/api/tts")
async def tts(request: Request) -> Response:
    payload = await request.json()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{TTS_URL}/api/tts", json=payload)
            return Response(content=r.content, media_type=r.headers.get("content-type", "audio/wav"))
    except Exception as exc:  # noqa: BLE001
        return Response(content=f"TTS unavailable: {exc}", status_code=503)


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿️]"
)


def _speechify_fallback(text: str) -> str:
    """Deterministic clean-up when the LLM rewrite isn't available — mirrors the
    frontend cleanForSpeech so nothing unreadable ever reaches TTS."""
    t = re.sub(r"```[\s\S]*?```|`[^`]*`", " ", text)      # code
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)           # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)        # links → label
    t = re.sub(r"https?://\S+", " ", t)                   # bare URLs
    t = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", t, flags=re.M)  # list markers
    t = re.sub(r"^\s{0,3}#{1,6}\s+", "", t, flags=re.M)   # headings
    t = re.sub(r"[*_~>#|]", "", t)                        # stray symbols
    t = _EMOJI_RE.sub("", t)                              # emoji
    t = re.sub(r"\n+", ". ", t)
    t = re.sub(r"\.\s*(?:\.\s*)+", ". ", t)               # collapse periods
    t = re.sub(r"\s+([.,!?;:])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:1200]


@app.post("/api/speechify")
async def speechify(request: Request) -> dict:
    """Rewrite an assistant reply into a short, natural SPOKEN version for TTS —
    summarised, conversational, with no markdown/symbols/code/URLs."""
    payload = await request.json()
    text = (payload.get("text") or "").strip()
    if not text:
        return {"text": ""}
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or len(text) < 160:
        # Short answers don't need summarising — just clean them.
        return {"text": _speechify_fallback(text)}
    prompt = (
        "Rewrite the assistant reply below as a short, natural SPOKEN version for "
        "text-to-speech. Rules: conversational plain sentences; summarise to the key "
        "points in at most 4 short sentences; NO markdown, bullet points, symbols, code, "
        "or URLs; don't spell out links; first person as the assistant. Output ONLY the "
        "spoken text.\n\nREPLY:\n" + text
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            data = r.json()
            spoken = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ).strip()
            return {"text": spoken or _speechify_fallback(text)}
    except Exception:  # noqa: BLE001
        return {"text": _speechify_fallback(text)}


@app.get("/api/voices")
async def voices() -> Response:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{TTS_URL}/api/voices")
            return Response(content=r.content, media_type="application/json")
    except Exception:  # noqa: BLE001
        return Response(content=json.dumps({"voices": []}), media_type="application/json")


# ---------------------------------------------------------------- static UI
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
