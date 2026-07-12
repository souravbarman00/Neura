"""Workflow memory — per-conversation JSON store.

Each workflow (= one conversation) gets ONE JSON file at
    <repo>/data/workflow_memory/<conversation_id>.json

holding the important details captured while Neura runs a long, multi-step task
(ticket keys, branch names, PR/commit URLs, decisions, resource IDs, user notes).
It is kept OUT of the global "about the user" memory so it stays scoped to the
task and can be deleted wholesale when the workflow is done.

Pure stdlib so it can be imported by both the neuro-san coded tool
(coded_tools.neura.workflow_memory_tool) and the FastAPI backend.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# <repo>/coded_tools/neura/workflow_memory_lib.py -> repo root is parents[2]
_ROOT = Path(__file__).resolve().parents[2]
_DIR = _ROOT / "data" / "workflow_memory"

MAX_ENTRIES = 300  # safety cap per workflow


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(conv_id: str) -> Path:
    # conv_id is a hex id from the app; keep the filename safe regardless.
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(conv_id or "").strip()) or "unknown"
    return _DIR / f"{safe}.json"


def load(conv_id: str) -> Dict[str, Any]:
    """Return the workflow's memory doc (empty scaffold if none yet)."""
    p = _path(conv_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — corrupt file: start fresh, don't crash
            pass
    return {"conversation_id": conv_id, "title": "", "created": None, "updated": None, "entries": []}


def _save(doc: Dict[str, Any]) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    doc["updated"] = _now()
    _path(doc["conversation_id"]).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def add(
    conv_id: str,
    value: str,
    key: str = "note",
    source: str = "model",
    title: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Append one entry. Skips exact (key,value) duplicates. Returns the entry, or
    None if it was a duplicate / empty."""
    value = (value or "").strip()
    key = (key or "note").strip() or "note"
    if not value:
        return None
    doc = load(conv_id)
    if title and not doc.get("title"):
        doc["title"] = title
    if doc.get("created") is None:
        doc["created"] = _now()
    for e in doc["entries"]:
        if e.get("key", "").lower() == key.lower() and e.get("value", "").strip() == value:
            return None  # already remembered
    entry = {"id": uuid.uuid4().hex[:12], "key": key, "value": value, "source": source, "ts": _now()}
    doc["entries"].append(entry)
    doc["entries"] = doc["entries"][-MAX_ENTRIES:]
    _save(doc)
    return entry


def get_checklist(conv_id: str) -> List[Dict[str, Any]]:
    """The workflow's task-plan, stored alongside its memory in the same JSON."""
    return list(load(conv_id).get("checklist") or [])


def set_checklist(conv_id: str, items: List[Dict[str, Any]]) -> None:
    doc = load(conv_id)
    if doc.get("created") is None:
        doc["created"] = _now()
    doc["checklist"] = items or []
    _save(doc)


def delete_entry(conv_id: str, entry_id: str) -> bool:
    doc = load(conv_id)
    before = len(doc["entries"])
    doc["entries"] = [e for e in doc["entries"] if e.get("id") != entry_id]
    if len(doc["entries"]) == before:
        return False
    _save(doc)
    return True


def delete_all(conv_id: str) -> bool:
    """Delete the whole workflow's memory file (user control once it's done)."""
    p = _path(conv_id)
    if p.exists():
        p.unlink()
        return True
    return False


# --- automatic identifier capture -------------------------------------------
_JIRA_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+")
# Branch names only from explicit command forms or git's quoted output — NOT the bare
# word "branch" in prose (which produced false positives like "on branch checkout").
_BRANCH_RE = re.compile(
    r"(?:checkout -b|switch -c|--branch[ =])\s*([A-Za-z0-9._/\-]+)"
    r"|branch ['\"]([A-Za-z0-9._/\-]+)['\"]"
)
_RESOURCEY = ("github.com", "atlassian.net", "/browse/", "figma.com", "slack.com", "/pull/", "/commit/")


def auto_capture(conv_id: str, text: str, title: Optional[str] = None) -> List[Dict[str, Any]]:
    """Cheap, no-LLM scrape of salient identifiers from an answer + command output.
    Captures Jira keys, resource URLs (github/jira/figma/slack, PRs, commits), and
    git branch names. Returns the entries actually added."""
    text = text or ""
    added: List[Dict[str, Any]] = []

    def _add(v: str, k: str):
        e = add(conv_id, v, key=k, source="auto", title=title)
        if e:
            added.append(e)

    for m in set(_JIRA_RE.findall(text)):
        _add(m, "jira")
    for u in set(_URL_RE.findall(text)):
        if any(tok in u.lower() for tok in _RESOURCEY):
            _add(u.rstrip(".,"), "link")
    for g1, g2 in _BRANCH_RE.findall(text):
        b = g1 or g2
        if b and b not in ("main", "master", "HEAD"):
            _add(b, "branch")
    return added


def preface(conv_id: str) -> str:
    """A compact grounding block of this workflow's remembered facts, injected at the
    top of every turn so long workflows don't lose track after context compaction."""
    doc = load(conv_id)
    entries = doc.get("entries") or []
    if not entries:
        return ""
    lines = ["(THIS WORKFLOW'S MEMORY — important details captured for this task; treat as ground truth:"]
    for e in entries:
        lines.append(f"  - [{e.get('key','note')}] {e.get('value','')}")
    lines.append("Use these directly; don't re-derive or re-ask for them.)")
    return "\n".join(lines)
