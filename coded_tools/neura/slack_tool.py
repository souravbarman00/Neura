"""Neura CodedTool: authenticated Slack Web API calls.

Reads config from the environment (set via the Configuration panel → .env):
  - SLACK_BOT_TOKEN   a Slack bot token (xoxb-...) with the scopes you need
  - SLACK_USER_TOKEN  (optional) a user token (xoxp-...) — required for search.messages

The `slack` sub-agent drives this by choosing Slack Web API methods (it knows them).
All methods are POSTed form-encoded (works for both read and write methods); nested
values (e.g. blocks) are JSON-encoded as Slack expects.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import httpx

from neuro_san.interfaces.coded_tool import CodedTool


class SlackRequest(CodedTool):
    """Call a Slack Web API method and return the JSON result."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        method = (args.get("method") or "").strip().lstrip("/")
        params = args.get("params") or {}

        token = os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_USER_TOKEN") or ""
        if not method:
            return "Provide a Slack API method, e.g. conversations.list or chat.postMessage."
        if not token:
            return "Slack isn't configured. Set SLACK_BOT_TOKEN in the Configuration panel."

        if isinstance(params, str) and params.strip():
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        form: Dict[str, Any] = {}
        for k, v in (params or {}).items():
            form[k] = v if isinstance(v, (str, int, float, bool)) else json.dumps(v)

        url = f"https://slack.com/api/{method}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, headers=headers, data=form)
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            return f"Slack request error: {exc}"

        if not data.get("ok", False):
            err = data.get("error", "unknown_error")
            if err in ("not_authed", "invalid_auth", "account_inactive", "token_revoked", "token_expired"):
                return f"Slack auth failed ({err}). Check SLACK_BOT_TOKEN in the Configuration panel."
            if err == "missing_scope":
                return (
                    f"Slack error: missing_scope (needed: {data.get('needed')}, "
                    f"have: {data.get('provided')}). Add the scope to your Slack app and reinstall."
                )
            return f"Slack error: {err}"

        text = json.dumps(data, indent=2)
        if len(text) > 6000:
            text = text[:6000] + "\n… (truncated)"
        return text
