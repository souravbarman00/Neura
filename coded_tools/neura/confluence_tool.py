"""Neura CodedTool: authenticated Confluence REST API calls.

Confluence Cloud shares your Atlassian account and API token with Jira, so this
reuses the same credentials — no separate token needed:
  - CONFLUENCE_BASE_URL  e.g. https://your-site.atlassian.net/wiki
                         (optional; defaults to JIRA_BASE_URL + "/wiki")
  - JIRA_API_TOKEN       the same Atlassian API token used for Jira
  - JIRA_EMAIL           your Atlassian account email (Cloud)

Auth mode mirrors jira_tool: JIRA_EMAIL set → Basic (email:token) for Cloud;
otherwise → Bearer token (Data Center PAT).

The `confluence` sub-agent drives this by choosing REST endpoints (it knows the API).
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict

import httpx

from neuro_san.interfaces.coded_tool import CodedTool


class ConfluenceRequest(CodedTool):
    """Make an authenticated request to the Confluence REST API and return the result."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        method = (args.get("method") or "GET").upper()
        path = args.get("path") or ""
        body = args.get("body")

        # Confluence base URL: explicit, else derive from the Jira site (+ /wiki).
        base = (os.environ.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
        if not base:
            jira = (os.environ.get("JIRA_BASE_URL") or "").rstrip("/")
            if jira:
                base = jira if jira.endswith("/wiki") else jira + "/wiki"
        token = os.environ.get("JIRA_API_TOKEN") or ""
        email = os.environ.get("JIRA_EMAIL") or ""

        if not base or not token:
            return (
                "Confluence isn't configured yet. It reuses your Jira Atlassian credentials — "
                "set JIRA_BASE_URL and JIRA_API_TOKEN (and JIRA_EMAIL for Cloud) in the "
                "Configuration panel, or set CONFLUENCE_BASE_URL explicitly, then save."
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
            return f"Confluence request error: {exc}"

        if resp.status_code in (401, 403):
            return (
                f"Confluence auth failed (HTTP {resp.status_code}). Check CONFLUENCE_BASE_URL "
                "(or JIRA_BASE_URL), JIRA_EMAIL and JIRA_API_TOKEN in the Configuration panel."
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
