"""Neura CodedTool: authenticated Microsoft Graph API calls (Outlook + Teams).

Microsoft Graph uses short-lived OAuth access tokens. We keep a long-lived refresh
token (obtained once via scripts/ms_login.py, device-code flow) and exchange it for
an access token on demand, caching it until it expires.

Config (env, via Configuration panel + the login script):
  - MS_TENANT_ID     your Azure AD tenant id (or "common")
  - MS_CLIENT_ID     the registered app's Application (client) ID
  - MS_REFRESH_TOKEN written by scripts/ms_login.py after you sign in once
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from neuro_san.interfaces.coded_tool import CodedTool

_ROOT = Path(__file__).resolve().parents[2]
_ENV = _ROOT / ".env"

# Delegated scopes covering Outlook (mail + calendar) and Teams (chats). Teams
# *channel* messages (ChannelMessage.Read.All) usually need admin consent — add
# them later if your tenant grants them.
SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite Chat.Read Chat.ReadWrite"

_cache: Dict[str, Any] = {"token": None, "exp": 0.0}


def _persist_refresh(new_rt: str) -> None:
    """Persist a rotated refresh token back to .env so it survives restarts."""
    try:
        lines = []
        found = False
        if _ENV.exists():
            for ln in _ENV.read_text(encoding="utf-8").splitlines():
                if ln.startswith("MS_REFRESH_TOKEN="):
                    lines.append(f"MS_REFRESH_TOKEN={new_rt}")
                    found = True
                else:
                    lines.append(ln)
        if not found:
            lines.append(f"MS_REFRESH_TOKEN={new_rt}")
        _ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _ENV.chmod(0o600)
    except Exception:  # noqa: BLE001
        pass


async def _access_token() -> Tuple[Optional[str], Optional[str]]:
    now = time.time()
    if _cache["token"] and _cache["exp"] - 60 > now:
        return _cache["token"], None
    tenant = os.environ.get("MS_TENANT_ID") or "common"
    client = os.environ.get("MS_CLIENT_ID")
    refresh = os.environ.get("MS_REFRESH_TOKEN")
    if not client or not refresh:
        return None, (
            "Microsoft isn't connected yet. Set MS_TENANT_ID and MS_CLIENT_ID in the "
            "Configuration panel, then run: .venv/bin/python scripts/ms_login.py"
        )
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": client,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "scope": SCOPES,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, data=data)
        j = r.json()
    except Exception as exc:  # noqa: BLE001
        return None, f"Microsoft token request failed: {exc}"
    if "access_token" not in j:
        return None, (
            f"Microsoft auth failed: {j.get('error_description', j.get('error', 'unknown'))}. "
            "Re-run scripts/ms_login.py to sign in again."
        )
    _cache["token"] = j["access_token"]
    _cache["exp"] = now + int(j.get("expires_in", 3600))
    new_rt = j.get("refresh_token")
    if new_rt and new_rt != refresh:
        os.environ["MS_REFRESH_TOKEN"] = new_rt
        _persist_refresh(new_rt)
    return j["access_token"], None


class GraphRequest(CodedTool):
    """Make an authenticated Microsoft Graph request and return the result."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        method = (args.get("method") or "GET").upper()
        path = args.get("path") or ""
        body = args.get("body")

        token, err = await _access_token()
        if err:
            return err

        if path.startswith("http"):
            url = path  # follow @odata.nextLink etc.
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = f"https://graph.microsoft.com/v1.0{path}"

        if isinstance(body, str) and body.strip():
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.request(method, url, headers=headers, json=body if body not in (None, "") else None)
        except Exception as exc:  # noqa: BLE001
            return f"Microsoft Graph request error: {exc}"

        if r.status_code in (401, 403):
            return (
                f"Microsoft Graph {r.status_code}: {r.text[:400]}\n"
                "The token may lack a required scope/consent (Teams channel access often needs "
                "admin consent). Re-run scripts/ms_login.py or ask an admin to consent."
            )
        ctype = r.headers.get("content-type", "")
        if "json" in ctype:
            try:
                text = json.dumps(r.json(), indent=2)
            except Exception:  # noqa: BLE001
                text = r.text
        else:
            text = r.text or f"(HTTP {r.status_code}, empty body)"
        if len(text) > 6000:
            text = text[:6000] + "\n… (truncated)"
        return f"HTTP {r.status_code}\n{text}"
