# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

"""Canonical CodedTool scaffold for the Tool Studio (P3-T3).

This module is the reference skeleton every new coded tool starts from. It is
intentionally NOT registered in ``toolbox_info`` (the leading underscore keeps
it out of the catalog) — it exists to be copied, renamed, and filled in.

Contract (see ``tool_assistant._CONTRACT``):

- Exactly one public class that subclasses ``CodedTool``; keep the class name
  the Tool Studio gives you.
- Implement ``async def async_invoke(self, args, sly_data)``.
- ``args`` carries the LLM-facing parameters you declare (the function schema).
- ``sly_data[<sly_key>]`` carries the connection config / secrets (API keys, DB
  URLs, MCP endpoints). It is supplied at runtime by the operator and NEVER
  flows through the LLM and NEVER lands in saved HOCON — the saved config only
  ever holds the literal ``"sly_data"`` sentinel, never a value.
- Return a concrete JSON-serialisable value (dict / str / list). On failure
  return ``{"error": "..."}`` instead of raising.
- Heavy client libraries are imported lazily INSIDE ``async_invoke`` so the
  exporter can vendor them and import time stays cheap.
"""

from __future__ import annotations

from typing import Any
from typing import Dict

from neuro_san.interfaces.coded_tool import CodedTool

# The key under which this tool's connection config / secrets are delivered in
# ``sly_data``. The Tool Studio wires this to the tool's declared ``sly_key``.
SLY_KEY = "template_tool"


class TemplateTool(CodedTool):
    """Skeleton coded tool — copy this class, rename it, and fill in the body."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        """Run the tool's action and return a concrete result.

        :param args: The declared LLM-facing parameters (your function schema).
            Read inputs like ``args.get("query")``. Never read secrets from
            ``args`` — the LLM controls it.
        :param sly_data: Server-side context + secrets. ``sly_data[SLY_KEY]``
            holds the connection config the operator configured (API key, base
            URL, DB DSN, ...). Tenant identity — ``user_id`` / ``agent_network``
            / ``agent_name`` — is read from ``sly_data`` too, never from ``args``.
        :return: A JSON-serialisable dict/str/list, or ``{"error": "..."}``.
        """
        # CONNECTION / SECRETS — only ever from sly_data, never from args.
        cfg: Dict[str, Any] = dict((sly_data or {}).get(SLY_KEY) or {})
        if not cfg:
            return {
                "error": "not configured — set the connection details via the Configure dialog"
            }

        # INPUTS — the parameters the calling agent passes.
        query: str = (args.get("query") or "").strip()
        if not query:
            return {"error": "missing required input: 'query'"}

        # Lazily import any heavy client library HERE (so the exporter vendors it
        # and module import stays cheap), then call the API / DB / MCP endpoint:
        #
        #     import httpx
        #     resp = httpx.get(cfg["base_url"], params={"q": query}, timeout=15)
        #     resp.raise_for_status()
        #     return {"result": resp.json()}
        #
        # Keep exception handling narrow: surface auth/connection failures as a
        # concise ``{"error": ...}`` rather than swallowing them silently.
        return {"note": "not implemented yet", "query": query}
