"""Neura CodedTool: operate on the current chat's local codebase (workspace).

The chat's workspace folder — the same folder indexed for per-chat knowledge and
watched for auto-re-index — arrives via `sly_data["workspace_path"]` (kept out of the
LLM prompt). Every file path is confined to that folder: reads, writes, edits, and
shell commands cannot escape it (no absolute paths, no `..` traversal, `run` uses the
workspace as its working directory).

Reads (`list`, `read`, `search`) are safe and run freely. Mutations (`write`, `edit`,
`run`) are executed when called — the HUMAN APPROVAL GATE is enforced by the `codebase`
sub-agent's instructions, which must get an explicit yes before invoking them.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

MAX_READ_BYTES = 200_000
MAX_OUTPUT_CHARS = 20_000
RUN_TIMEOUT = 120
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", ".cache", ".idea", ".vscode", ".mypy_cache", ".pytest_cache"}


class CodebaseTool(CodedTool):
    """Read, edit, and run commands inside this chat's workspace folder."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        # Operate on an explicit `root` (an absolute repo/dir path) if given, else on
        # this chat's indexed workspace. This lets Neura edit a repo the user names
        # even when it isn't indexed as the chat's folder.
        root_str = (args.get("root") or (sly_data or {}).get("workspace_path") or "").strip()
        if not root_str:
            return ("No target folder. Either index a folder as this chat's workspace, or pass "
                    "`root` = the absolute path of the repo/directory to work in.")
        root = Path(root_str).expanduser().resolve()
        if not root.is_dir():
            return f"Workspace folder no longer exists: {root}"

        action = (args.get("action") or "").strip().lower()
        rel = (args.get("path") or "").strip()

        def resolve(p: str) -> Path:
            """Resolve a workspace-relative path, refusing anything outside root."""
            if not p:
                return root
            cand = (root / p).resolve() if not os.path.isabs(p) else Path(p).resolve()
            if cand != root and root not in cand.parents:
                raise ValueError(f"path '{p}' is outside the workspace; refused.")
            return cand

        try:
            if action == "list":
                return self._list(resolve(rel), root)
            if action == "read":
                return self._read(resolve(rel), root, args)
            if action == "search":
                return self._search(root, args)
            if action == "find":
                return self._find(root, args)
            if action == "write":
                return self._write(resolve(rel), root, args)
            if action == "edit":
                return self._edit(resolve(rel), root, args)
            if action == "run":
                return self._run(root, args)
        except ValueError as e:
            return f"Refused: {e}"
        except Exception as e:  # noqa: BLE001
            return f"Error during '{action}': {e}"
        return ("Unknown action. Use one of: list, find, read, search, write, edit, run.")

    # ---- reads -------------------------------------------------------------
    def _list(self, target: Path, root: Path) -> str:
        if target.is_file():
            return f"{target.relative_to(root)} (file, {target.stat().st_size} bytes)"
        if not target.is_dir():
            return f"Not found: {target.relative_to(root) if target != root else '.'}"
        entries: List[str] = []
        for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if p.name.startswith(".") or p.name in SKIP_DIRS:
                continue
            rel = p.relative_to(root)
            entries.append(f"{rel}/" if p.is_dir() else f"{rel}")
        loc = target.relative_to(root) if target != root else "."
        if not entries:
            return f"{loc}/ is empty (or only hidden/ignored files)."
        return f"Contents of {loc}/:\n" + "\n".join(entries[:400])

    def _read(self, target: Path, root: Path, args: Dict[str, Any]) -> str:
        if not target.is_file():
            return f"Not a file: {target.relative_to(root) if target != root else '.'}"
        data = target.read_bytes()[:MAX_READ_BYTES]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"{target.relative_to(root)} is a binary file; cannot read as text."
        lines = text.splitlines()
        start = _int(args.get("start"), 1)
        count = _int(args.get("max_lines"), 0)
        if start > 1 or count:
            end = start - 1 + count if count else len(lines)
            shown = lines[start - 1:end]
            body = "\n".join(f"{start + i}\t{ln}" for i, ln in enumerate(shown))
            head = f"{target.relative_to(root)} (lines {start}-{start - 1 + len(shown)} of {len(lines)}):\n"
        else:
            body = "\n".join(f"{i + 1}\t{ln}" for i, ln in enumerate(lines))
            head = f"{target.relative_to(root)} ({len(lines)} lines):\n"
        return _cap(head + body)

    def _find(self, root: Path, args: Dict[str, Any]) -> str:
        """Locate files by name/glob — returns PATHS ONLY (cheap; no file contents).
        Use this to resolve 'the X file' to a path before reading, instead of grepping."""
        import fnmatch

        pattern = (args.get("query") or args.get("path") or "").strip()
        if not pattern:
            return "Provide 'query' = a filename or glob, e.g. 'UserService.ts' or '*.hocon'."
        low = pattern.lower()
        hits: List[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                if fnmatch.fnmatch(fn, pattern) or low in fn.lower():
                    hits.append(str(Path(dirpath, fn).relative_to(root)))
                    if len(hits) >= 200:
                        break
            if len(hits) >= 200:
                break
        if not hits:
            return f"No files matching '{pattern}'."
        hits.sort(key=lambda h: (h.count("/"), len(h)))  # shallowest / shortest first
        return f"{len(hits)} file(s) matching '{pattern}':\n" + "\n".join(hits[:100])

    def _search(self, root: Path, args: Dict[str, Any]) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "Provide a 'query' to search for."
        try:
            proc = subprocess.run(
                ["grep", "-rniI", "--line-number"] +
                [f"--exclude-dir={d}" for d in SKIP_DIRS] +
                [query, "."],
                cwd=str(root), capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            return "grep is not available on this system."
        except subprocess.TimeoutExpired:
            return "Search timed out."
        out = proc.stdout.strip()
        if not out:
            return f"No matches for '{query}'."
        hits = out.splitlines()
        head = f"{len(hits)} match(es) for '{query}':\n"
        return _cap(head + "\n".join(hits[:200]))

    # ---- mutations (human-gated by the sub-agent) --------------------------
    def _write(self, target: Path, root: Path, args: Dict[str, Any]) -> str:
        content = args.get("content")
        if content is None:
            return "Provide 'content' to write."
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        n = str(content).count("\n") + 1
        verb = "Overwrote" if existed else "Created"
        return f"{verb} {target.relative_to(root)} ({n} lines, {len(str(content))} bytes)."

    def _edit(self, target: Path, root: Path, args: Dict[str, Any]) -> str:
        if not target.is_file():
            return f"Not a file: {target.relative_to(root) if target != root else '.'}"
        old = args.get("old")
        new = args.get("new")
        if old is None or new is None:
            return "Provide both 'old' (exact text to replace) and 'new'."
        old, new = str(old), str(new)
        text = target.read_text(encoding="utf-8", errors="replace")
        count = text.count(old)
        if count == 0:
            return "The 'old' text was not found exactly; nothing changed. Re-read the file and match exactly."
        if count > 1:
            return (f"The 'old' text appears {count} times — it must be unique. "
                    "Include more surrounding context so it matches exactly once.")
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"Edited {target.relative_to(root)} (1 replacement)."

    def _run(self, root: Path, args: Dict[str, Any]) -> str:
        command = (args.get("command") or "").strip()
        if not command:
            return "Provide a 'command' to run."
        try:
            proc = subprocess.run(
                command, shell=True, cwd=str(root),
                capture_output=True, text=True, timeout=RUN_TIMEOUT,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.TimeoutExpired:
            return f"Command timed out after {RUN_TIMEOUT}s: {command}"
        parts = [f"$ {command}", f"(exit code {proc.returncode})"]
        if proc.stdout.strip():
            parts.append("--- stdout ---\n" + proc.stdout.rstrip())
        if proc.stderr.strip():
            parts.append("--- stderr ---\n" + proc.stderr.rstrip())
        if not proc.stdout.strip() and not proc.stderr.strip():
            parts.append("(no output)")
        return _cap("\n".join(parts))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)


def _int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _cap(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n… (truncated at {MAX_OUTPUT_CHARS} chars)"
