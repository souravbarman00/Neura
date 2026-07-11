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

import asyncio
import logging
import os
import re
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any
from typing import Optional

from langchain_community.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_core.vectorstores.base import VectorStoreRetriever
from sqlalchemy.exc import ProgrammingError

# The shared vector-backend factory (WI1). base_rag is now routed through it for
# embeddings / chunk-splitting / vector-store construction. Imported as a module
# so the exporter's ast.walk reaches the dotted adapter imports it declares.
import toolbox.vector_backends as vector_backends

# Invalid file path character pattern
INVALID_PATH_PATTERN = r"[<>:\"|?*\x00-\x1F]"
DEFAULT_TABLE_NAME = "vectorstore"
# Kept as the factory DEFAULTS for back-compat (see vector_backends.DEFAULT_*).
EMBEDDINGS_MODEL = "text-embedding-3-small"
VECTOR_SIZE = 1536

logger = logging.getLogger(__name__)


@dataclass
class PostgresConfig:
    """Configuration for PostgreSQL connection."""

    user: str
    password: str
    host: str
    port: str
    database: str
    table_name: str

    @property
    def connection_string(self) -> str:
        """Generate PostgreSQL connection string."""

        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class BaseRag(ABC):
    """
    Abstract Base Class for different types of RAG implementations.
    """

    def __init__(self):
        # Save the generated vector store as a JSON file if True
        self.save_vector_store: bool = False
        self.abs_vector_store_path: Optional[str] = None
        # Embeddings are built through the factory using the legacy constants as
        # defaults, so existing behavior (text-embedding-3-small / 1536) is
        # reproduced unless a loader supplies an explicit embeddings config.
        self.embeddings: Embeddings = vector_backends.get_embeddings(
            {"model": EMBEDDINGS_MODEL, "dimensions": VECTOR_SIZE}
        )
        # Non-secret chunk selection routed through vector_backends.get_splitter.
        # Empty => factory defaults (1000/200).
        self.chunk_config: dict = {}

    @abstractmethod
    async def load_documents(self, loader_args: Any) -> list[Document]:
        """
        Abstract method to load documents from a specific data source.
        """
        raise NotImplementedError

    def configure_vector_store_path(self, vector_store_path: Optional[str]):
        """
        Validate the vector store file path and set it as an absolute path.

        :param vector_store_path: Relative or absolute path to the vector store JSON file.
        :raises ValueError: If the path contains invalid characters or has an incorrect file extension.
        """
        if not vector_store_path:
            return

        # Check for obviously invalid characters in filenames (basic check)
        if re.search(INVALID_PATH_PATTERN, vector_store_path):
            logger.error(
                "Invalid characters in vector_store_path: '%s'\n", vector_store_path
            )
            raise ValueError(f"Invalid vector_store_path: '{vector_store_path}'")

        # Check file extension
        if not vector_store_path.endswith(".json"):
            logger.error(
                "vector_store_path must be a .json file, got: '%s'\n", vector_store_path
            )
            raise ValueError(
                f"vector_store_path must be a .json file, got: '{vector_store_path}'"
            )

        if os.path.isabs(vector_store_path):
            # It's already an absolute path — use it directly
            self.abs_vector_store_path = vector_store_path
        else:
            # Combine to relative path to base path to make absolute path
            base_path: str = os.path.dirname(__file__)
            self.abs_vector_store_path = os.path.abspath(
                os.path.join(base_path, vector_store_path)
            )

    def resolve_vector_store_config(self, args: dict, sly_data: Optional[dict]) -> dict:
        """Resolve the backend connection dict for the loaders (P2-T4 shim).

        Prefers the new ``args["vector_store"]`` dict. Falls back to the legacy
        ``vector_store_type`` arg via a shim (``postgres`` -> ``pgvector``,
        anything else -> ``in_memory``). For a Postgres/pgvector backend the
        connection secrets PREFER ``sly_data["vector_store"]`` and fall back to
        the ``POSTGRES_*`` environment variables for back-compat.

        Non-secret selection (backend / index / table name) comes from operator
        ``args`` only; secrets never come from LLM-supplied args.
        """
        sly_data = sly_data or {}

        vs_arg = args.get("vector_store")
        if isinstance(vs_arg, dict):
            conn: dict = dict(vs_arg)
        else:
            # LEGACY shim: map the old vector_store_type onto a backend.
            legacy_type = args.get("vector_store_type", "in_memory")
            backend = "pgvector" if legacy_type == "postgres" else "in_memory"
            conn = {"backend": backend}

        backend = (conn.get("backend") or "in_memory").lower()

        if backend in {"pgvector", "postgres"}:
            conn["backend"] = "pgvector"
            # SECRETS: prefer sly_data["vector_store"], else POSTGRES_* env.
            sly_vs = dict(sly_data.get("vector_store") or {})
            creds = {
                "user": sly_vs.get("user", os.getenv("POSTGRES_USER")),
                "password": sly_vs.get("password", os.getenv("POSTGRES_PASSWORD")),
                "host": sly_vs.get("host", os.getenv("POSTGRES_HOST")),
                "port": sly_vs.get("port", os.getenv("POSTGRES_PORT")),
                "database": sly_vs.get("database", os.getenv("POSTGRES_DB")),
            }
            # sly_data may carry additional non-null connection keys; prefer them.
            merged = {**creds, **sly_vs}
            conn.update(
                {key: value for key, value in merged.items() if value is not None}
            )
            # Table/index name is operator config (back-compat: legacy 'table_name').
            table = (
                args.get("table_name") or conn.get("index") or conn.get("table_name")
            )
            if table:
                conn["index"] = table

        return conn

    async def generate_vector_store(
        self,
        loader_args: Any,
        postgres_config: Optional[PostgresConfig] = None,
        vector_store_type: str = "in_memory",
        vector_store: Optional[dict] = None,
        embeddings: Optional[dict] = None,
        chunk: Optional[dict] = None,
    ) -> Optional[VectorStore]:
        """
        Asynchronously loads documents from a given data source, splits them into
        chunks, and builds a vector store through the shared backend factory.

        :param loader_args: Arguments specific to the document loader
        :param postgres_config: Legacy PostgreSQL configuration (legacy shim path only)
        :param vector_store_type: Legacy vector store type selector (legacy shim path only)
        :param vector_store: New backend connection dict (``{"backend": ..., ...}``);
            when provided, construction is dispatched through the factory.
        :param embeddings: Optional non-secret embeddings config; routed through
            ``vector_backends.get_embeddings``.
        :param chunk: Optional non-secret chunk config; routed through
            ``vector_backends.get_splitter``.
        :return: Vector store containing the embedded document chunks
        """
        # Configure chunking / embeddings selection when supplied by the loader.
        if chunk is not None:
            self.chunk_config = dict(chunk)
        if embeddings:
            self.embeddings = vector_backends.get_embeddings(embeddings)

        # NEW factory path: an explicit backend connection dict is provided.
        if vector_store is not None:
            return await self._create_vector_store_via_factory(
                loader_args, vector_store
            )

        # LEGACY shim path — kept reachable for back-compat (env-Postgres,
        # direct vector_store_type callers) until every caller passes a dict.
        if vector_store_type not in {"in_memory", "postgres"}:
            logger.warning(
                "Received %s as 'vector_store_type'. Available types are 'in_memory' and 'postgres'\n",
                vector_store_type,
            )
            vector_store_type = "in_memory"

        # Validate postgres config if needed
        if vector_store_type == "postgres" and postgres_config is None:
            raise ValueError(
                "postgres_config is required when vector_store_type is 'postgres'\n"
            )

        # Try to load existing vector store for in-memory vector store
        if vector_store_type == "in_memory":
            existing_store = await self._load_existing_vector_store()
            if existing_store:
                return existing_store

        # Load and process documents
        vectorstore = await self._create_new_vector_store(
            loader_args, postgres_config, vector_store_type
        )

        # Save vector store if configured
        await self._save_vector_store(vectorstore, vector_store_type)

        return vectorstore

    async def _create_vector_store_via_factory(
        self, loader_args: Any, vector_store: dict
    ) -> Optional[VectorStore]:
        """Build a vector store via the WI1 factory and load the documents into it."""
        conn: dict = dict(vector_store or {})
        backend: str = (conn.get("backend") or vector_backends.DEFAULT_BACKEND).lower()

        # For in_memory, honor the existing save/load JSON cache (back-compat).
        if backend == "in_memory":
            existing_store = await self._load_existing_vector_store()
            if existing_store:
                return existing_store

        vectorstore = await vector_backends.get_vectorstore(
            backend, conn, self.embeddings
        )

        doc_chunks: list[Document] = await self._process_documents(loader_args)
        if doc_chunks:
            logger.info(
                "Adding %d document chunks to the '%s' vector store.",
                len(doc_chunks),
                backend,
            )
            await vectorstore.aadd_documents(doc_chunks)

        # Save vector store if configured (only meaningful for in_memory).
        await self._save_vector_store(
            vectorstore, "in_memory" if backend == "in_memory" else backend
        )

        return vectorstore

    async def _load_existing_vector_store(self) -> Optional[VectorStore]:
        """Try to load existing vector store from file."""

        if not self.abs_vector_store_path:
            return None

        try:
            vector_store: VectorStore = InMemoryVectorStore.load(
                path=self.abs_vector_store_path, embedding=self.embeddings
            )
            logger.info("Loaded vector store from: %s\n", self.abs_vector_store_path)
            return vector_store
        except FileNotFoundError:
            logger.info(
                "Vector store not found at: %s. Creating from source.\n",
                self.abs_vector_store_path,
            )
            return None

    async def _create_new_vector_store(
        self,
        loader_args: Any,
        postgres_config: Optional[PostgresConfig],
        vector_store_type: str,
    ) -> Optional[VectorStore]:
        """Create a new vector store."""

        if vector_store_type == "in_memory":
            return await self._create_in_memory_vector_store(loader_args)

        return await self._create_postgres_vector_store(loader_args, postgres_config)

    async def _process_documents(self, loader_args: Any) -> list[Document]:
        """Load and split documents"""
        # Load documents and build the vector store
        docs: list[Document] = await self.load_documents(loader_args)

        # Split documents into smaller chunks for better embedding and retrieval.
        # Routed through the factory; default chunking is now 1000/200.
        text_splitter = vector_backends.get_splitter(self.chunk_config)

        doc_chunks: list[Document] = text_splitter.split_documents(docs)
        logger.info("Processed %d document chunks\n", len(doc_chunks))

        return doc_chunks

    async def _create_in_memory_vector_store(self, loader_args) -> VectorStore:
        """Create an in-memory vector store."""
        doc_chunks: list[Document] = await self._process_documents(loader_args)
        logger.info("Creating in-memory vector store.")
        return await InMemoryVectorStore.afrom_documents(
            documents=doc_chunks,
            embedding=self.embeddings,
        )

    async def _create_postgres_vector_store(
        self, loader_args: Any, postgres_config: PostgresConfig
    ) -> Optional[VectorStore]:
        """Create a PostgreSQL vector store."""

        # Do lazy import so that users do not always have to install postgres
        # pylint: disable=import-error
        # pylint: disable=import-outside-toplevel
        from asyncpg import InvalidCatalogNameError
        from asyncpg import InvalidPasswordError
        from langchain_postgres import PGEngine
        from langchain_postgres import PGVectorStore

        # Create engine and table
        pg_engine = PGEngine.from_connection_string(
            url=postgres_config.connection_string
        )
        table_name: str = postgres_config.table_name or DEFAULT_TABLE_NAME

        logger.info(
            "PostgreSQL connection details:\n"
            + "  Host: %s\n"
            + "  Port: %s\n"
            + "  Database: %s\n"
            + "  Table: %s\n",
            postgres_config.host,
            postgres_config.port,
            postgres_config.database,
            table_name,
        )

        try:
            # Initialize vector store table
            await pg_engine.ainit_vectorstore_table(
                table_name=table_name,
                vector_size=VECTOR_SIZE,
            )

            doc_chunks: list[Document] = await self._process_documents(loader_args)

            logger.info("Creating postgres vector store from documents.")
            # Create vector store and load documents
            return await PGVectorStore.afrom_documents(
                documents=doc_chunks,
                embedding=self.embeddings,
                engine=pg_engine,
                table_name=table_name,
            )

        except ProgrammingError:
            # Table already exists. Create vector store from it.
            logger.info("Table %s already exists.\n", table_name)
            logger.info("Creating postgres vector store from existing table.\n")
            return await PGVectorStore.create(
                engine=pg_engine,
                table_name=table_name,
                embedding_service=self.embeddings,
            )

        except OSError as os_error:
            # Fail to create vector store due to connection error
            logger.error(
                "Fail to create vector store due to connection error. %s\n", os_error
            )
            return None

        except InvalidPasswordError as invalid_password_error:
            # Fail to create vector store due to invalid username or password
            logger.error(
                "Fail to create vector store due to invalid username or password. %s\n",
                invalid_password_error,
            )
            return None

        except InvalidCatalogNameError as invalid_catalog_error:
            # Fail to create vector store due to invalid DB name
            logger.error(
                "Fail to create vector store due to invalid DB name. %s\n",
                invalid_catalog_error,
            )
            return None

    async def _save_vector_store(
        self, vectorstore: VectorStore, vector_store_type: str
    ):
        """Save vector store to file if configured."""
        should_save: bool = (
            self.save_vector_store
            and self.abs_vector_store_path
            and vector_store_type == "in_memory"
        )

        if not should_save:
            return None

        try:
            os.makedirs(os.path.dirname(self.abs_vector_store_path), exist_ok=True)
            vectorstore.dump(path=self.abs_vector_store_path)
            logger.info("Vector store saved to: %s\n", self.abs_vector_store_path)
        except OSError as os_error:
            logger.error(
                "Failed to save vector store to %s: %s\n",
                self.abs_vector_store_path,
                os_error,
            )

    async def query_vectorstore(self, vectorstore: VectorStore, query: str) -> str:
        """
        Query the given vector store using the provided query string
        and return the combined content of retrieved documents.

        :param vectorstore: The in-memory vector store to query
        :param query: The user query to search for relevant documents
        :return: Concatenated text content of the retrieved documents
        """
        try:
            # Create a retriever interface from the vector store
            retriever: VectorStoreRetriever = vectorstore.as_retriever()

            return await self.query_retriever(retriever, query)

        except AttributeError:
            return "Failed to create vector store. Please check the log for more information.\n"

    @staticmethod
    async def query_retriever(retriever: Any, query: str) -> str:
        """
        Query the retriever with the given query string and return the results.

        :param retriever: The retriever interface to query
        :param query: The user query to search for relevant documents
        :return: Concatenated text content of the retrieved documents
        """
        try:
            # Perform an asynchronous similarity search
            results: list[Document] = await retriever.ainvoke(query)

            if results:
                logger.info("Retrieval completed!\n")

            formatted_results: list[dict[str, Any]] = []

            for doc in results:
                formatted_results.append(
                    {"content": doc.page_content, "metadata": doc.metadata}
                )

            return formatted_results

        except asyncio.TimeoutError as e:
            return f"Timed out while querying retriever: {e}"
