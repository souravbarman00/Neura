"""Dynamic agent-network spawning via the real `agent_network_designer`.

The designer network (ported from neuro-san-studio / alive) does the heavy lifting:
given a capability description it designs a multi-agent network, writes it to
registries/generated/<name>.hocon, and registers it in the generated manifest via
its own persistence middleware. The runtime hot-reloads it (AGENT_MANIFEST_UPDATE_PERIOD_SECONDS).

This module drives that designer, detects the network it produced, and records it in
our DB so the UI can list and title it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend import store
from backend.nsclient import collect

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "registries" / "generated"
GENERATED_MANIFEST = GENERATED_DIR / "manifest.hocon"
MCP_INFO = ROOT / "config" / "mcp" / "mcp_info.hocon"

# Substitution vars that are NOT user config (framework/LLM plumbing).
_NOISE_VARS = {"aaosa_call", "aaosa_instructions", "aaosa_command"}


def required_config(name: str) -> list[dict[str, str]]:
    """Best-effort list of env vars a spawned network needs (from its HOCON + MCP servers)."""
    stem = name.split("/")[-1]
    # Spawned networks live under generated/; connected tool agents live in registries/.
    hocon = GENERATED_DIR / f"{stem}.hocon"
    if not hocon.exists():
        hocon = ROOT / "registries" / f"{stem}.hocon"
    keys: set[str] = set()
    if hocon.exists():
        text = hocon.read_text(encoding="utf-8", errors="ignore")
        for _opt, var in re.findall(r"\$\{(\??)([A-Z0-9_]+)\}", text):
            if var not in _NOISE_VARS:
                keys.add(var)
        # Explicit hint for env vars read by coded tools: "# neura:config KEY1 KEY2 ..."
        for line in re.findall(r"#\s*neura:config\s+([A-Z0-9_ ]+)", text):
            for var in line.split():
                keys.add(var)
        urls = set(re.findall(r"https?://[^\s\"']+", text))
        if urls and MCP_INFO.exists():
            mcp_text = MCP_INFO.read_text(encoding="utf-8", errors="ignore")
            for url in urls:
                idx = mcp_text.find(url)
                if idx < 0:
                    continue
                block = mcp_text[idx : idx + 600]
                for _opt, var in re.findall(r"\$\{(\??)([A-Z0-9_]+)\}", block):
                    if var not in _NOISE_VARS:
                        keys.add(var)
    return [{"key": k, "label": k.replace("_", " ").title()} for k in sorted(keys)]


def _generated_names() -> set[str]:
    if not GENERATED_DIR.exists():
        return set()
    return {p.stem for p in GENERATED_DIR.glob("*.hocon") if p.name != "manifest.hocon"}


def _title_from_hocon(path: Path, fallback: str) -> str:
    """Best-effort friendly title from the generated network's metadata.description."""
    try:
        text = path.read_text(encoding="utf-8")
        m = re.search(r'"description"\s*:\s*"""(.*?)"""', text, re.DOTALL) or re.search(
            r'"description"\s*:\s*"([^"]+)"', text
        )
        if m:
            desc = " ".join(m.group(1).split())
            if desc:
                return desc[:80]
    except Exception:  # noqa: BLE001
        pass
    return fallback


async def spawn_via_designer(description: str) -> dict[str, Any]:
    """Drive agent_network_designer to create a network; record & return the result."""
    before = _generated_names()
    prompt = (
        f"Create a new agent network for this capability: {description}\n\n"
        "Design it, save it, and confirm the network name."
    )
    answer, _sources, _ctx = await collect("agent_network_designer", prompt)

    after = _generated_names()
    new = sorted(after - before)
    if not new:
        return {
            "status": "error",
            "message": "The designer did not produce a new network. Try rephrasing the capability.",
            "answer": answer[-800:],
        }

    created = []
    for name in new:
        served = f"generated/{name}"
        title = _title_from_hocon(GENERATED_DIR / f"{name}.hocon", name.replace("_", " ").title())
        store.add_network(
            name=served,
            title=title,
            description=(description or "")[:200],
            hocon_path=str(GENERATED_DIR / f"{name}.hocon"),
            config={},
        )
        created.append({"name": served, "title": title})

    return {"status": "created", "networks": created, "answer": answer}


def remove_network(name: str) -> None:
    """Delete a spawned network: DB record, hocon file, and manifest entry.

    `name` is the served name, e.g. 'generated/language_translator'.
    """
    store.delete_network(name)
    stem = name.split("/")[-1]
    hocon_path = GENERATED_DIR / f"{stem}.hocon"
    if hocon_path.exists():
        hocon_path.unlink()
    if GENERATED_MANIFEST.exists():
        lines = [
            ln for ln in GENERATED_MANIFEST.read_text(encoding="utf-8").splitlines()
            if f'"generated/{stem}.hocon"' not in ln
        ]
        GENERATED_MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
