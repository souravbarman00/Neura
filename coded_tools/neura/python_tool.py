"""Neura CodedTool: run Python in an isolated temp dir to GROUND results.

Instead of computing/guessing in its head, Neura writes Python, this tool drops it
into a fresh temp directory, runs it with the same interpreter the app uses, and
returns the real stdout/stderr + exit code. Use it to calculate, parse/transform
data, count, check math/dates, or verify a claim — the output is real, not invented.

Output uses the "$ python main.py …" shape so the UI renders it as a terminal card.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300

# Sandbox is only a temp cwd, so refuse code that clearly tries to wreck the machine.
_DENY = (
    "rm -rf /",
    "rmtree('/",
    'rmtree("/',
    "rmtree(os.path.expanduser",
    "os.system('rm ",
    'os.system("rm ',
    ":(){",
    "shutil.rmtree('/",
)


class PythonRun(CodedTool):
    """Execute a Python snippet in a throwaway directory and return its real output."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        code = args.get("code") or ""
        if not code.strip():
            return "Provide Python `code` to run."
        low = code.lower()
        if any(bad in low for bad in _DENY):
            return "Refused: the code looks destructive and was blocked as a safety backstop."
        try:
            timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT

        tmp = tempfile.mkdtemp(prefix="neura_py_")
        script = os.path.join(tmp, "main.py")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as exc:  # noqa: BLE001
            return f"$ python main.py\n(error writing script) {exc}"

        try:
            proc = subprocess.run(
                [sys.executable, script],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return f"$ python main.py\n(timed out after {timeout}s)"
        except Exception as exc:  # noqa: BLE001
            return f"$ python main.py\n(error) {exc}"

        parts = [f"$ python main.py  (in {tmp})", f"(exit code {proc.returncode})"]
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
