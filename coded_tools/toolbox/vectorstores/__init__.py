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

"""Per-backend vector-store adapters for the ALIVE plugin layer.

Each adapter module exposes the same five async coroutines::

    build(conn, embeddings) -> VectorStore
    fetch_hashes(vs, ids)   -> dict[str, str]
    upsert(vs, docs, ids)   -> None
    read_contract(vs)       -> dict | None
    write_contract(vs, meta) -> None

Every heavy client library is imported lazily *inside* the functions so these
modules import cleanly without the backend packages installed, while the
exporter's ``ast.walk`` still discovers the dependency names.
"""
