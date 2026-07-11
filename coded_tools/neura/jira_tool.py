"""Neura CodedTool: authenticated Jira REST API calls.

Reads connection config from the environment (set via the Configuration panel → .env):
  - JIRA_BASE_URL   e.g. https://your-site.atlassian.net   (or your Data Center URL)
  - JIRA_API_TOKEN  an Atlassian API token (Cloud) or a Personal Access Token (Data Center)
  - JIRA_EMAIL      your Atlassian account email (Cloud only)

Auth mode is chosen automatically: if JIRA_EMAIL is set → Basic (email:token) for Jira
Cloud; otherwise → Bearer token for Jira Data Center/Server PATs.

The `jira` sub-agent drives this tool by choosing REST endpoints (it knows the Jira API).
Prefer the /rest/api/2 endpoints for plain-text comment/description bodies.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict

import httpx

from neuro_san.interfaces.coded_tool import CodedTool


class JiraRequest(CodedTool):
    """Make an authenticated request to the Jira REST API and return the result."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        method = (args.get("method") or "GET").upper()
        path = args.get("path") or ""
        body = args.get("body")

        base = (os.environ.get("JIRA_BASE_URL") or "").rstrip("/")
        token = os.environ.get("JIRA_API_TOKEN") or ""
        email = os.environ.get("JIRA_EMAIL") or ""

        if not base or not token:
            return (
                "Jira isn't configured yet. In the Configuration panel set JIRA_BASE_URL and "
                "JIRA_API_TOKEN (and JIRA_EMAIL for Jira Cloud), then save."
            )

        if not path.startswith("/"):
            path = "/" + path
        url = base + path

        if email:
            cred = base64.b64encode(f"{email}:{token}".encode()).decode()
            auth_header = f"Basic {cred}"
        else:
            auth_header = f"Bearer {token}"
        headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if isinstance(body, str) and body.strip():
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    method, url, headers=headers, json=body if body not in (None, "") else None
                )
        except Exception as exc:  # noqa: BLE001
            return f"Jira request error: {exc}"

        if resp.status_code in (401, 403):
            return (
                f"Jira auth failed (HTTP {resp.status_code}). Check JIRA_BASE_URL, JIRA_EMAIL and "
                "JIRA_API_TOKEN in the Configuration panel."
            )

        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            try:
                data = resp.json()
                text = json.dumps(data, indent=2)
            except Exception:  # noqa: BLE001
                text = resp.text
        else:
            text = resp.text

        if len(text) > 6000:
            text = text[:6000] + "\n… (truncated)"
        return f"HTTP {resp.status_code}\n{text}"
