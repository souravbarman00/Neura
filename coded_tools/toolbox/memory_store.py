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

"""Explicit, wireable-today memory CodedTool over a configured backend (P3-T1).

``MemoryTool`` reads/writes topic-scoped memory on the catalog path (needs no
``memory_config``). The (network, agent, user) namespace is derived ENTIRELY
from server-side ``sly_data`` — never from LLM ``args`` (M4) — so a prompt can
never spoof cross-agent or cross-tenant memory access. The LLM only supplies
``action``/``topic``/``content``; the backend connection secrets come from
``sly_data["memory"]``.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import Dict

from neuro_san.interfaces.coded_tool import CodedTool

import toolbox.memory_backends as memory_backends

logger = logging.getLogger(__name__)


class MemoryTool(CodedTool):
    """Read/write topic-scoped memory over the configured memory backend."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        """Dispatch a memory ``action`` against the tenant-scoped namespace.

        :param args: NON-secret operator/LLM inputs. The LLM function schema
            exposes only ``action`` (``read``/``write``/``search``/``list``/
            ``remove``), ``topic`` and ``content``. ``backend`` is a non-secret
            HOCON selection arg (not in the LLM schema, so LLM-unspoofable) and
            is read args-first with a ``sly_data["memory"]["backend"]`` fallback.
            ``args`` is NEVER a source of tenant identity (M4).
        :param sly_data: Server-side context + secrets. ``sly_data["memory"]``
            holds the backend selection + connection; ``user_id``/
            ``agent_network``/``agent_name`` supply the namespace.
        :return: A concise tool-output string or a list of ``{topic, content}``.
        """
        action: str = (args.get("action") or "").strip().lower()
        topic: str = (args.get("topic") or "").strip()
        content: str = args.get("content") or ""

        # SECRETS + connection come only from sly_data.
        conn: Dict[str, Any] = dict((sly_data or {}).get("memory") or {})

        # M4: tenant identity is SERVER-SIDE ONLY — never read from args.
        user_id: str = (sly_data or {}).get("user_id") or ""
        network: str = (sly_data or {}).get("agent_network") or "net"
        agent: str = (sly_data or {}).get("agent_name") or "agent"
        namespace: str = f"{network}/{agent}/{user_id}"

        # NON-secret backend selection prefers args (HOCON) over sly_data.
        backend: str = args.get("backend") or conn.get("backend") or "in_memory"

        try:
            mem = memory_backends.get_memory(backend, conn)
        except ValueError as error:
            logger.error("memory_store configuration error: %s", error)
            return f"Memory error: {error}"

        try:
            if action == "write":
                if not topic:
                    return "Missing required input: 'topic' for write."
                mem.write(namespace, topic, content)
                return f"Stored memory topic '{topic}'."
            if action == "read":
                if not topic:
                    return "Missing required input: 'topic' for read."
                value = mem.read(namespace, topic)
                if value is None:
                    return f"No memory found for topic '{topic}'."
                return value
            if action == "search":
                query = content or topic
                return mem.search(namespace, query)
            if action == "list":
                return mem.list(namespace)
            if action in ("remove", "delete"):
                if not topic:
                    return "Missing required input: 'topic' for remove."
                removed = mem.remove(namespace, topic)
                if removed:
                    return f"Removed memory topic '{topic}'."
                return f"No memory found for topic '{topic}'."
        except Exception as error:  # noqa: BLE001 — surface ops errors to the agent
            logger.error("memory_store operational error: %s", error)
            return f"Memory operation failed: {error}"

        return (
            f"Unknown action '{action}'. "
            "Expected one of: read, write, search, list, remove."
        )
