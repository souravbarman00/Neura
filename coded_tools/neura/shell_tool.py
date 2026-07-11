"""Neura CodedTool: run an arbitrary shell command on the user's machine.

This is the general-purpose terminal (unlike codebase_op, which is confined to a
chat's workspace). It can create directories, run scripts, install packages, use
git/gh/az/gcloud, etc. Every run is HUMAN-APPROVED by the `terminal` sub-agent's
instructions before it executes.

Output is returned in the same "$ <cmd>\\n(exit code N)\\n--- stdout ---\\n…" shape
the codebase runner uses, so the UI renders it as a terminal card.

Interactive commands (that wait for typed input or a browser login) don't work here
because output is captured non-interactively — for those, tell the user to run them
themselves with `! <command>` in the session.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600

# Obvious foot-guns are refused outright even after approval, as a safety backstop.
_DENY = (
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/",
    ":(){:|:&};:",
    "mkfs",
    "> /dev/sd",
    "of=/dev/sd",
    "of=/dev/disk",
    "shutdown",
    "reboot",
    "chmod -r 000 /",
)


class ShellRun(CodedTool):
    """Run a shell command and return its stdout/stderr and exit code."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        command = (args.get("command") or "").strip()
        if not command:
            return "Provide a 'command' to run."

        low = command.lower()
        if any(bad in low for bad in _DENY):
            return f"Refused: '{command}' looks destructive and was blocked as a safety backstop."

        cwd = (args.get("cwd") or "").strip()
        workdir = Path(cwd).expanduser() if cwd else Path.home()
        try:
            workdir = workdir.resolve()
        except Exception:  # noqa: BLE001
            pass
        if not workdir.is_dir():
            return f"Working directory does not exist: {workdir}"

        try:
            timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout,
                # Keep git/gh/az from blocking on an interactive credential prompt.
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "DEBIAN_FRONTEND": "noninteractive"},
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return (
                f"$ {command}\n(timed out after {timeout}s)\n"
                "If this command is interactive (waits for input or a browser login), it can't run "
                "here — ask the user to run it themselves with `! " + command + "`."
            )
        except Exception as exc:  # noqa: BLE001
            return f"$ {command}\n(error) {exc}"

        parts = [f"$ {command}", f"(exit code {proc.returncode})"]
        if proc.stdout.strip():
            parts.append("--- stdout ---\n" + proc.stdout.rstrip())
        if proc.stderr.strip():
            parts.append("--- stderr ---\n" + proc.stderr.rstrip())
        if not proc.stdout.strip() and not proc.stderr.strip():
            parts.append("(no output)")
        out = "\n".join(parts)
        if len(out) > MAX_OUTPUT_CHARS:
            out = out[:MAX_OUTPUT_CHARS] + f"\n… (truncated at {MAX_OUTPUT_CHARS} chars)"
        return out

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)
