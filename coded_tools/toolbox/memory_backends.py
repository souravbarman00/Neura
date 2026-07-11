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

"""Shared memory-backend factory for the ALIVE plugin layer (P3-T1).

``get_memory(backend, conn)`` returns a backend adapter exposing the
key/value-by-``(namespace, topic)`` surface the explicit ``MemoryTool`` drives:
``write`` / ``read`` / ``remove`` / ``search`` / ``list``.

Adapters:

* ``in_memory`` — module-level dict; the always-green dev/CI DEFAULT. Requires
  no external service (mirrors the vector ``in_memory`` adapter).
* ``cosmos`` — Azure Cosmos DB (``azure.cosmos``).
* ``dynamodb`` — AWS DynamoDB (``boto3``).
* ``firestore`` — Google Cloud Firestore (``google.cloud.firestore``).

Cloud client libraries are LAZY-imported INSIDE methods so this module imports
clean without them installed, and so the exporter's ``ast.walk`` still records
each third-party import name for the bundle.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

_LOG = logging.getLogger(__name__)

DEFAULT_BACKEND = "in_memory"

# Module-level store for the in_memory backend: {namespace: {topic: content}}.
# Module-level (not instance) so the dev/CI store persists across get_memory()
# calls within a process — matching the vector in_memory fallback's semantics.
_IN_MEMORY_STORE: dict[str, dict[str, str]] = {}


class InMemoryBackend:
    """Dev/CI memory backend backed by a process-global dict (no service)."""

    def write(self, namespace: str, topic: str, content: str) -> None:
        """Store ``content`` under ``(namespace, topic)`` (replace-by-key)."""
        _IN_MEMORY_STORE.setdefault(namespace, {})[topic] = content

    def read(self, namespace: str, topic: str) -> str | None:
        """Return the content for ``(namespace, topic)`` or ``None``."""
        return _IN_MEMORY_STORE.get(namespace, {}).get(topic)

    def remove(self, namespace: str, topic: str) -> bool:
        """Delete ``(namespace, topic)``; return ``True`` if it existed."""
        bucket = _IN_MEMORY_STORE.get(namespace)
        if bucket is not None and topic in bucket:
            del bucket[topic]
            return True
        return False

    def search(self, namespace: str, query: str) -> list[dict[str, str]]:
        """Case-insensitive substring match over topics/content in ``namespace``."""
        needle = (query or "").strip().lower()
        out: list[dict[str, str]] = []
        for topic, content in _IN_MEMORY_STORE.get(namespace, {}).items():
            if not needle or needle in topic.lower() or needle in content.lower():
                out.append({"topic": topic, "content": content})
        return out

    def list(self, namespace: str) -> list[str]:
        """Return the topics stored under ``namespace``."""
        return sorted(_IN_MEMORY_STORE.get(namespace, {}).keys())


# Cosmos item ids may not contain these characters; the namespace embeds '/'.
_COSMOS_ID_TABLE = str.maketrans({c: "_" for c in "/\\?#"})


class CosmosBackend:
    """Azure Cosmos DB memory backend (one item per ``(namespace, topic)``)."""

    def __init__(self, conn: dict[str, Any]) -> None:
        self._conn = conn or {}
        self._container_client = None

    def _container(self):
        """Return a cached Cosmos container client (lazy client import)."""
        if self._container_client is not None:
            return self._container_client
        # Lazy import so the module loads without azure-cosmos installed.
        from azure.cosmos import CosmosClient

        endpoint = self._conn.get("endpoint")
        key = self._conn.get("key")
        database = self._conn.get("database")
        container = self._conn.get("container")
        client = CosmosClient(endpoint, credential=key)
        db_client = client.get_database_client(database)
        self._container_client = db_client.get_container_client(container)
        return self._container_client

    @staticmethod
    def _item_id(namespace: str, topic: str) -> str:
        # Cosmos item ids forbid / \ ? # (the namespace embeds '/'). Sanitize,
        # then append a short digest of the raw key so two distinct
        # (namespace, topic) pairs can never collide onto one sanitized id.
        # partition_key=namespace still scopes every read/write.
        raw = f"{namespace}::{topic}"
        safe = raw.translate(_COSMOS_ID_TABLE)[:200]
        return f"{safe}~{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:10]}"

    def write(self, namespace: str, topic: str, content: str) -> None:
        self._container().upsert_item(
            {
                "id": self._item_id(namespace, topic),
                "namespace": namespace,
                "topic": topic,
                "content": content,
            }
        )

    def read(self, namespace: str, topic: str) -> str | None:
        from azure.cosmos import exceptions

        try:
            item = self._container().read_item(
                item=self._item_id(namespace, topic),
                partition_key=namespace,
            )
        except exceptions.CosmosResourceNotFoundError:
            return None
        return item.get("content")

    def remove(self, namespace: str, topic: str) -> bool:
        from azure.cosmos import exceptions

        try:
            self._container().delete_item(
                item=self._item_id(namespace, topic),
                partition_key=namespace,
            )
        except exceptions.CosmosResourceNotFoundError:
            return False
        return True

    def search(self, namespace: str, query: str) -> list[dict[str, str]]:
        # Parameterized query — table/container come from operator config only.
        items = self._container().query_items(
            query=(
                "SELECT c.topic, c.content FROM c WHERE c.namespace=@ns AND "
                "(CONTAINS(LOWER(c.content), @q) OR CONTAINS(LOWER(c.topic), @q))"
            ),
            parameters=[
                {"name": "@ns", "value": namespace},
                {"name": "@q", "value": (query or "").strip().lower()},
            ],
            partition_key=namespace,
        )
        return [{"topic": i.get("topic"), "content": i.get("content")} for i in items]

    def list(self, namespace: str) -> list[str]:
        items = self._container().query_items(
            query="SELECT c.topic FROM c WHERE c.namespace=@ns",
            parameters=[{"name": "@ns", "value": namespace}],
            partition_key=namespace,
        )
        return sorted(i.get("topic") for i in items)


class DynamoDBBackend:
    """AWS DynamoDB memory backend (PK=namespace, SK=topic)."""

    def __init__(self, conn: dict[str, Any]) -> None:
        self._conn = conn or {}
        self._table_resource = None

    def _table(self):
        """Return a cached DynamoDB table resource (lazy client import)."""
        if self._table_resource is not None:
            return self._table_resource
        # Lazy import so the module loads without boto3 installed.
        import boto3

        kwargs: dict[str, Any] = {}
        if self._conn.get("region"):
            kwargs["region_name"] = self._conn["region"]
        if self._conn.get("access_key_id"):
            kwargs["aws_access_key_id"] = self._conn["access_key_id"]
        if self._conn.get("secret_access_key"):
            kwargs["aws_secret_access_key"] = self._conn["secret_access_key"]
        if self._conn.get("endpoint_url"):
            kwargs["endpoint_url"] = self._conn["endpoint_url"]
        resource = boto3.resource("dynamodb", **kwargs)
        self._table_resource = resource.Table(self._conn.get("table"))
        return self._table_resource

    def write(self, namespace: str, topic: str, content: str) -> None:
        self._table().put_item(
            Item={"namespace": namespace, "topic": topic, "content": content}
        )

    def read(self, namespace: str, topic: str) -> str | None:
        resp = self._table().get_item(Key={"namespace": namespace, "topic": topic})
        item = resp.get("Item")
        return item.get("content") if item else None

    def remove(self, namespace: str, topic: str) -> bool:
        resp = self._table().delete_item(
            Key={"namespace": namespace, "topic": topic},
            ReturnValues="ALL_OLD",
        )
        return bool(resp.get("Attributes"))

    def search(self, namespace: str, query: str) -> list[dict[str, str]]:
        from boto3.dynamodb.conditions import Key

        needle = (query or "").strip().lower()
        resp = self._table().query(
            KeyConditionExpression=Key("namespace").eq(namespace)
        )
        out: list[dict[str, str]] = []
        for item in resp.get("Items", []):
            topic = item.get("topic", "")
            content = item.get("content", "")
            if not needle or needle in topic.lower() or needle in content.lower():
                out.append({"topic": topic, "content": content})
        return out

    def list(self, namespace: str) -> list[str]:
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(
            KeyConditionExpression=Key("namespace").eq(namespace),
            ProjectionExpression="topic",
        )
        return sorted(i.get("topic") for i in resp.get("Items", []))


class FirestoreBackend:
    """Google Cloud Firestore memory backend (one doc per ``(namespace, topic)``)."""

    def __init__(self, conn: dict[str, Any]) -> None:
        self._conn = conn or {}
        self._db = None

    def _collection(self):
        """Return the configured Firestore collection (lazy client import)."""
        # Lazy import so the module loads without google-cloud-firestore installed.
        from google.cloud import firestore

        if self._db is None:
            project = self._conn.get("project") or None
            self._db = firestore.Client(project=project)
        return self._db.collection(self._conn.get("collection"))

    @staticmethod
    def _doc_id(namespace: str, topic: str) -> str:
        return f"{namespace}::{topic}"

    def write(self, namespace: str, topic: str, content: str) -> None:
        self._collection().document(self._doc_id(namespace, topic)).set(
            {"namespace": namespace, "topic": topic, "content": content}
        )

    def read(self, namespace: str, topic: str) -> str | None:
        snap = self._collection().document(self._doc_id(namespace, topic)).get()
        if not snap.exists:
            return None
        return (snap.to_dict() or {}).get("content")

    def remove(self, namespace: str, topic: str) -> bool:
        doc = self._collection().document(self._doc_id(namespace, topic))
        if not doc.get().exists:
            return False
        doc.delete()
        return True

    def search(self, namespace: str, query: str) -> list[dict[str, str]]:
        needle = (query or "").strip().lower()
        out: list[dict[str, str]] = []
        docs = self._collection().where("namespace", "==", namespace).stream()
        for snap in docs:
            data = snap.to_dict() or {}
            topic = data.get("topic", "")
            content = data.get("content", "")
            if not needle or needle in topic.lower() or needle in content.lower():
                out.append({"topic": topic, "content": content})
        return out

    def list(self, namespace: str) -> list[str]:
        docs = self._collection().where("namespace", "==", namespace).stream()
        return sorted((snap.to_dict() or {}).get("topic", "") for snap in docs)


_BACKENDS = {
    "in_memory": InMemoryBackend,
    "cosmos": CosmosBackend,
    "dynamodb": DynamoDBBackend,
    "firestore": FirestoreBackend,
}


def get_memory(backend: str | None, conn: dict[str, Any] | None):
    """Return a memory backend adapter for ``backend`` (defaulting when falsy).

    :param backend: Backend key (``in_memory``/``cosmos``/``dynamodb``/``firestore``).
    :param conn: Connection dict (secrets from ``sly_data["memory"]``); ignored by
        ``in_memory``.
    :return: A backend adapter exposing ``write``/``read``/``remove``/``search``/``list``.
    """
    key = (backend or DEFAULT_BACKEND).lower()
    cls = _BACKENDS.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown memory backend '{backend}'. Options: {sorted(_BACKENDS)}"
        )
    if cls is InMemoryBackend:
        return cls()
    return cls(conn or {})
