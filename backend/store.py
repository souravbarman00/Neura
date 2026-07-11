"""SQLite-backed conversation store for Neura.

Persists every conversation and message, plus a rolling **compressed summary**
produced by the `memory_compressor` agent network (see compress.py). Recent turns
are kept verbatim; older turns are folded into the summary — the same
recent-verbatim + older-summarized approach a chat assistant uses to keep long
histories manageable.

Timestamps are epoch seconds. `chat_context` (neuro-san multi-turn state) and
`sources` are stored as JSON text.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "neura.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id            TEXT PRIMARY KEY,
                title         TEXT NOT NULL,
                network       TEXT NOT NULL DEFAULT 'neura',
                created       REAL NOT NULL,
                updated       REAL NOT NULL,
                summary       TEXT DEFAULT '',
                summarized_upto INTEGER DEFAULT 0,   -- # of messages folded into summary
                chat_context  TEXT DEFAULT ''         -- JSON neuro-san context
            );
            CREATE TABLE IF NOT EXISTS messages (
                id            TEXT PRIMARY KEY,
                conv_id       TEXT NOT NULL,
                role          TEXT NOT NULL,
                text          TEXT NOT NULL,
                sources       TEXT DEFAULT '',
                build         TEXT DEFAULT '',   -- capability desc if Neura suggested building
                created       REAL NOT NULL,
                FOREIGN KEY (conv_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id, created);

            -- Registry of dynamically-spawned agent networks.
            CREATE TABLE IF NOT EXISTS networks (
                name          TEXT PRIMARY KEY,   -- served network name (e.g. github_agent)
                title         TEXT NOT NULL,       -- friendly label
                description   TEXT DEFAULT '',
                hocon_path    TEXT DEFAULT '',
                config        TEXT DEFAULT '',     -- JSON: filled config values (secrets)
                created       REAL NOT NULL
            );

            -- Simple key/value app settings (e.g. the user's personal profile as JSON).
            CREATE TABLE IF NOT EXISTS settings (
                key           TEXT PRIMARY KEY,
                value         TEXT DEFAULT ''
            );
            """
        )
        # Lightweight migration: add conversations.network if an older DB predates it.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(conversations)").fetchall()}
        if "network" not in cols:
            c.execute("ALTER TABLE conversations ADD COLUMN network TEXT NOT NULL DEFAULT 'neura'")
        mcols = {r["name"] for r in c.execute("PRAGMA table_info(messages)").fetchall()}
        if "build" not in mcols:
            c.execute("ALTER TABLE messages ADD COLUMN build TEXT DEFAULT ''")
        if "trace" not in mcols:
            c.execute("ALTER TABLE messages ADD COLUMN trace TEXT DEFAULT ''")
        if "commands" not in mcols:
            c.execute("ALTER TABLE messages ADD COLUMN commands TEXT DEFAULT ''")
        if "workspace_path" not in cols:
            c.execute("ALTER TABLE conversations ADD COLUMN workspace_path TEXT DEFAULT ''")
        if "checklist" not in cols:
            c.execute("ALTER TABLE conversations ADD COLUMN checklist TEXT DEFAULT ''")


def create_conversation(title: str = "New conversation", network: str = "neura") -> str:
    cid = uuid.uuid4().hex[:12]
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO conversations (id, title, network, created, updated) VALUES (?,?,?,?,?)",
            (cid, title[:120], network, now, now),
        )
    return cid


def rename_conversation(cid: str, title: str) -> None:
    with _conn() as c:
        c.execute("UPDATE conversations SET title=?, updated=? WHERE id=?", (title[:120], time.time(), cid))


def list_conversations(network: Optional[str] = None) -> list[dict[str, Any]]:
    q = """
        SELECT c.id, c.title, c.network, c.updated,
               (SELECT COUNT(*) FROM messages m WHERE m.conv_id = c.id) AS count
        FROM conversations c
    """
    params: tuple = ()
    if network:
        q += " WHERE c.network = ?"
        params = (network,)
    q += " ORDER BY c.updated DESC"
    with _conn() as c:
        rows = c.execute(q, params).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ networks
def add_network(name: str, title: str, description: str, hocon_path: str, config: Optional[dict]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO networks (name, title, description, hocon_path, config, created) "
            "VALUES (?,?,?,?,?,?)",
            (name, title, description, hocon_path, json.dumps(config or {}), time.time()),
        )


def list_networks() -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT name, title, description, created FROM networks ORDER BY created").fetchall()
    return [dict(r) for r in rows]


def get_network(name: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM networks WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["config"] = json.loads(out["config"]) if out["config"] else {}
    return out


def set_network_config(name: str, config: dict) -> None:
    with _conn() as c:
        row = c.execute("SELECT name FROM networks WHERE name=?", (name,)).fetchone()
        if row:
            c.execute("UPDATE networks SET config=? WHERE name=?", (json.dumps(config or {}), name))
        else:
            title = name.split("/")[-1].replace("_", " ").title()
            c.execute(
                "INSERT INTO networks (name, title, description, hocon_path, config, created) "
                "VALUES (?,?,?,?,?,?)",
                (name, title, "", "", json.dumps(config or {}), time.time()),
            )


def delete_network(name: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM networks WHERE name=?", (name,))


def get_conversation(cid: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        msgs = c.execute(
            "SELECT id, role, text, sources, build, trace, commands, created FROM messages WHERE conv_id=? ORDER BY created",
            (cid,),
        ).fetchall()
    out = dict(row)
    out["workspace_path"] = (row["workspace_path"] if "workspace_path" in row.keys() else "") or ""
    cl_raw = (row["checklist"] if "checklist" in row.keys() else "") or ""
    out["checklist"] = json.loads(cl_raw) if cl_raw else []
    out["messages"] = [
        {
            "id": m["id"],
            "role": m["role"],
            "text": m["text"],
            "sources": json.loads(m["sources"]) if m["sources"] else [],
            "build": (m["build"] if "build" in m.keys() else "") or "",
            "trace": json.loads(m["trace"]) if ("trace" in m.keys() and m["trace"]) else [],
            "commands": json.loads(m["commands"]) if ("commands" in m.keys() and m["commands"]) else [],
        }
        for m in msgs
    ]
    return out


def add_message(
    cid: str, role: str, text: str, sources: Optional[list] = None, build: str = "",
    trace: Optional[list] = None, commands: Optional[list] = None,
) -> str:
    mid = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO messages (id, conv_id, role, text, sources, build, trace, commands, created) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, cid, role, text, json.dumps(sources or []), build or "",
             json.dumps(trace or []), json.dumps(commands or []), time.time()),
        )
        c.execute("UPDATE conversations SET updated=? WHERE id=?", (time.time(), cid))
    return mid


def set_workspace(cid: str, path: str) -> None:
    with _conn() as c:
        c.execute("UPDATE conversations SET workspace_path=? WHERE id=?", (path, cid))


def set_checklist(cid: str, items: list) -> None:
    """Persist the latest task-plan checklist for a conversation."""
    with _conn() as c:
        c.execute("UPDATE conversations SET checklist=? WHERE id=?", (json.dumps(items or []), cid))


def get_setting(key: str, default: Any = None) -> Any:
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row or not row["value"]:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return default


def set_setting(key: str, value: Any) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )


def get_profile() -> dict:
    """The user's personal profile (what Neura should always remember about them)."""
    return get_setting("profile", {}) or {}


def set_profile(profile: dict) -> None:
    set_setting("profile", profile)


def get_workspace(cid: str) -> str:
    with _conn() as c:
        row = c.execute("SELECT workspace_path FROM conversations WHERE id=?", (cid,)).fetchone()
    return (row["workspace_path"] if row and "workspace_path" in row.keys() else "") or ""


def get_context(cid: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT chat_context FROM conversations WHERE id=?", (cid,)).fetchone()
    if row and row["chat_context"]:
        try:
            return json.loads(row["chat_context"])
        except json.JSONDecodeError:
            return None
    return None


def set_context(cid: str, ctx: Optional[dict]) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE conversations SET chat_context=? WHERE id=?",
            (json.dumps(ctx) if ctx else "", cid),
        )


def message_count(cid: str) -> int:
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM messages WHERE conv_id=?", (cid,)).fetchone()
    return row["n"] if row else 0


def get_summary_state(cid: str) -> tuple[str, int]:
    with _conn() as c:
        row = c.execute("SELECT summary, summarized_upto FROM conversations WHERE id=?", (cid,)).fetchone()
    if not row:
        return "", 0
    return row["summary"] or "", row["summarized_upto"] or 0


def messages_after(cid: str, offset: int) -> list[dict[str, Any]]:
    """Return messages beyond the first `offset` (oldest-first), for compression."""
    with _conn() as c:
        rows = c.execute(
            "SELECT role, text FROM messages WHERE conv_id=? ORDER BY created LIMIT -1 OFFSET ?",
            (cid, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def set_summary(cid: str, summary: str, summarized_upto: int) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE conversations SET summary=?, summarized_upto=? WHERE id=?",
            (summary, summarized_upto, cid),
        )


def delete_conversation(cid: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM messages WHERE conv_id=?", (cid,))
        c.execute("DELETE FROM conversations WHERE id=?", (cid,))
